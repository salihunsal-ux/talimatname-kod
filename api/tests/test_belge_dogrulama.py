"""Belge doğrulama: kâğıttaki koddan kayda (ST-101; FR-1218).

Sınanan şey tek cümleyle: **kâğıtta basılan kod, oturumsuz bir uç
noktadan sorulduğunda o raporun kaydını buluyor** — ve bulamadığında,
ya da kayda dokunulduğunda bunu söylüyor.

Testlerin çoğu kodu PDF metninden okuyor, olaydan değil: doğrulamanın
tersine çevirdiği şey **basılan** kod. Olaydan okumak, yazdırma ile
arama arasındaki bir ayrışmayı göremezdi.
"""

from __future__ import annotations

import io
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfReader

from conftest import oturum_ac
from talimatname.api import bagimliliklar
from talimatname.api.app import create_app
from talimatname.api.routers import dogrulama
from talimatname.domain.audit import (
    GENESIS,
    AuditEvent,
    format_code,
    parse_code,
    record_intact,
    sealed,
)
from talimatname.domain.validation import ValidationError
from talimatname.infra.memory import MemoryAuditRepository
from talimatname.services.audit import AuditService, tampered
from talimatname.services.verification import (
    AmbiguousCode,
    DocumentNotFound,
    VerificationService,
)
from talimatname.settings import Settings

AN = datetime(2026, 11, 1, 8, 30, tzinfo=UTC)


@pytest.fixture(autouse=True)
def sinir_sifir() -> None:
    """Hız sınırı modül düzeyinde yaşıyor: testler birbirini tüketmesin."""
    dogrulama.hiz_siniri.sifirla()


@pytest.fixture
def istemci(tmp_path: Path) -> TestClient:
    return TestClient(create_app(Settings(evidence_dir=str(tmp_path))))


# --- kodun biçimi (alan katmanı) ---------------------------------------


def test_kod_bicimi_ve_cozumu_birbirinin_tersi() -> None:
    ozet = "a1b2c3d4e5f6" + "0" * 52

    kod = format_code(ozet)

    assert kod == "A1B2-C3D4-E5F6"
    assert parse_code(kod) == "a1b2c3d4e5f6"


@pytest.mark.parametrize(
    "yazim",
    ["A1B2-C3D4-E5F6", "a1b2c3d4e5f6", " A1B2 C3D4 E5F6 ", "a1b2-C3D4-e5f6"],
)
def test_kod_elle_yazilmis_haliyle_okunuyor(yazim: str) -> None:
    """Denetçi kodu kâğıttan okuyup yazıyor: tire ve büyüklük serbest."""
    assert parse_code(yazim) == "a1b2c3d4e5f6"


@pytest.mark.parametrize("bozuk", ["", "A1B2-C3D4", "A1B2-C3D4-E5F6-7788", "A1B2-C3D4-E5GH"])
def test_bozuk_kod_dogrulama_hatasi_veriyor(bozuk: str) -> None:
    """ "Bulunamadı" demek, bozuk kodu kayıtsız sanmak olurdu."""
    with pytest.raises(ValidationError):
        parse_code(bozuk)


# --- servis -------------------------------------------------------------


def _depo_ve_servis() -> tuple[MemoryAuditRepository, VerificationService]:
    depo = MemoryAuditRepository()
    iz = AuditService(depo, now=lambda: AN)
    return depo, VerificationService(iz, timezone=lambda: "Europe/Istanbul")


def _rapor_olayi(iz: AuditService, **ozet: str) -> AuditEvent:
    olay = iz.record(
        "rapor.uretildi",
        object_type="rapor",
        after={"tur": "aylik-ozet", "icerik": "XXXX-YYYY-ZZZZ", **ozet},
    )
    assert olay is not None
    return olay


def test_kod_raporun_kaydini_buluyor() -> None:
    depo, servis = _depo_ve_servis()
    iz = AuditService(depo, now=lambda: AN)
    olay = _rapor_olayi(iz, donem="2026-10")

    sonuc = servis.check(format_code(olay.hash))

    assert sonuc.document == "aylik-ozet"
    assert sonuc.document_label == "Aylık özet raporu"
    assert sonuc.period == "2026-10"
    assert (sonuc.issued_at, sonuc.timezone) == (AN, "Europe/Istanbul")
    assert sonuc.trustworthy


def test_bilinmeyen_kod_bulunamadi() -> None:
    _, servis = _depo_ve_servis()

    with pytest.raises(DocumentNotFound):
        servis.check("ABCD-EF12-3456")


