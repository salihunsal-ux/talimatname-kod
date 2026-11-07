"""Yenileme belirteci: döndürme, iptal ve cihaz listesi (FR-0203).

Oturum 30 dakikalık tek bir erişim belirteciydi; vardiya boyunca açık
kalması gereken saha listesi yarım saatte bir giriş istiyordu ve bir
oturumu iptal etmenin yolu yoktu
(`docs/04-gereksinimler/08-oturum-suresi-acigi.md`).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from conftest import TELEFON, oturum_ac
from talimatname.api import bagimliliklar
from talimatname.api.app import create_app
from talimatname.domain.sessions import TTL, digest, new_secret, open_session
from talimatname.domain.users import User
from talimatname.infra.memory import MemorySessionRepository, MemoryUserRepository
from talimatname.services.sessions import SessionInvalid, SessionService
from talimatname.settings import Settings

AN = datetime(2026, 11, 8, 9, 0, tzinfo=UTC)


def _servis(an: datetime = AN) -> tuple[SessionService, MemorySessionRepository]:
    depo = MemorySessionRepository()
    return SessionService(depo, now=lambda: an), depo


def _kullanici() -> User:
    kisi = MemoryUserRepository().user_by_phone(TELEFON["staff"])
    assert kisi is not None
    return kisi


# --- alan katmanı -----------------------------------------------------


def test_sir_depoda_durmuyor() -> None:
    """Veritabanını okuyan biri canlı oturumları ele geçirmemeli."""
    sir = new_secret()
    oturum = open_session(id=uuid4(), user_id=uuid4(), secret=sir, kind="web", now=AN)

    assert sir not in (oturum.token_digest, str(oturum))
    assert oturum.token_digest == digest(sir)


def test_omur_istemci_turune_gore() -> None:
    """Web 12 saat, mobil 30 gün (FR-0203)."""
    assert TTL["web"] == timedelta(hours=12)
    assert TTL["mobile"] == timedelta(days=30)


def test_suresi_dolan_oturum_kullanilamaz() -> None:
    oturum = open_session(id=uuid4(), user_id=uuid4(), secret=new_secret(), kind="web", now=AN)

    assert oturum.usable(AN + timedelta(hours=11))
    assert not oturum.usable(AN + timedelta(hours=13))


# --- döndürme ---------------------------------------------------------


def test_yenileme_eskisini_iptal_edip_yenisini_veriyor() -> None:
    servis, _ = _servis()
    _, ilk_sir = servis.open(_kullanici())

    ikinci, ikinci_sir = servis.rotate(ilk_sir)

    assert ikinci_sir != ilk_sir
    assert ikinci.usable(AN)
    with pytest.raises(SessionInvalid):
        servis.rotate(ilk_sir)


def test_tekrar_kullanim_butun_oturumlari_dusuruyor() -> None:
    """Çalınan belirteç ikinci kez sunulursa zincir düşer.

    Belirteç iki elde demektir ve hangisinin gerçek kullanıcı olduğu
    bilinemez; kullanıcıyı yeniden giriş yapmaya zorlamak, saldırganın
    elinde çalışır bir oturum bırakmaktan iyidir.
    """
    servis, _ = _servis()
    kisi = _kullanici()
    _, ilk_sir = servis.open(kisi)
    _, ikinci_sir = servis.rotate(ilk_sir)
    assert servis.active(kisi.id)

    with pytest.raises(SessionInvalid):
        servis.rotate(ilk_sir)  # çalınan eski belirteç

    assert servis.active(kisi.id) == []
    with pytest.raises(SessionInvalid):
        servis.rotate(ikinci_sir)  # gerçek kullanıcının belirteci de düştü


def test_taninmayan_belirtec_reddediliyor() -> None:
    servis, _ = _servis()

    with pytest.raises(SessionInvalid):
        servis.rotate(new_secret())


def test_suresi_dolmus_belirtec_yenilenemez() -> None:
    depo = MemorySessionRepository()
    sir = new_secret()
    depo.save_session(open_session(id=uuid4(), user_id=uuid4(), secret=sir, kind="web", now=AN))
    gec = SessionService(depo, now=lambda: AN + timedelta(hours=13))

    with pytest.raises(SessionInvalid):
        gec.rotate(sir)


# --- kapatma ----------------------------------------------------------


def test_cikis_oturumu_kapatiyor() -> None:
    servis, _ = _servis()
    kisi = _kullanici()
    _, sir = servis.open(kisi)

    servis.revoke(sir)

    assert servis.active(kisi.id) == []
    with pytest.raises(SessionInvalid):
        servis.rotate(sir)


def test_taninmayan_belirtecle_cikis_hata_vermiyor() -> None:
    """İstemci zaten belirteci atıyor; "çıkamadın" demek işe yaramaz."""
    servis, _ = _servis()

    assert servis.revoke(new_secret()) is None


def test_uzaktan_sonlandirma_baskasinin_oturumunu_kapatamaz() -> None:
    servis, _ = _servis()
    kisi = _kullanici()
    oturum, _sir = servis.open(kisi)

    with pytest.raises(SessionInvalid):
        servis.revoke_session(uuid4(), oturum.id)

    assert servis.active(kisi.id)


def test_uzaktan_sonlandirma_kendi_oturumunu_kapatiyor() -> None:
    servis, _ = _servis()
    kisi = _kullanici()
    oturum, _sir = servis.open(kisi)

    servis.revoke_session(kisi.id, oturum.id)

    assert servis.active(kisi.id) == []


# --- uç noktalar ------------------------------------------------------


@pytest.fixture
def istemci() -> TestClient:
    return TestClient(create_app(Settings(demo_show_otp_code=True)))


def _giris(istemci: TestClient, rol: str = "staff") -> dict[str, object]:
    telefon = TELEFON[rol]
    kod = istemci.post("/api/v1/auth/request-code", json={"phone": telefon}).json()["dev_code"]
    yanit = istemci.post("/api/v1/auth/verify", json={"phone": telefon, "code": kod})
    assert yanit.status_code == 200, yanit.text
    return yanit.json()  # type: ignore[no-any-return]


def test_uc_nokta_giris_yenileme_belirteci_veriyor(istemci: TestClient) -> None:
    govde = _giris(istemci)

    assert govde["refresh_token"]
    assert govde["refresh_expires_at"]
    assert govde["expires_in_minutes"] == Settings().access_token_minutes


def test_erisim_belirteci_varsayilani_on_bes_dakika() -> None:
    """Yenileme yazılmadan önce 30 dk idi: oturum onunla bitiyordu.

    Artık bu süre yalnızca **iptalin gecikmesi**: uzaktan kapatılan
    oturum en fazla bu kadar içeride kalır. Ortam değişkeni bunu
    değiştirebilir, varsayılan burada sabitleniyor (API taslağı).
    """
    assert Settings.model_fields["access_token_minutes"].default == 15


def test_uc_nokta_yenileme_yeni_erisim_belirteci_veriyor(istemci: TestClient) -> None:
    govde = _giris(istemci)

    yeni = istemci.post(
        "/api/v1/auth/refresh", json={"refresh_token": govde["refresh_token"]}
    ).json()

    # Erişim belirteci aynı saniyede üretilirse birebir aynı çıkar
    # (aynı `sub`, `iat`, `exp`): zararsız, çünkü taşıdığı iddia aynı.
    # Sınanan şey yenileme belirtecinin **değişmesi** ve yeni erişim
    # belirtecinin çalışması.
    assert yeni["refresh_token"] != govde["refresh_token"]
    # Yeni erişim belirteci gerçekten çalışıyor.
    ben = istemci.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {yeni['access_token']}"}
    )
    assert ben.status_code == 200


def test_uc_nokta_eski_yenileme_belirteci_reddediliyor(istemci: TestClient) -> None:
    govde = _giris(istemci)
    istemci.post("/api/v1/auth/refresh", json={"refresh_token": govde["refresh_token"]})

    tekrar = istemci.post("/api/v1/auth/refresh", json={"refresh_token": govde["refresh_token"]})

    assert tekrar.status_code == 403
    assert tekrar.json()["type"].endswith("oturum-gecersiz")


def test_uc_nokta_cikis_yenilemeyi_kapatiyor(istemci: TestClient) -> None:
    govde = _giris(istemci)

    cikis = istemci.post("/api/v1/auth/logout", json={"refresh_token": govde["refresh_token"]})

    assert cikis.status_code == 200
    sonra = istemci.post("/api/v1/auth/refresh", json={"refresh_token": govde["refresh_token"]})
    assert sonra.status_code == 403


def test_uc_nokta_oturum_listesi_kendi_cihazlarini_gosteriyor(istemci: TestClient) -> None:
    govde = _giris(istemci)

    liste = istemci.get(
        "/api/v1/auth/sessions",
        headers={"Authorization": f"Bearer {govde['access_token']}"},
    )

    assert liste.status_code == 200
    satirlar = liste.json()
    # Aynı kullanıcının başka testlerden kalan oturumları olabilir:
    # oturumlar kalıcı, listede birikiyorlar. Sınanan şey en yeninin
    # bu giriş olması ve satırın ne taşıdığı.
    assert satirlar
    assert satirlar[0]["kind"] == "web"
    assert satirlar[0]["device"]
    # Belirteç ya da özeti **dönmüyor**.
    assert "token_digest" not in satirlar[0]
    assert govde["refresh_token"] not in str(satirlar)


def test_uc_nokta_pasif_kullanici_yenileyemiyor(istemci: TestClient) -> None:
    """Yetki belirteçten değil kullanıcıdan okunuyor (FR-0205)."""
    govde = _giris(istemci)
    yonetici = oturum_ac(TestClient(create_app(Settings())), "admin")
    kisi_id = govde["user"]["id"]  # type: ignore[index]
    yonetici.post(f"/api/v1/users/{kisi_id}/deactivate")

    try:
        yanit = istemci.post("/api/v1/auth/refresh", json={"refresh_token": govde["refresh_token"]})
        assert yanit.status_code == 403
    finally:
        yonetici.post(f"/api/v1/users/{kisi_id}/activate")


def test_uc_nokta_uzaktan_sonlandirma(istemci: TestClient) -> None:
    govde = _giris(istemci)
    baslik = {"Authorization": f"Bearer {govde['access_token']}"}
    oturum_id = istemci.get("/api/v1/auth/sessions", headers=baslik).json()[0]["id"]

    kapat = istemci.post(f"/api/v1/auth/sessions/{oturum_id}/revoke", headers=baslik)

    assert kapat.status_code == 200
    kalanlar = [o["id"] for o in istemci.get("/api/v1/auth/sessions", headers=baslik).json()]
    assert oturum_id not in kalanlar
    sonra = istemci.post("/api/v1/auth/refresh", json={"refresh_token": govde["refresh_token"]})
    assert sonra.status_code == 403


def test_uc_nokta_olay_gunluguna_yaziliyor(istemci: TestClient) -> None:
    """Denetim "kim ne zaman girdi"yi soruyor; yenileme de oturum açmaktır."""
    depo = bagimliliklar._izi_deposu()
    once = len(depo.events(limit=1000))
    govde = _giris(istemci)
    istemci.post("/api/v1/auth/refresh", json={"refresh_token": govde["refresh_token"]})

    turler = [o.event_type for o in depo.events(limit=1000)[once:]]

    assert "oturum.acildi" in turler
    assert "oturum.yenilendi" in turler
