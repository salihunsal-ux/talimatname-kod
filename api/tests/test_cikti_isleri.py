"""Arka planda çıktı üretimi (ST-102; FR-1217).

Sınanan şey: **eşiği geçen rapor istek içinde üretilmiyor**, iş kaydına
dönüyor, zamanlayıcı turunda üretiliyor ve yalnızca isteyen indiriyor.

Eşik testlerde küçültülüyor (tohumda binlerce çalıştırma yok); ölçülen
şey sayının kendisi değil, sayıyı geçince ne olduğu.
"""

from __future__ import annotations

import io
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfReader

from conftest import TELEFON, oturum_ac
from talimatname.api import bagimliliklar
from talimatname.api.app import create_app
from talimatname.domain.exports import (
    MAX_ATTEMPTS,
    ExportJob,
    file_name,
    pending,
)
from talimatname.domain.validation import ValidationError
from talimatname.services.export_jobs import JobNotFound, JobNotReady
from talimatname.settings import Settings

AN = datetime(2026, 11, 1, 9, 0, tzinfo=UTC)


def _is(**ek: object) -> ExportJob:
    temel = {
        "id": uuid4(),
        "kind": "aylik-ozet",
        "params": {"year": "2026", "month": "11"},
        "requested_by": uuid4(),
        "requested_at": AN,
        "run_count": 800,
    }
    return ExportJob(**{**temel, **ek})  # type: ignore[arg-type]


# --- alan katmanı -------------------------------------------------------


def test_dosya_adi_donemi_tasiyor() -> None:
    aylik = _is(params={"year": "2026", "month": "9"})
    olcum = _is(
        kind="olcum-gunlugu",
        params={"first_day": "2026-10-01", "last_day": "2026-10-31"},
    )

    assert file_name(aylik) == "talimatname-aylik-ozet-2026-09.pdf"
    assert file_name(olcum) == "talimatname-olcum-gunlugu-20261001-20261031.pdf"


def test_eksik_parametre_kuyruga_girmiyor() -> None:
    """Kuyruğa giren iş üretim anında çözülebilmeli."""
    with pytest.raises(ValidationError):
        _is(params={"year": "2026"}).validated()


def test_dusen_is_once_yeniden_deneniyor_sonra_pes_ediliyor() -> None:
    """Geçici hata bir sonraki turda düzelebilir; üçüncüde düzelmiyorsa
    "hazırlanıyor" yazısıyla oyalamak yanlış olur."""
    is_kaydi = _is()

    for _ in range(MAX_ATTEMPTS - 1):
        is_kaydi = is_kaydi.claimed(AN).broken(AN, code="Timeout")
        assert is_kaydi.state == "queued"

    is_kaydi = is_kaydi.claimed(AN).broken(AN, code="Timeout")
    assert (is_kaydi.state, is_kaydi.error_code) == ("failed", "Timeout")
    assert not pending(is_kaydi)


def test_hazir_dosyanin_suresi_doluyor() -> None:
    hazir = _is().claimed(AN).completed(AN, key="exports/x.pdf", size=10, code="AAAA-BBBB-CCCC")

    assert not hazir.expired(AN + timedelta(days=6))
    assert hazir.expired(AN + timedelta(days=8))
    # Süpürülen kayıt duruyor ama indirilemiyor: "vardı, süresi doldu".
    assert not hazir.swept().downloadable
    assert hazir.swept().document_code == "AAAA-BBBB-CCCC"


# --- uç nokta ve işçi ---------------------------------------------------


@pytest.fixture
def istemci(tmp_path: Path) -> TestClient:
    return TestClient(create_app(Settings(evidence_dir=str(tmp_path))))


