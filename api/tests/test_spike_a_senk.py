"""Spike A · çevrimdışı kuyruk ve idempotent senk — Flutter'sız koşum.

ADR-0013 md.3 Faz B'nin ilk işini Spike A olarak veriyor ve sorusu şu:
*72 saat çevrimdışı, 500 kanıt, iki cihaz aynı çalıştırma: kanıt kaybı
sıfır ve tek kayıt garantisi verilebilir mi?* (FR-0701…0708, BR-24,
TC-051…055)

Spike Flutter'da planlanmıştı. Burada **sunucu tarafı** Flutter'sız
koşuluyor: aşağıdaki `Cihaz` sınıfı mobil istemcinin yapacağı şeyi
yapıyor — çevrimdışı kuyruk tutuyor, kayıtların kimliğini **kendisi**
üretiyor, bağlantı gelince `/sync/batch` ile gönderiyor, dönen yükleme
adreslerine baytları yüklüyor ve `complete` ile kapatıyor.

Neden önce burada: senk sözleşmesinin birim testleri vardı ama onu
**hiçbir istemci çalıştırmamıştı** — saha istemcisi çevrimdışı
çalışmıyor. Sözleşme kâğıt üzerinde doğru olup sahada bozuk olabilir ve
bunu Flutter'da keşfetmek mobil geliştiricinin haftalarına mal olur.
Burada bir güne mal oluyor.

Kapsam dışı (Flutter gerektiriyor, spike'ın kalanı): arka plan senkinin
uygulama öldürülüp açılınca sürmesi, WorkManager/BGTask davranışı,
ekrandaki bekleyen sayısı, kamera yolu (Spike C).
"""

from __future__ import annotations

import hashlib
import struct
import zlib
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from conftest import json_madde_degeri, oturum_ac
from talimatname.api.app import create_app
from talimatname.domain.sync import MAX_BATCH_ANSWERS, MAX_BATCH_EVIDENCE
from talimatname.settings import Settings


def _png(etiket: str) -> bytes:
    """Küçük ama **benzersiz** PNG: aynı baytlar kanıt tekrarı sayılır."""
    en = boy = 8
    tohum = int(hashlib.sha256(etiket.encode()).hexdigest()[:6], 16)
    r, g, b = (tohum >> 16) & 0xFF, (tohum >> 8) & 0xFF, tohum & 0xFF
    satirlar = b"".join(b"\x00" + bytes([r, g, b]) * en for _ in range(boy))

    def parca(tur: bytes, veri: bytes) -> bytes:
        return (
            struct.pack(">I", len(veri))
            + tur
            + veri
            + struct.pack(">I", zlib.crc32(tur + veri) & 0xFFFFFFFF)
        )

    return (
        b"\x89PNG\r\n\x1a\n"
        + parca(b"IHDR", struct.pack(">IIBBBBB", en, boy, 8, 2, 0, 0, 0))
        + parca(b"IDAT", zlib.compress(satirlar))
        + parca(b"IEND", b"")
    )


@dataclass
class Kuyruk:
    """Cihazdaki çevrimdışı kuyruk. Gönderilen kayıt silinmez: sunucu
    'accepted' demedikçe cihaz onu bırakmamalı (FR-0703)."""

    cevaplar: list[dict[str, Any]] = field(default_factory=list)
    kanitlar: list[dict[str, Any]] = field(default_factory=list)
    baytlar: dict[str, bytes] = field(default_factory=dict)

    def __len__(self) -> int:
        return len(self.cevaplar) + len(self.kanitlar)


@dataclass
class SenkSonucu:
    kabul_cevap: int = 0
    red_cevap: int = 0
    kabul_kanit: int = 0
    tekrar_kanit: int = 0
    red_kanit: int = 0
    yuklenen: int = 0
    hatalar: list[str] = field(default_factory=list)