def test_rapor_olmayan_kayit_belge_sayilmiyor() -> None:
    """Günlükteki her özet 12 basamakla başlıyor; belge olan yalnızca rapor.

    Oturum kaydını belge gibi göstermek, denetçiye "evet bu belge
    sistemde var" demek olurdu.
    """
    depo, servis = _depo_ve_servis()
    iz = AuditService(depo, now=lambda: AN)
    olay = iz.record("oturum.acildi", object_type="kullanici")
    assert olay is not None

    with pytest.raises(DocumentNotFound):
        servis.check(format_code(olay.hash))


def test_cakisan_onek_gizlenmiyor() -> None:
    """İki kayıt aynı önekte: "ilkini" göstermek yanlış kaydı göstermek olurdu."""
    depo, servis = _depo_ve_servis()
    iz = AuditService(depo, now=lambda: AN)
    bir = _rapor_olayi(iz)
    # Aynı önekli ikinci bir kayıt, elle: doğal yolla üretilemez.
    depo._events.append(tampered(bir, sequence=99, hash=bir.hash))

    with pytest.raises(AmbiguousCode):
        servis.check(format_code(bir.hash))


def test_kayda_dokunulmussa_ozet_tutmuyor() -> None:
    """FR-1304: değişiklik görünür. Sayfa "sağlam" demiyor."""
    depo, servis = _depo_ve_servis()
    iz = AuditService(depo, now=lambda: AN)
    olay = _rapor_olayi(iz, donem="2026-10")
    depo._events[0] = tampered(olay, after={**olay.after, "donem": "2026-09"})

    sonuc = servis.check(format_code(olay.hash))

    assert sonuc.period == "2026-09"  # kâğıtla tutmayacak
    assert not sonuc.record_intact
    assert not sonuc.trustworthy


def test_onceki_halka_tutmuyorsa_zincir_bagi_kirik() -> None:
    depo, servis = _depo_ve_servis()
    iz = AuditService(depo, now=lambda: AN)
    iz.record("oturum.acildi", object_type="kullanici")
    olay = _rapor_olayi(iz)
    depo._events[0] = tampered(depo._events[0], hash="f" * 64)

    sonuc = servis.check(format_code(olay.hash))

    assert sonuc.record_intact  # kaydın kendisine dokunulmadı
    assert not sonuc.chain_linked
    assert not sonuc.trustworthy


def test_zincirin_ilk_halkasi_bagsiz_sayilmiyor() -> None:
    """İlk kaydın öncesi yok: bu bir kırılma değil, zincirin başı."""
    depo, servis = _depo_ve_servis()
    iz = AuditService(depo, now=lambda: AN)
    olay = _rapor_olayi(iz)

    assert olay.prev_hash == GENESIS
    assert servis.check(format_code(olay.hash)).chain_linked


def test_kayit_butunlugu_hesaplaniyor() -> None:
    olay = sealed(
        AuditEvent(
            id=uuid4(),
            sequence=1,
            event_type="rapor.uretildi",
            at=AN,
            object_type="rapor",
        )
    )

    assert record_intact(olay)
    assert not record_intact(tampered(olay, object_type="calistirma"))


# --- uç nokta (oturumsuz) ----------------------------------------------


def _pdf_metni(baytlar: bytes) -> str:
    return "\n".join(s.extract_text() or "" for s in PdfReader(io.BytesIO(baytlar)).pages)


def _kagittaki_kod(metin: str) -> str:
    satir = next(s for s in metin.splitlines() if "Belge kodu:" in s)
    return satir.split("Belge kodu:")[1].strip().split()[0]


def _aylik_pdf(istemci: TestClient) -> str:
    bugun = datetime.now(UTC).date()
    yanit = oturum_ac(istemci).get(
        "/api/v1/reports/monthly.pdf", params={"year": bugun.year, "month": bugun.month}
    )
    assert yanit.status_code == 200, yanit.text
    return _kagittaki_kod(_pdf_metni(yanit.content))


def test_kagittaki_kod_oturumsuz_sorulabiliyor(istemci: TestClient) -> None:
    """Denetçi panele giremez: uç nokta belirteç **istemiyor**."""
    kod = _aylik_pdf(istemci)
    bugun = datetime.now(UTC).date()

    temiz = TestClient(istemci.app)  # belirteç yok
    yanit = temiz.get(f"/api/v1/verify/{kod}")

    assert yanit.status_code == 200, yanit.text
    govde = yanit.json()
    assert govde["code"] == kod
    assert govde["document"] == "aylik-ozet"
    assert govde["document_label"] == "Aylık özet raporu"
    assert govde["period"] == f"{bugun.year}-{bugun.month:02d}"
    assert (govde["record_intact"], govde["chain_linked"]) == (True, True)