@pytest.fixture
def kucuk_esik(tmp_path: Path) -> TestClient:
    """Eşiği 1'e indirilmiş uygulama: tohumda binlerce çalıştırma yok.

    Ayarla indiriliyor, yamayla değil: eşik zaten yapılandırılabilir
    (kapasite kararı), testin de ürünün gerçek kolunu kullanması iyi.
    """
    return TestClient(
        create_app(Settings(evidence_dir=str(tmp_path), export_background_threshold=1))
    )


def _pdf_metni(baytlar: bytes) -> str:
    return "\n".join(s.extract_text() or "" for s in PdfReader(io.BytesIO(baytlar)).pages)


def test_esik_altinda_pdf_dogrudan_geliyor(istemci: TestClient) -> None:
    """Küçük rapor hâlâ senkron: her isteği kuyruğa atmak gereksiz bekletme."""
    oturum_ac(istemci)
    bugun = datetime.now(UTC).date()

    yanit = istemci.get(
        "/api/v1/reports/monthly.pdf", params={"year": bugun.year, "month": bugun.month}
    )

    assert yanit.status_code == 200
    assert yanit.headers["content-type"] == "application/pdf"


def test_esigi_gecen_cikti_202_ile_kuyruga_giriyor(kucuk_esik: TestClient) -> None:
    istemci = oturum_ac(kucuk_esik)
    bugun = datetime.now(UTC).date()

    yanit = istemci.get(
        "/api/v1/reports/monthly.pdf", params={"year": bugun.year, "month": bugun.month}
    )

    assert yanit.status_code == 202
    govde = yanit.json()
    assert govde["state"] == "queued"
    assert govde["kind"] == "aylik-ozet"
    assert govde["run_count"] >= 1
    assert govde["downloadable"] is False


def test_ayni_istek_ikinci_kez_is_acmiyor(kucuk_esik: TestClient) -> None:
    """Düğmeye iki kez basmak en pahalı işi iki kez yaptırmamalı."""
    istemci = oturum_ac(kucuk_esik)
    bugun = datetime.now(UTC).date()
    sorgu = {"year": bugun.year, "month": bugun.month}

    bir = istemci.get("/api/v1/reports/monthly.pdf", params=sorgu).json()
    iki = istemci.get("/api/v1/reports/monthly.pdf", params=sorgu).json()

    assert bir["id"] == iki["id"]
    assert len(istemci.get("/api/v1/reports/exports").json()) == 1


def test_zamanlayici_turu_ciktiyi_uretiyor(kucuk_esik: TestClient) -> None:
    """Uçtan uca: istek → kuyruk → tur → indirilebilir PDF."""
    istemci = oturum_ac(kucuk_esik)
    bugun = datetime.now(UTC).date()
    is_kaydi = istemci.get(
        "/api/v1/reports/monthly.pdf", params={"year": bugun.year, "month": bugun.month}
    ).json()

    tur = istemci.post("/api/v1/scheduler/tick").json()

    assert tur["exports_done"] == 1
    durum = istemci.get(f"/api/v1/reports/exports/{is_kaydi['id']}").json()
    assert durum["state"] == "ready"
    assert durum["downloadable"] is True
    assert durum["size_bytes"] > 0

    dosya = istemci.get(f"/api/v1/reports/exports/{is_kaydi['id']}/dosya")
    assert dosya.status_code == 200
    assert dosya.headers["content-type"] == "application/pdf"
    assert "aylık özet" in _pdf_metni(dosya.content)


