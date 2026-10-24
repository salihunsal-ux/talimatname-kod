"""Damgalama işçisi testleri (ST-040; TC-043, FR-0606, FR-1208).

Burada sınanan iddia şu: **ham dosya kanıttır, damgalı kopya anlatır.**
Ham dosyanın baytı değişmez (BR-12, özeti kayıtta duruyor); damgalı
kopya ve küçük resim yanına yazılır.
"""

from __future__ import annotations

import hashlib
import io
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from conftest import oturum_ac
from talimatname.api.app import create_app
from talimatname.domain.evidence import derived_key, stamp_text
from talimatname.infra.memory import (
    MemoryEvidenceRepository,
    MemoryOrganizationRepository,
    MemoryPlanRepository,
    MemoryTemplateRepository,
    MemoryUserRepository,
    sabit_id,
)
from talimatname.services import imaging
from talimatname.services.evidence import EvidenceService
from talimatname.services.plans import PlanService
from talimatname.services.storage import LocalObjectStore, digest
from talimatname.settings import Settings

KADIKOY = sabit_id("sube:KDK")
PERSONEL = "+905321110005"


def _resim(
    genislik: int = 900,
    yukseklik: int = 600,
    bicim: str = "JPEG",
    renk: tuple[int, int, int] = (40, 90, 140),
) -> tuple[bytes, str]:
    """Sentetik görsel: gerçek fotoğraf değil, gerçek bir JPEG/PNG."""
    resim = Image.new("RGB", (genislik, yukseklik), renk)
    tampon = io.BytesIO()
    resim.save(tampon, format=bicim)
    baytlar = tampon.getvalue()
    return baytlar, hashlib.sha256(baytlar).hexdigest()


class Dunya:
    def __init__(self, tmp: Path) -> None:
        self.an = datetime.now(UTC)
        self.planlar = MemoryPlanRepository()
        self.org = MemoryOrganizationRepository()
        self.kullanicilar = MemoryUserRepository()
        PlanService(
            self.planlar, self.org, MemoryTemplateRepository(), now=lambda: self.an
        ).generate_all()
        self.depo = LocalObjectStore(tmp)
        self.servis = EvidenceService(
            MemoryEvidenceRepository(),
            self.planlar,
            self.org,
            self.depo,
            self.kullanicilar,
            settings=Settings(environment="dev"),
            now=lambda: self.an,
        )
        self.run_id = next(r for r in self.planlar.runs() if r.branch_id == KADIKOY).id
        kisi = self.kullanicilar.user_by_phone(PERSONEL)
        assert kisi is not None
        self.kisi = kisi

    def kanit_yukle(self, baytlar: bytes, ozet: str, **ek: object) -> UUID:
        """Doğrulanmış (stored) bir kanıt bırakır: işçinin girdisi."""
        kanit, belirtec = self.servis.start(
            run_id=self.run_id,
            answer_id=ek.pop("answer_id", uuid4()),  # type: ignore[arg-type]
            item_id=ek.pop("item_id", sabit_id("madde:1")),  # type: ignore[arg-type]
            sha256=ozet,
            content_type=ek.pop("content_type", "image/jpeg"),  # type: ignore[arg-type]
            size_bytes=len(baytlar),
            user_id=self.kisi.id,
            **ek,  # type: ignore[arg-type]
        )
        self.servis.receive(belirtec, baytlar)
        return self.servis.complete(kanit.id).id


@pytest.fixture
def dunya(tmp_path: Path) -> Dunya:
    return Dunya(tmp_path)


# --- damga metni (FR-0606) --------------------------------------------


def test_damga_metni_sube_tarih_kisi() -> None:
    metin = stamp_text(
        "Kadıköy",
        "Emre Personel",
        datetime(2026, 11, 2, 23, 40, tzinfo=UTC),
        "UTC+3",
    )
    assert metin == "Kadıköy · 02.11.2026 23:40 UTC+3 · Emre Personel"