class Cihaz:
    """Mobil istemcinin sunucuya bakan yüzü: kuyruk + senk döngüsü."""

    def __init__(self, istemci: TestClient, ad: str) -> None:
        self.istemci = istemci
        self.ad = ad
        self.device_id = uuid4()
        self.kuyruk = Kuyruk()

    # --- çevrimdışı -------------------------------------------------

    def cevapla(
        self,
        run_id: str,
        madde: dict[str, Any],
        durum: str = "passed",
        *,
        answer_id: UUID | None = None,
        cevap_ani: datetime | None = None,
        kanit_sayisi: int = 0,
    ) -> UUID:
        aid = answer_id or uuid4()
        kayit: dict[str, Any] = {
            "answer_id": str(aid),
            "run_id": run_id,
            "item_id": madde["id"],
            "state": durum,
            "device_id": str(self.device_id),
            "evidence_count": kanit_sayisi,
        }
        deger = json_madde_degeri(madde, durum)
        if deger is not None:
            kayit["value"] = deger
        if durum == "not_done":
            kayit["not_done_reason"] = "no_time"
            kayit["note"] = "Cevrimdisi denemede yapilamadi"
        if durum == "failed":
            kayit["note"] = "Cevrimdisi denemede basarisiz"
        if cevap_ani is not None:
            kayit["answered_at"] = cevap_ani.isoformat()
        self.kuyruk.cevaplar.append(kayit)
        return aid

    def fotografla(self, run_id: str, answer_id: UUID, madde: dict[str, Any], etiket: str) -> UUID:
        eid = uuid4()
        ham = _png(f"{self.ad}:{etiket}:{eid}")
        self.kuyruk.kanitlar.append(
            {
                "evidence_id": str(eid),
                "run_id": run_id,
                "answer_id": str(answer_id),
                "item_id": madde["id"],
                "sha256": hashlib.sha256(ham).hexdigest(),
                "content_type": "image/png",
                "size_bytes": len(ham),
                "from_gallery": False,
                "device_id": str(self.device_id),
            }
        )
        self.kuyruk.baytlar[str(eid)] = ham
        return eid

    # --- bağlantı geldi ---------------------------------------------

    def senkle(self, *, device_time: datetime | None = None) -> SenkSonucu:
        """Kuyruğu gönderir, kabul edilen kanıtların baytlarını yükler."""
        sonuc = SenkSonucu()
        for cevap_dilimi, kanit_dilimi in self._dilimler():
            govde: dict[str, Any] = {"answers": cevap_dilimi, "evidence": kanit_dilimi}
            if device_time is not None:
                govde["device_time"] = device_time.isoformat()
            yanit = self.istemci.post("/api/v1/sync/batch", json=govde)
            assert yanit.status_code == 200, yanit.text
            govde_yanit = yanit.json()

            for satir in govde_yanit["answers"]:
                if satir["outcome"] == "accepted":
                    sonuc.kabul_cevap += 1
                else:
                    sonuc.red_cevap += 1
                    sonuc.hatalar.append(satir["error"]["type"])

            for satir in govde_yanit["evidence"]:
                if satir["outcome"] == "rejected":
                    sonuc.red_kanit += 1
                    sonuc.hatalar.append(satir["error"]["type"])
                    continue
                if satir["outcome"] == "duplicate":
                    sonuc.tekrar_kanit += 1
                    continue
                sonuc.kabul_kanit += 1
                if self._yukle(satir):
                    sonuc.yuklenen += 1
        return sonuc

    def _dilimler(self) -> list[tuple[list[dict[str, Any]], list[dict[str, Any]]]]:
        """Kuyruğu sunucunun parti sınırlarına böler (FR-0707)."""
        dilimler = []
        c, k = self.kuyruk.cevaplar, self.kuyruk.kanitlar
        adim = max(1, (len(c) // MAX_BATCH_ANSWERS) + (1 if len(c) % MAX_BATCH_ANSWERS else 0))
        adim = max(adim, (len(k) // MAX_BATCH_EVIDENCE) + (1 if len(k) % MAX_BATCH_EVIDENCE else 0))
        for i in range(adim):
            dilimler.append(
                (
                    c[i * MAX_BATCH_ANSWERS : (i + 1) * MAX_BATCH_ANSWERS],
                    k[i * MAX_BATCH_EVIDENCE : (i + 1) * MAX_BATCH_EVIDENCE],
                )
            )
        return dilimler or [([], [])]

    def _yukle(self, satir: dict[str, Any]) -> bool:
        """Baytları gönderip `complete` ile kapatır."""
        eid = satir["evidence_id"]
        ham = self.kuyruk.baytlar.get(eid)
        if ham is None or not satir.get("upload_url"):
            return False
        yol = satir["upload_url"]
        self.istemci.request("PUT", yol, content=ham, headers={"Content-Type": "image/png"})
        kapanis = self.istemci.post(f"/api/v1/evidence/{eid}/complete", json={})
        return kapanis.status_code == 200


# --- ortam ------------------------------------------------------------


@pytest.fixture
def istemci(tmp_path: Path) -> TestClient:
    return oturum_ac(TestClient(create_app(Settings(evidence_dir=str(tmp_path)))), "staff")


def _acik_calistirma(istemci: TestClient) -> tuple[str, list[dict[str, Any]]]:
    """Manifestten yazılabilir bir çalıştırma ve maddeleri.

    Tohumdaki pencereler sabit saatlerde; testi duvar saatine bağlamamak
    için gerektiğinde penceresi şu anı kapsayan bir plan kuruluyor
    (`test_execution` ile aynı yol).
    """
    manifest = _yazilabilir_manifest(istemci)
    aday = _yazilabilir(manifest)
    assert aday, "manifestte yazılabilir çalıştırma yok"
    run = aday[0]
    # Manifest sürümün **kimliğini** veriyor, içeriğini değil: sürüm
    # yayınlandıktan sonra değişmediği için cihaz bir kez indirip
    # süresiz önbelleğe alıyor (ManifestSurumu açıklaması).
    return run["run_id"], _maddeler(istemci, run["template_version_id"])


def _maddeler(istemci: TestClient, version_id: str) -> list[dict[str, Any]]:
    surum = istemci.get(f"/api/v1/template-versions/{version_id}").json()
    return [m for b in surum["sections"] for m in b["items"] if m["type"] != "instruction"]


def _yazilabilir_manifest(istemci: TestClient) -> dict[str, Any]:
    """Yazılabilir çalıştırma içeren manifest; yoksa plan kurup döner."""
    manifest = istemci.get("/api/v1/sync/manifest").json()
    if _yazilabilir(manifest):
        return manifest
    from test_execution import _acik_calistirma as _calistirma_kur

    cagiranin = istemci.headers.get("Authorization")
    try:
        _calistirma_kur(oturum_ac(istemci, "branch_manager"))
    finally:
        if cagiranin is not None:
            istemci.headers["Authorization"] = cagiranin
    return istemci.get("/api/v1/sync/manifest").json()


def _yazilabilir(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    simdi = datetime.now(UTC)
    return [
        r
        for r in manifest["runs"]
        if datetime.fromisoformat(r["writable_from"]) <= simdi
        and datetime.fromisoformat(r["tolerance_end"]) > simdi
    ]


def _sunucudaki_cevaplar(istemci: TestClient, run_id: str) -> dict[str, dict[str, Any]]:
    gorunum = istemci.get(f"/api/v1/runs/{run_id}").json()
    return {
        m["item_id"]: m["answer"]
        for b in gorunum["sections"]
        for m in b["items"]
        if m.get("answer")
    }


# --- manifest ---------------------------------------------------------


def test_manifest_cihazin_ihtiyaci_olani_tasiyor() -> None:
    """Cihaz pencereyi, sürümü ve sınırları manifestten öğrenmeli."""
    istemci = oturum_ac(TestClient(create_app(Settings())), "staff")

    manifest = istemci.get("/api/v1/sync/manifest").json()

    assert manifest["clock"]["server_time"]
    assert manifest["horizon_hours"] > 0
    # Parti sınırları **kuyruk** sınırından ayrı ve ikisi de söylenmeli:
    # aşılınca sunucu bütün isteği 422 ile reddediyor (Spike A bulgusu).
    assert manifest["policy"]["batch_answer_limit"] == MAX_BATCH_ANSWERS
    assert manifest["policy"]["batch_evidence_limit"] == MAX_BATCH_EVIDENCE
    assert manifest["policy"]["queue_evidence_limit"] >= MAX_BATCH_EVIDENCE
    assert manifest["runs"], "manifest boş: cihaz ne indireceğini bilemez"
    # BR-02a: pencere açılmadan doldurmaya davet etmemeli (ADR-0013 eki).
    assert all("writable_from" in r for r in manifest["runs"])


# --- idempotentlik ----------------------------------------------------


def test_ayni_kuyruk_iki_kez_gonderilince_cift_kayit_olmuyor(istemci: TestClient) -> None:
    """Kabul yanıtı kaybolursa cihaz aynı kuyruğu yeniden gönderir.

    TC-051: kimlik cihazda üretildiği için ikinci gönderim aynı kaydı
    günceller, yenisini açmaz.
    """
    run_id, maddeler = _acik_calistirma(istemci)
    cihaz = Cihaz(istemci, "A")
    for madde in maddeler[:5]:
        cihaz.cevapla(run_id, madde)

    ilk = cihaz.senkle()
    ikinci = cihaz.senkle()

    assert ilk.kabul_cevap == 5
    assert ikinci.kabul_cevap == 5, "tekrar gönderim reddedildi: kuyruk tıkanır"
    assert ikinci.red_cevap == 0
    sunucuda = _sunucudaki_cevaplar(istemci, run_id)
    assert len({sunucuda[m["id"]]["id"] for m in maddeler[:5]}) == 5


def test_ayni_fotograf_ikinci_kez_tekrar_diye_doner(istemci: TestClient) -> None:
    """Kanıt tekrarı **hata değil**: cihaz kuyruğu temizleyebilmeli."""
    run_id, maddeler = _acik_calistirma(istemci)
    madde = maddeler[0]
    cihaz = Cihaz(istemci, "A")
    aid = cihaz.cevapla(run_id, madde, kanit_sayisi=1)
    cihaz.fotografla(run_id, aid, madde, "tek")

    ilk = cihaz.senkle()
    ikinci = cihaz.senkle()

    assert ilk.kabul_kanit == 1
    assert ilk.yuklenen == 1
    assert ikinci.red_kanit == 0, "tekrar fotoğraf reddedilirse kuyruk sonsuza kadar tıkanır"
    assert ikinci.kabul_kanit + ikinci.tekrar_kanit == 1


def test_kayip_yok_yirmi_madde_bes_fotograf(istemci: TestClient) -> None:
    """Spike A deneyinin uçak modu senaryosu: hepsi sunucuya ulaşmalı."""
    run_id, maddeler = _acik_calistirma(istemci)
    cihaz = Cihaz(istemci, "A")
    fotografli = [m for m in maddeler if m["type"] == "photo"][:5]
    for madde in maddeler:
        kanit = 1 if madde in fotografli else 0
        aid = cihaz.cevapla(run_id, madde, kanit_sayisi=kanit)
        if kanit:
            cihaz.fotografla(run_id, aid, madde, madde["title"][:12])

    sonuc = cihaz.senkle()

    assert sonuc.red_cevap == 0, sonuc.hatalar
    assert sonuc.kabul_cevap == len(maddeler)
    assert sonuc.yuklenen == len(fotografli)
    assert len(_sunucudaki_cevaplar(istemci, run_id)) == len(maddeler)


# --- iki cihaz --------------------------------------------------------


def test_iki_cihaz_ayni_calistirma_tek_kayit(istemci: TestClient) -> None:
    """BR-24: aynı maddeye iki cevap gelirse son yazan kazanır, kayıt tek.

    İki cihaz **aynı kullanıcıyla**: kilit kişiye bağlı olduğu için
    ikisi de yazabiliyor. Farklı kullanıcı senaryosu BR-26'da ve
    `test_execution` içinde sınanıyor.
    """
    run_id, maddeler = _acik_calistirma(istemci)
    madde = maddeler[0]
    a, b = Cihaz(istemci, "A"), Cihaz(istemci, "B")
    a.cevapla(run_id, madde, "passed")
    b.cevapla(run_id, madde, "failed")

    a.senkle()
    b.senkle()

    sunucuda = _sunucudaki_cevaplar(istemci, run_id)
    assert madde["id"] in sunucuda
    # Tek kayıt: iki cihaz iki satır açmadı.
    gorunum = istemci.get(f"/api/v1/runs/{run_id}").json()
    satirlar = [
        m for bol in gorunum["sections"] for m in bol["items"] if m["item_id"] == madde["id"]
    ]
    assert len(satirlar) == 1


def test_iki_cihaz_karisik_sirayla_yuz_tur(istemci: TestClient) -> None:
    """Spike A kabulü: 100 tekrarda sıfır kayıp, sıfır çift kayıt."""
    run_id, maddeler = _acik_calistirma(istemci)
    madde = maddeler[0]
    a, b = Cihaz(istemci, "A"), Cihaz(istemci, "B")
    sabit_a, sabit_b = uuid4(), uuid4()
    a.cevapla(run_id, madde, "passed", answer_id=sabit_a)
    b.cevapla(run_id, madde, "failed", answer_id=sabit_b)

    for tur in range(50):
        (a if tur % 2 == 0 else b).senkle()
        (b if tur % 2 == 0 else a).senkle()

    gorunum = istemci.get(f"/api/v1/runs/{run_id}").json()
    satirlar = [
        m for bol in gorunum["sections"] for m in bol["items"] if m["item_id"] == madde["id"]
    ]
    assert len(satirlar) == 1
    assert satirlar[0]["answer"] is not None


# --- sınır ve ret davranışı -------------------------------------------


def test_bozuk_kayit_kuyrugu_tikamiyor(istemci: TestClient) -> None:
    """Tek bozuk kayıt yüzünden 4xx dönmek kuyruğu sonsuza tıkardı."""
    run_id, maddeler = _acik_calistirma(istemci)
    cihaz = Cihaz(istemci, "A")
    cihaz.cevapla(run_id, maddeler[0])
    # Olmayan maddeye cevap: tek kayıt reddedilmeli, parti değil.
    cihaz.kuyruk.cevaplar.append(
        {
            "answer_id": str(uuid4()),
            "run_id": run_id,
            "item_id": str(uuid4()),
            "state": "passed",
            "device_id": str(cihaz.device_id),
        }
    )
    cihaz.cevapla(run_id, maddeler[1])

    sonuc = cihaz.senkle()

    assert sonuc.kabul_cevap == 2
    assert sonuc.red_cevap == 1
    assert sonuc.hatalar, "reddin sebebi yazılmamış: cihaz ne yapacağını bilemez"


def test_penceresi_kapanmis_calistirma_reddediliyor(istemci: TestClient) -> None:
    """Geç kalan kuyruk sessizce kabul edilmemeli (BR-03).

    `retryable` **false** olmalı: cihaz bunu sonsuza kadar denememeli.
    """
    # Gerçek senaryo: cihaz manifesti dün indirdi, çevrimdışı kaldı,
    # pencere bu arada kapandı. Manifest ufku ileriye baktığı için
    # kapanmış çalıştırmayı çalıştırma listesinden alıyoruz.
    simdi = datetime.now(UTC)
    kapali = None
    for gun in range(1, 8):
        tarih = (simdi - timedelta(days=gun)).date().isoformat()
        aday = [
            r
            for r in istemci.get(f"/api/v1/runs?business_day={tarih}").json()
            if datetime.fromisoformat(r["tolerance_end"]) <= simdi
        ]
        if aday:
            kapali = aday[0]
            break
    assert kapali is not None, "penceresi kapanmış çalıştırma bulunamadı"
    gorunum = istemci.get(f"/api/v1/runs/{kapali['id']}").json()
    ham = next(m for b in gorunum["sections"] for m in b["items"] if m["type"] != "instruction")
    madde = {**ham, "id": ham["item_id"]}

    cihaz = Cihaz(istemci, "A")
    cihaz.cevapla(kapali["id"], madde)
    yanit = istemci.post("/api/v1/sync/batch", json={"answers": cihaz.kuyruk.cevaplar}).json()

    satir = yanit["answers"][0]
    assert satir["outcome"] == "rejected"
    assert satir["error"]["retryable"] is False


def test_saat_kaymasi_kaydediliyor_reddedilmiyor(istemci: TestClient) -> None:
    """FR-0704: cihaz saati yanlışsa kayıt alınır, sapma işaretlenir."""
    run_id, maddeler = _acik_calistirma(istemci)
    cihaz = Cihaz(istemci, "A")
    kayma = datetime.now(UTC) - timedelta(hours=3)
    cihaz.cevapla(run_id, maddeler[0], cevap_ani=kayma)

    sonuc = cihaz.senkle(device_time=kayma)

    assert sonuc.kabul_cevap == 1
    cevap = _sunucudaki_cevaplar(istemci, run_id)[maddeler[0]["id"]]
    assert cevap["clock_skew_minutes"] is not None
    assert abs(cevap["clock_skew_minutes"]) >= 170
    assert cevap["clock_flagged"] is True


def test_madde_basina_dorduncu_fotograf_reddediliyor(istemci: TestClient) -> None:
    """Sınır sunucuda: cihaz saymayı unutursa kayıt reddedilir."""
    run_id, maddeler = _acik_calistirma(istemci)
    madde = next(m for m in maddeler if m["type"] == "photo")
    cihaz = Cihaz(istemci, "A")
    aid = cihaz.cevapla(run_id, madde, kanit_sayisi=3)
    for sira in range(4):
        cihaz.fotografla(run_id, aid, madde, f"kare-{sira}")

    sonuc = cihaz.senkle()

    assert sonuc.kabul_kanit == 3
    assert sonuc.red_kanit == 1
    assert any("kanit-sayisi" in h for h in sonuc.hatalar)