def test_arka_plandaki_kagidin_kodu_da_zincire_bagli(kucuk_esik: TestClient) -> None:
    """FR-1218 arka planda da geçerli: kod doğrulama sayfasından sorulabiliyor.

    Olayın aktörü **isteyen kişi**: kâğıdı o istedi, işçi yalnızca üretti.
    """
    istemci = oturum_ac(kucuk_esik)
    bugun = datetime.now(UTC).date()
    is_kaydi = istemci.get(
        "/api/v1/reports/monthly.pdf", params={"year": bugun.year, "month": bugun.month}
    ).json()
    istemci.post("/api/v1/scheduler/tick")

    durum = istemci.get(f"/api/v1/reports/exports/{is_kaydi['id']}").json()
    kod = durum["document_code"]
    assert kod, "arka planda üretilen kâğıt kodsuz kalmamalı"

    dogrulama = TestClient(kucuk_esik.app).get(f"/api/v1/verify/{kod}")

    assert dogrulama.status_code == 200, dogrulama.text
    assert dogrulama.json()["document"] == "aylik-ozet"
    assert dogrulama.json()["record_intact"] is True
    # Kâğıtta da aynı kod yazıyor.
    dosya = istemci.get(f"/api/v1/reports/exports/{is_kaydi['id']}/dosya")
    assert f"Belge kodu: {kod}" in _pdf_metni(dosya.content)


def test_hazir_olunca_bildirim_dusuyor(kucuk_esik: TestClient) -> None:
    """FR-1217: hazır olunca bildirim. Sürücü yoksa "gönderildi" yazmıyoruz."""
    istemci = oturum_ac(kucuk_esik)
    bugun = datetime.now(UTC).date()
    istemci.get("/api/v1/reports/monthly.pdf", params={"year": bugun.year, "month": bugun.month})

    istemci.post("/api/v1/scheduler/tick")

    bildirimler = istemci.get("/api/v1/notifications").json()
    hazir = [b for b in bildirimler if b["kind"] == "export_ready"]
    assert len(hazir) == 1
    assert "hazır" in hazir[0]["title"]


def test_baskasinin_ciktisi_gorunmuyor(kucuk_esik: TestClient) -> None:
    """Çıktı isteyenin kapsamıyla üretildi; başkasına vermek kapsamı delmek olurdu."""
    istemci = oturum_ac(kucuk_esik, "admin")
    bugun = datetime.now(UTC).date()
    is_kaydi = istemci.get(
        "/api/v1/reports/monthly.pdf", params={"year": bugun.year, "month": bugun.month}
    ).json()
    istemci.post("/api/v1/scheduler/tick")

    baskasi = oturum_ac(TestClient(kucuk_esik.app), "branch_manager")

    assert baskasi.get("/api/v1/reports/exports").json() == []
    assert baskasi.get(f"/api/v1/reports/exports/{is_kaydi['id']}").status_code == 404
    assert baskasi.get(f"/api/v1/reports/exports/{is_kaydi['id']}/dosya").status_code == 404


def test_hazir_olmayan_cikti_indirilemez(kucuk_esik: TestClient) -> None:
    istemci = oturum_ac(kucuk_esik)
    bugun = datetime.now(UTC).date()
    is_kaydi = istemci.get(
        "/api/v1/reports/monthly.pdf", params={"year": bugun.year, "month": bugun.month}
    ).json()

    yanit = istemci.get(f"/api/v1/reports/exports/{is_kaydi['id']}/dosya")

    assert yanit.status_code == 409
    assert yanit.json()["type"] == "urn:talimatname:cikti-hazir-degil"


def test_cikti_oturumsuz_indirilemez(istemci: TestClient) -> None:
    yanit = istemci.get(f"/api/v1/reports/exports/{uuid4()}/dosya")

    assert yanit.status_code == 403