def test_yanit_ic_veriyi_acmiyor(istemci: TestClient) -> None:
    """Kodu eline geçiren herkese puan, kişi ve IP açılmıyor (BR-21).

    Sayfanın işi kâğıdı doğrulamak; kâğıtta olmayan bir şeyi söylemek
    oturumsuz bir uç noktadan veri sızdırmak olurdu.
    """
    kod = _aylik_pdf(istemci)

    govde = TestClient(istemci.app).get(f"/api/v1/verify/{kod}").json()

    assert set(govde) == {
        "code",
        "document",
        "document_label",
        "issued_at",
        "timezone",
        "period",
        "branch_code",
        "record_intact",
        "chain_linked",
    }


def test_calistirma_kodu_sube_ve_is_gunu_tasiyor(istemci: TestClient) -> None:
    """Denetçi kâğıdın hangi şube ve güne ait olduğunu karşılaştırabilsin."""
    oturum_ac(istemci)
    kosular = istemci.get("/api/v1/runs").json()
    run = kosular[0]

    kagit = istemci.get(f"/api/v1/runs/{run['id']}/pdf")
    assert kagit.status_code == 200, kagit.text
    metin = _pdf_metni(kagit.content)
    kod = _kagittaki_kod(metin)

    govde = TestClient(istemci.app).get(f"/api/v1/verify/{kod}").json()

    assert govde["document"] == "calistirma"
    assert govde["period"] == run["business_day"]
    # Kâğıt şubeyi "Ad (KOD)" diye yazıyor: sayfadaki kod oradaki kod.
    tek_satir = metin.replace("\n", "")
    assert f"{run['branch_name']} ({govde['branch_code']})" in tek_satir


def test_bilinmeyen_kod_404_problem_donuyor(istemci: TestClient) -> None:
    yanit = istemci.get("/api/v1/verify/ABCD-EF12-3456")

    assert yanit.status_code == 404
    assert yanit.json()["type"] == "urn:talimatname:belge-bulunamadi"


def test_bozuk_kod_422_donuyor(istemci: TestClient) -> None:
    yanit = istemci.get("/api/v1/verify/ELMA")

    assert yanit.status_code == 422
    assert yanit.json()["type"] == "urn:talimatname:gecersiz-istek"


def test_hiz_siniri_asildiginda_429(istemci: TestClient) -> None:
    """Oturumsuz uç nokta sınırsız olamaz (bkz. api/hiz_siniri)."""
    baslik = {"X-Forwarded-For": "203.0.113.9"}
    for _ in range(dogrulama.DENEME_SINIRI):
        istemci.get("/api/v1/verify/ABCD-EF12-3456", headers=baslik)

    yanit = istemci.get("/api/v1/verify/ABCD-EF12-3456", headers=baslik)

    assert yanit.status_code == 429
    assert yanit.json()["type"] == "urn:talimatname:cok-fazla-deneme"
    # Başka bir istemci etkilenmiyor: sınır IP başına.
    baska = istemci.get(
        "/api/v1/verify/ABCD-EF12-3456", headers={"X-Forwarded-For": "203.0.113.10"}
    )
    assert baska.status_code == 404


def test_dogrulama_sorgusu_gunluge_yazilmiyor(istemci: TestClient) -> None:
    """Dışarıdan tetiklenen bir yazma, zinciri herkesin uzatabildiği şey yapardı.

    Üstelik ürünün müşterisi olmayan insanların IP'si denetim
    günlüğüne girerdi (BR-21).
    """
    kod = _aylik_pdf(istemci)
    iz = bagimliliklar.izi_servisi()
    once = len(iz._repo.events(limit=500))

    TestClient(istemci.app).get(f"/api/v1/verify/{kod}")

    assert len(iz._repo.events(limit=500)) == once


def test_pdf_dipnotu_adres_ayarliyken_tam_baglanti_yaziyor(tmp_path: Path) -> None:
    """Kâğıttaki adres ayardan geliyor; yoksa uydurulmuyor (FR-1218)."""
    ayar = Settings(evidence_dir=str(tmp_path), panel_url="https://panel.ornek.com/")
    istemci = oturum_ac(TestClient(create_app(ayar)))
    bugun = datetime.now(UTC).date()

    yanit = istemci.get(
        "/api/v1/reports/monthly.pdf", params={"year": bugun.year, "month": bugun.month}
    )

    metin = _pdf_metni(yanit.content).replace("\n", "")
    kod = _kagittaki_kod(_pdf_metni(yanit.content))
    assert f"https://panel.ornek.com/dogrula/{kod}" in metin


def test_pdf_dipnotu_adres_yoksa_sayfanin_adini_yaziyor(istemci: TestClient) -> None:
    oturum_ac(istemci)
    bugun = datetime.now(UTC).date()

    yanit = istemci.get(
        "/api/v1/reports/monthly.pdf", params={"year": bugun.year, "month": bugun.month}
    )

    metin = _pdf_metni(yanit.content).replace("\n", "")
    assert "Belge doğrula" in metin
    assert "https://" not in metin