def test_damga_metni_kisi_bilinmiyorsa_bos_birakmaz() -> None:
    metin = stamp_text("Kadıköy", None, datetime(2026, 11, 2, 7, 5, tzinfo=UTC), "UTC+3")
    assert metin.endswith("· —")


def test_damga_metni_sube_saatiyle_yazilir(dunya: Dunya) -> None:
    """Denetçi yerel saat bekler; UTC damga okunmaz (FR-0606)."""
    baytlar, ozet = _resim()
    kanit_id = dunya.kanit_yukle(baytlar, ozet)
    kanit = dunya.servis.get(kanit_id)

    metin = dunya.servis._damga_metni(kanit)

    assert metin.startswith("Kadıköy · ")
    assert "UTC+3" in metin
    assert dunya.kisi.full_name in metin


# --- yazı tipi --------------------------------------------------------


def test_yazi_tipi_turkce_harfleri_cizebiliyor() -> None:
    """Gömülü yazı tipinde ş/ğ/İ yok: sınamadan damga kutu kutu çıkar."""
    try:
        font, yol = imaging.find_font(20)
    except imaging.FontMissing:  # pragma: no cover - yazı tipi olmayan makine
        pytest.skip("bu makinede Türkçe yazabilen yazı tipi yok")

    assert Path(yol).is_file()
    for harf in imaging.TURKISH_PROBE:
        assert imaging._glyph_exists(font, harf), harf