def test_dusen_is_sebebini_sakliyor(
    kucuk_esik: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Hata gizlenmiyor: kullanıcı neden gelmediğini görsün."""
    istemci = oturum_ac(kucuk_esik)
    bugun = datetime.now(UTC).date()
    is_kaydi = istemci.get(
        "/api/v1/reports/monthly.pdf", params={"year": bugun.year, "month": bugun.month}
    ).json()

    servis = bagimliliklar.rapor_servisi()
    monkeypatch.setattr(
        bagimliliklar,
        "rapor_servisi",
        lambda: _patlayan(servis),
    )
    tur = istemci.post("/api/v1/scheduler/tick").json()

    assert tur["exports_failed"] == 1
    durum = istemci.get(f"/api/v1/reports/exports/{is_kaydi['id']}").json()
    assert durum["state"] == "queued"  # denemesi kaldı
    assert durum["error_code"] == "RuntimeError"


def _patlayan(servis: object) -> object:
    class Patlayan:
        def __getattr__(self, ad: str) -> object:
            def _patla(*a: object, **k: object) -> object:
                raise RuntimeError("deneme")

            return _patla

    return Patlayan()


def test_suresi_dolan_dosya_supuruluyor_kayit_kaliyor(
    kucuk_esik: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Üretilmiş rapor iş verisi taşır; sonsuza kadar saklamıyoruz.

    Kayıt kalıyor: "vardı ama süresi doldu" demek, "hiç olmadı"
    demekten dürüsttür.
    """
    istemci = oturum_ac(kucuk_esik)
    bugun = datetime.now(UTC).date()
    is_kaydi = istemci.get(
        "/api/v1/reports/monthly.pdf", params={"year": bugun.year, "month": bugun.month}
    ).json()
    istemci.post("/api/v1/scheduler/tick")

    # Saati sekiz gün ileri alıp turu tekrar koşuyoruz.
    servis = bagimliliklar.cikti_servisi()
    monkeypatch.setattr(servis, "_now", lambda: datetime.now(UTC) + timedelta(days=8))
    assert servis.sweep_files() == 1

    durum = istemci.get(f"/api/v1/reports/exports/{is_kaydi['id']}").json()
    assert durum["state"] == "ready"
    assert durum["downloadable"] is False
    dosya = istemci.get(f"/api/v1/reports/exports/{is_kaydi['id']}/dosya")
    assert dosya.status_code == 404
    assert dosya.json()["type"] == "urn:talimatname:cikti-suresi-doldu"


def test_servis_kapsami_isteyenden_okuyor(kucuk_esik: TestClient) -> None:
    """Şube müdürünün arka plan raporu da yalnızca kendi şubesini kapsıyor.

    Kapsam işte dondurulmuyor, üretim anında rolden okunuyor — ve
    hesabı yapan fonksiyon uç noktanınkiyle aynı.
    """
    mudur = oturum_ac(kucuk_esik, "branch_manager")
    bugun = datetime.now(UTC).date()
    mudur.get("/api/v1/reports/monthly.pdf", params={"year": bugun.year, "month": bugun.month})
    # Tur yönetici işi; çıktıyı üreten yine müdürün kapsamı olmalı.
    oturum_ac(TestClient(kucuk_esik.app), "admin").post("/api/v1/scheduler/tick")

    is_kaydi = mudur.get("/api/v1/reports/exports").json()[0]
    dosya = mudur.get(f"/api/v1/reports/exports/{is_kaydi['id']}/dosya")
    metin = _pdf_metni(dosya.content)

    # Kadıköy müdürünün kâğıdında başka şube yok.
    assert "KDK" in metin
    assert "USK" not in metin


def test_cikti_servisi_dogrudan_hatalari(tmp_path: Path) -> None:
    """Servis hataları HTTP'den bağımsız: port yüzeyi de sınanıyor."""
    create_app(Settings(evidence_dir=str(tmp_path)))
    servis = bagimliliklar.cikti_servisi()
    kullanici = bagimliliklar._kullanici_deposu().user_by_phone(TELEFON["admin"])
    assert kullanici is not None

    with pytest.raises(JobNotFound):
        servis.job_for(kullanici.id, uuid4())

    is_kaydi = servis.queue(
        kullanici.id, kind="aylik-ozet", params={"year": "2026", "month": "11"}, run_count=900
    )
    with pytest.raises(JobNotReady):
        servis.file(kullanici.id, is_kaydi.id)
    with pytest.raises(JobNotFound):
        servis.file(uuid4(), is_kaydi.id)