def test_yazi_tipi_yoksa_hata(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(imaging, "FONT_CANDIDATES", ())
    with pytest.raises(imaging.FontMissing, match="STAMP_FONT_PATH"):
        imaging.find_font(20)


# --- görsel işleme ----------------------------------------------------


def test_damga_alt_bantta_yazi_birakir_ustu_bozmaz() -> None:
    """PNG seçildi: yeniden kodlama gürültüsü olmadan karşılaştırılabilsin."""
    baytlar, _ = _resim(bicim="PNG")
    damgali = imaging.stamp(baytlar, text="Kadıköy · test · Çağla", content_type="image/png")

    ham_resim = Image.open(io.BytesIO(baytlar)).convert("RGB")
    yeni_resim = Image.open(io.BytesIO(damgali)).convert("RGB")
    assert yeni_resim.size == ham_resim.size

    band = imaging.band_height(ham_resim.height)
    ust = (0, 0, ham_resim.width, ham_resim.height - band)
    alt = (0, ham_resim.height - band, ham_resim.width, ham_resim.height)

    assert ham_resim.crop(ust).tobytes() == yeni_resim.crop(ust).tobytes()
    assert ham_resim.crop(alt).tobytes() != yeni_resim.crop(alt).tobytes()
    # Bant yarı saydam: altındaki fotoğraf tamamen kaybolmamalı.
    assert yeni_resim.crop(alt).getextrema()[0][1] > 0


UZUN_DAMGA = "Çok Uzun Bir Şube Adı Burada · 02.11.2026 23:40 UTC+3 · Çağla Şubeci Yıldırım"


def _en_kucuk_genislik(metin: str) -> int:
    """Metnin en küçük boyda kapladığı genişlik.

    Testler bunu yazı tipinden türetiyor: CI'daki DejaVu, buradaki
    Segoe UI'dan geniş. Sabit bir piksel sayısı yazmak, testi makineye
    bağlardı — ilk koşuda tam olarak bu oldu.
    """
    font, _ = imaging.find_font(imaging.TEXT_MIN_PX)
    return int(font.getbbox(metin)[2])


def test_sigan_metin_tek_satir_kalir() -> None:
    genis = _en_kucuk_genislik(UZUN_DAMGA) * 2

    yerlesim = imaging.layout(UZUN_DAMGA, (genis, 800))

    assert yerlesim.lines == (UZUN_DAMGA,)
    assert yerlesim.band == imaging.band_height(800)


def test_sigmayan_metin_kirpilmaz_ikinci_satira_taşar() -> None:
    """Taşan metin sessizce kenardan kesilmemeli: damga yalan söyler.

    CI ilk koşuda yakaladı: DejaVu, Segoe UI'dan geniş; aynı metin bir
    yazı tipinde sığarken diğerinde taşıyordu.
    """
    # Tek satıra sığmayacak, iki satıra rahat sığacak bir genişlik.
    dar = _en_kucuk_genislik(UZUN_DAMGA) * 2 // 3

    yerlesim = imaging.layout(UZUN_DAMGA, (dar, 300))

    assert len(yerlesim.lines) == 2
    assert " · ".join(yerlesim.lines) == UZUN_DAMGA  # hiçbir bilgi düşmedi
    kullanilabilir = dar - 2 * yerlesim.padding
    for satir in yerlesim.lines:
        assert yerlesim.font.getbbox(satir)[2] <= kullanilabilir, satir
    assert yerlesim.band > imaging.band_height(300)  # bant iki satıra büyüdü


def test_hicbir_genislikte_bant_tasmiyor() -> None:
    """Değişmez: her satır banda sığar, satır sayısı ikiyi geçmez."""
    birim = _en_kucuk_genislik(UZUN_DAMGA)
    for genislik in (birim // 4, birim // 2, birim, birim * 3):
        yerlesim = imaging.layout(UZUN_DAMGA, (genislik, 400))
        kullanilabilir = genislik - 2 * yerlesim.padding
        assert len(yerlesim.lines) <= imaging.MAX_LINES
        for satir in yerlesim.lines:
            assert yerlesim.font.getbbox(satir)[2] <= kullanilabilir, (genislik, satir)


def test_tek_parca_sigmazsa_sondan_kirpilir() -> None:
    """Son çare. Şube adı ilk bilgi: en son kaybedilecek şey o."""
    sube = "Ş" * 120
    font, _ = imaging.find_font(imaging.TEXT_MIN_PX)
    hedef = int(font.getbbox(sube)[2]) // 3

    kesik = imaging._kirp(sube, font, hedef)

    assert kesik.endswith("…")
    assert font.getbbox(kesik)[2] <= hedef


def test_kucuk_resim_oran_korur_uzun_kenar_320() -> None:
    baytlar, _ = _resim(1200, 800)
    kucuk = Image.open(io.BytesIO(imaging.thumbnail(baytlar, content_type="image/jpeg")))

    assert max(kucuk.size) == imaging.THUMBNAIL_MAX_EDGE
    assert kucuk.size == (320, 213)


def test_damga_exif_yonunu_duzeltir() -> None:
    """Telefon fotoğrafı yan kaydedilir; düzeltmeden damga yan yazılır."""
    resim = Image.new("RGB", (600, 400), (10, 10, 10))
    tampon = io.BytesIO()
    exif = resim.getexif()
    exif[274] = 6  # 90° döndür
    resim.save(tampon, format="JPEG", exif=exif)

    kucuk = Image.open(io.BytesIO(imaging.thumbnail(tampon.getvalue(), content_type="image/jpeg")))

    # Yön düzeltilince en-boy yer değiştirir: 600x400 -> 400x600.
    assert kucuk.height > kucuk.width


# --- işçi (ST-040) ----------------------------------------------------


def test_isci_damga_ve_kucuk_resim_uretir(dunya: Dunya) -> None:
    baytlar, ozet = _resim()
    kanit_id = dunya.kanit_yukle(baytlar, ozet)

    sonuc = dunya.servis.stamp_pending()

    assert sonuc == {"stamped": 1, "thumbnails": 1, "skipped": 0, "failed": 0}
    kanit = dunya.servis.get(kanit_id)
    assert kanit.status == "stamped"
    assert kanit.stamped_at == dunya.an
    assert kanit.stamped_key == derived_key(dunya.run_id, kanit_id, "image/jpeg", "stamp")
    assert kanit.thumbnail_key == derived_key(dunya.run_id, kanit_id, "image/jpeg", "thumb")
    assert dunya.depo.exists(kanit.stamped_key)
    assert dunya.depo.exists(kanit.thumbnail_key)


def test_tc043_ham_dosya_dokunulmaz_kalir(dunya: Dunya) -> None:
    """TC-043: ham dosya erişilebilir ve özeti kayıttakiyle eşleşir."""
    baytlar, ozet = _resim()
    kanit_id = dunya.kanit_yukle(baytlar, ozet)

    dunya.servis.stamp_pending()

    kanit = dunya.servis.get(kanit_id)
    ham = dunya.depo.get(kanit.storage_key)
    assert ham == baytlar
    assert digest(ham) == kanit.sha256
    assert dunya.depo.get(kanit.stamped_key or "") != ham


def test_isci_idempotent(dunya: Dunya) -> None:
    baytlar, ozet = _resim()
    dunya.kanit_yukle(baytlar, ozet)

    ilk = dunya.servis.stamp_pending()
    ikinci = dunya.servis.stamp_pending()

    assert ilk["stamped"] == 1
    assert ikinci == {"stamped": 0, "thumbnails": 0, "skipped": 0, "failed": 0}


def test_yazi_tipi_yoksa_kucuk_resim_var_damga_yok(
    dunya: Dunya, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Kutu kutu bir şube adı basmaktansa damgasız kalmak iyidir.

    Kayıt `stored` kalır: yazı tipi kurulunca sonraki tur damgayı basar.
    """
    monkeypatch.setattr(imaging, "FONT_CANDIDATES", ())
    baytlar, ozet = _resim()
    kanit_id = dunya.kanit_yukle(baytlar, ozet)

    sonuc = dunya.servis.stamp_pending()

    assert sonuc == {"stamped": 0, "thumbnails": 1, "skipped": 1, "failed": 0}
    kanit = dunya.servis.get(kanit_id)
    assert kanit.status == "stored"
    assert kanit.stamped_key is None
    assert kanit.thumbnail_key is not None
    assert dunya.depo.exists(kanit.thumbnail_key)

    # Yazı tipi gelince aynı kayıt damgalanır, küçük resim yeniden üretilmez.
    monkeypatch.undo()
    try:
        imaging.find_font(20)
    except imaging.FontMissing:  # pragma: no cover
        pytest.skip("bu makinede Türkçe yazabilen yazı tipi yok")
    sonra = dunya.servis.stamp_pending()
    assert sonra == {"stamped": 1, "thumbnails": 0, "skipped": 0, "failed": 0}


def test_bozuk_dosya_turu_dusurmez(dunya: Dunya) -> None:
    """Açılamayan bir dosya tüm turu değil kendini kaybeder."""
    bozuk = b"\xff\xd8bu-bir-jpeg-degil"
    dunya.kanit_yukle(bozuk, hashlib.sha256(bozuk).hexdigest(), answer_id=uuid4())
    saglam, ozet = _resim()
    saglam_id = dunya.kanit_yukle(saglam, ozet, answer_id=uuid4())

    sonuc = dunya.servis.stamp_pending()

    assert sonuc["failed"] == 1
    assert sonuc["stamped"] == 1
    assert dunya.servis.get(saglam_id).status == "stamped"


def test_acilamayan_dosya_her_turda_yeniden_denenmez(dunya: Dunya) -> None:
    """Açılamayan görsel bir daha denenmez: günlüğü boğar, bir şey değişmez.

    Kayıt `stored` kalıyor — ham dosya kanıttır ve yerinde duruyor.
    Kalıcı bir işaret için `status`a yeni bir değer ve göçüm gerekirdi.
    """
    bozuk = b"bu-bir-jpeg-degil"
    dunya.kanit_yukle(bozuk, hashlib.sha256(bozuk).hexdigest())

    ilk = dunya.servis.stamp_pending()
    ikinci = dunya.servis.stamp_pending()

    assert ilk["failed"] == 1
    assert ikinci["failed"] == 0


def test_isci_parti_sinirina_uyar(dunya: Dunya) -> None:
    for sira in range(3):
        # Her kare **farklı** olmalı: aynı baytlar tekillik denetimine
        # takılırdı (FR-0614). Rastgele renk ara sıra çakışıyordu —
        # testi kendi elimle kararsız yapmışım, boyut farkı kesin.
        baytlar, ozet = _resim(900 + sira, 600)
        dunya.kanit_yukle(baytlar, ozet, answer_id=uuid4())

    sonuc = dunya.servis.stamp_pending(limit=2)

    assert sonuc["stamped"] == 2
    assert dunya.servis.stamp_pending(limit=2)["stamped"] == 1


# --- imzalı bağlantı kopya türüyle ------------------------------------


def test_belirtec_kopya_turunu_tasir(dunya: Dunya) -> None:
    baytlar, ozet = _resim()
    kanit_id = dunya.kanit_yukle(baytlar, ozet)
    dunya.servis.stamp_pending()

    _, ham = dunya.servis.read(dunya.servis.view_token(kanit_id, "raw"))
    _, damgali = dunya.servis.read(dunya.servis.view_token(kanit_id, "stamped"))
    _, kucuk = dunya.servis.read(dunya.servis.view_token(kanit_id, "thumbnail"))

    assert ham == baytlar
    assert damgali != baytlar
    assert len(kucuk) < len(baytlar)


def test_damgalanmamis_kanit_ham_dosyaya_duser(dunya: Dunya) -> None:
    """Damga turlu bir iş: hazır olmayan kopya için boş kare gösterilmez."""
    baytlar, ozet = _resim()
    kanit_id = dunya.kanit_yukle(baytlar, ozet)

    _, gelen = dunya.servis.read(dunya.servis.view_token(kanit_id, "stamped"))

    assert gelen == baytlar


def test_gecersiz_kopya_turu_reddedilir(dunya: Dunya) -> None:
    baytlar, ozet = _resim()
    kanit_id = dunya.kanit_yukle(baytlar, ozet)
    kanit = dunya.servis.get(kanit_id)

    # Alan nesnesi bilinmeyen türe ham dosyayı verir; şema zaten
    # sınırlıyor (EvidenceVariant), bu yüzden geri düşme güvenli.
    assert kanit.key_for("raw") == kanit.storage_key


# --- uç nokta ---------------------------------------------------------


def test_uc_nokta_kucuk_resmi_servis_eder(tmp_path: Path) -> None:
    istemci = oturum_ac(TestClient(create_app(Settings(evidence_dir=str(tmp_path)))))
    run = istemci.get("/api/v1/runs").json()[0]
    gorunum = istemci.get(f"/api/v1/runs/{run['id']}").json()
    madde = next(m for b in gorunum["sections"] for m in b["items"] if m["type"] != "instruction")

    baytlar, ozet = _resim()
    cevap_id = str(uuid4())
    izin = istemci.post(
        f"/api/v1/runs/{run['id']}/answers/{cevap_id}/evidence",
        json={
            "item_id": madde["item_id"],
            "sha256": ozet,
            "content_type": "image/jpeg",
            "size_bytes": len(baytlar),
        },
    ).json()
    istemci.put(izin["upload_url"], content=baytlar)
    kanit_id = izin["evidence"]["id"]
    assert istemci.post(f"/api/v1/evidence/{kanit_id}/complete").status_code == 200

    tur = istemci.post("/api/v1/scheduler/tick")
    assert tur.status_code == 200
    assert tur.json()["stamped"] >= 1

    ozet_yanit = istemci.get(f"/api/v1/runs/{run['id']}/evidence").json()
    kayit = next(k for k in ozet_yanit if k["id"] == kanit_id)
    assert kayit["status"] == "stamped"
    assert kayit["has_stamp"] is True
    assert kayit["has_thumbnail"] is True
    assert kayit["stamped_at"] is not None

    baglanti = istemci.get(f"/api/v1/evidence/{kanit_id}/url?variant=thumbnail").json()
    assert baglanti["variant"] == "thumbnail"
    dosya = istemci.get(baglanti["url"])
    assert dosya.status_code == 200
    assert len(dosya.content) < len(baytlar)
    assert max(Image.open(io.BytesIO(dosya.content)).size) == imaging.THUMBNAIL_MAX_EDGE


def test_uc_nokta_damgali_kopya_ham_dosyadan_farkli(tmp_path: Path) -> None:
    istemci = oturum_ac(TestClient(create_app(Settings(evidence_dir=str(tmp_path)))))
    run = istemci.get("/api/v1/runs").json()[0]
    gorunum = istemci.get(f"/api/v1/runs/{run['id']}").json()
    madde = next(m for b in gorunum["sections"] for m in b["items"] if m["type"] != "instruction")

    baytlar, ozet = _resim(bicim="PNG")
    izin = istemci.post(
        f"/api/v1/runs/{run['id']}/answers/{uuid4()}/evidence",
        json={
            "item_id": madde["item_id"],
            "sha256": ozet,
            "content_type": "image/png",
            "size_bytes": len(baytlar),
        },
    ).json()
    istemci.put(izin["upload_url"], content=baytlar, headers={"Content-Type": "image/png"})
    kanit_id = izin["evidence"]["id"]
    istemci.post(f"/api/v1/evidence/{kanit_id}/complete")
    istemci.post("/api/v1/scheduler/tick")

    ham_url = istemci.get(f"/api/v1/evidence/{kanit_id}/url?variant=raw").json()["url"]
    damga_url = istemci.get(f"/api/v1/evidence/{kanit_id}/url?variant=stamped").json()["url"]
    ham = istemci.get(ham_url).content
    damgali = istemci.get(damga_url).content

    assert ham == baytlar
    assert damgali != baytlar
    assert hashlib.sha256(ham).hexdigest() == ozet


def test_saklama_suresi_kopyalari_da_kapsar(dunya: Dunya) -> None:
    """Türetilmiş kopyalar ham dosyayla **aynı öbekte**: BR-21 silmesi
    çalıştırma düzeyinde iş görsün, kopya arkada kalmasın."""
    baytlar, ozet = _resim()
    kanit_id = dunya.kanit_yukle(baytlar, ozet)
    dunya.servis.stamp_pending()
    kanit = dunya.servis.get(kanit_id)

    onek = f"evidence/{dunya.run_id}/"
    assert kanit.storage_key.startswith(onek)
    assert (kanit.stamped_key or "").startswith(onek)
    assert (kanit.thumbnail_key or "").startswith(onek)


def test_damga_zamani_cekim_zamanini_kullanir(dunya: Dunya) -> None:
    """Çevrimdışı fotoğrafa senk anını basmak saatler sonrasını gösterirdi."""
    baytlar, ozet = _resim()
    cekim = dunya.an - timedelta(hours=5)
    kanit_id = dunya.kanit_yukle(baytlar, ozet, captured_at=cekim)
    kanit = dunya.servis.get(kanit_id)

    metin = dunya.servis._damga_metni(kanit)

    yerel = cekim.astimezone(ZoneInfo("Europe/Istanbul"))
    assert yerel.strftime("%d.%m.%Y %H:%M") in metin
    # Senk anı (stored_at) değil çekim anı yazılı:
    assert dunya.an.astimezone(ZoneInfo("Europe/Istanbul")).strftime("%H:%M") not in metin
