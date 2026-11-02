"""Oturum ve yetki testleri (ST-004, ST-005, ST-006; TC-006, TC-009, TC-010).

İki ayrı soru sınanıyor:

* **Kimlik** — kod akışı, sayaçlar ve belirteç (TC-009).
* **Yetki** — aynı uç nokta, farklı rol: kim neyi görüyor (TC-006, TC-010).
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi.testclient import TestClient

from conftest import TELEFON, oturum_ac
from talimatname.api.app import create_app
from talimatname.api.errors import URN_PREFIX
from talimatname.domain.auth import BLOCK_FOR, CODE_TTL, MAX_ATTEMPTS, RESEND_AFTER
from talimatname.infra.memory import MemoryUserRepository, sabit_id
from talimatname.services.auth import (
    AuthService,
    OtpRejected,
    ResendTooSoon,
    UnknownPhone,
    UserInactive,
)
from talimatname.services.tokens import TokenInvalid
from talimatname.settings import Settings

KADIKOY = sabit_id("sube:KDK")
BESIKTAS = sabit_id("sube:BSK")


class Saat:
    """İlerletilebilir saat: OTP süreleri gerçek beklemeden sınanıyor.

    Şimdiden başlıyor: belirteç süresini PyJWT **gerçek** saate göre
    denetliyor, geçmişte bir başlangıç her belirteci süresi dolmuş
    gösterirdi.
    """

    def __init__(self) -> None:
        self.an = datetime.now(UTC)

    def __call__(self) -> datetime:
        return self.an

    def ilerle(self, sure: timedelta) -> None:
        self.an += sure


def _servis(saat: Saat | None = None, kod: str = "123456") -> AuthService:
    return AuthService(
        MemoryUserRepository(),
        settings=Settings(environment="dev"),
        now=saat or Saat(),
        code_factory=lambda: kod,
    )


# --- kimlik -----------------------------------------------------------


def test_tc009_dogru_kod_belirtec_uretir() -> None:
    servis = _servis()
    numara, kod = servis.request_code("0532 111 00 01")
    assert numara == "+905321110001"
    assert kod == "123456"

    kullanici, belirtec = servis.verify_code("0532 111 00 01", "123456")
    assert kullanici.full_name == "Cem Yönetici"
    assert servis.user_from_token(belirtec).id == kullanici.id


def test_kod_yalnizca_gelistirmede_yanitta_yer_alir() -> None:
    """Geliştirmede kolaylık, başka ortamda sızıntı: ortam ayırt ediyor."""
    servis = AuthService(
        MemoryUserRepository(),
        settings=Settings(environment="staging"),
        now=Saat(),
        code_factory=lambda: "123456",
    )
    _, kod = servis.request_code("+905321110001")
    assert kod is None


def test_demo_modu_kodu_yanita_ekler() -> None:
    """SMS yokken demo kapısı kilitli kalmasın diye açık bir ayar var.

    Ortam adını ("dev") giriş davranışı için zorlamak yerine ayrı bir
    ayar: niyet yapılandırmada görünüyor ve prod'da yasak.
    """
    servis = AuthService(
        MemoryUserRepository(),
        settings=Settings(environment="staging", demo_show_otp_code=True),
        now=Saat(),
        code_factory=lambda: "123456",
    )
    _, kod = servis.request_code("+905321110001")
    assert kod == "123456"


def test_tc009_uc_hatali_deneme_bloklar() -> None:
    saat = Saat()
    servis = _servis(saat)
    servis.request_code("+905321110001")

    for _ in range(MAX_ATTEMPTS):
        with pytest.raises(OtpRejected):
            servis.verify_code("+905321110001", "000000")

    # Doğru kod bile blok süresince kabul edilmiyor.
    with pytest.raises(OtpRejected):
        servis.verify_code("+905321110001", "123456")

    saat.ilerle(BLOCK_FOR + timedelta(seconds=1))
    servis.request_code("+905321110001")
    kullanici, _ = servis.verify_code("+905321110001", "123456")
    assert kullanici.phone == "+905321110001"


def test_tc009_altmis_saniye_icinde_yeniden_gonderim_yok() -> None:
    saat = Saat()
    servis = _servis(saat)
    servis.request_code("+905321110001")

    with pytest.raises(ResendTooSoon):
        servis.request_code("+905321110001")

    saat.ilerle(RESEND_AFTER + timedelta(seconds=1))
    servis.request_code("+905321110001")  # artık serbest


def test_tc009_kodun_suresi_dolar() -> None:
    saat = Saat()
    servis = _servis(saat)
    servis.request_code("+905321110001")
    saat.ilerle(CODE_TTL + timedelta(seconds=1))

    with pytest.raises(OtpRejected, match="süresi"):
        servis.verify_code("+905321110001", "123456")


def test_bilinmeyen_numara_ve_kodsuz_dogrulama_reddedilir() -> None:
    servis = _servis()
    with pytest.raises(UnknownPhone):
        servis.request_code("+905320000000")
    with pytest.raises(OtpRejected, match="Önce kod"):
        servis.verify_code("+905321110001", "123456")


def test_pasif_kullanicinin_belirteci_aninda_gecersiz() -> None:
    """Yetki belirteçten değil kullanıcıdan okunuyor (FR-0205)."""
    depo = MemoryUserRepository()
    servis = AuthService(depo, settings=Settings(environment="dev"), now=Saat())
    kullanici = depo.user_by_phone("+905321110005")
    assert kullanici is not None
    belirtec = servis.issue_token(kullanici)
    assert servis.user_from_token(belirtec).id == kullanici.id

    depo.save_user(replace(kullanici, status="inactive"))
    with pytest.raises(UserInactive):
        servis.user_from_token(belirtec)


def test_bozuk_belirtec_reddedilir() -> None:
    with pytest.raises(TokenInvalid):
        _servis().user_from_token("bu.bir.belirtec-degil")


# --- uç noktalar ------------------------------------------------------


def _istemci(rol: str | None = None) -> TestClient:
    istemci = TestClient(create_app(Settings(environment="dev")))
    return istemci if rol is None else oturum_ac(istemci, rol)


#: Rol matrisinin (06-kvkk-ve-guvenlik) personele **vermediği** panel
#: okuma uçları. Kapsam denetimi bunları zaten şubeyle sınırlıyordu;
#: eksik olan rol boyutuydu — personel kendi şubesinin plan, şablon ve
#: raporlarını okuyabiliyordu (FR-0205 "yetki = rol × kapsam").
PANEL_OKUMA = [
    "/api/v1/branches",
    "/api/v1/templates",
    "/api/v1/plans",
    "/api/v1/dashboard",
    "/api/v1/actions",
    "/api/v1/actions/counts",
    "/api/v1/reports/exports",
    "/api/v1/reports/monthly?year=2026&month=11",
    "/api/v1/reports/measurements?first_day=2026-11-01&last_day=2026-11-30",
    "/api/v1/reports/gallery?first_day=2026-11-01&last_day=2026-11-30",
]

#: Personelin işi bunlarla yürüyor; kapalı olsalar ürün çalışmaz.
PERSONEL_ISI = ["/api/v1/auth/me", "/api/v1/runs"]


@pytest.mark.parametrize("yol", PANEL_OKUMA)
def test_personel_panel_okumasindan_dislaniyor(yol: str) -> None:
    """TC-006: yetki = rol × kapsam; yalnızca kapsam yetmiyor."""
    yanit = _istemci("staff").get(yol)

    assert yanit.status_code == 403, f"{yol} -> {yanit.status_code}"
    assert _hata_kodu(yanit) == "yetki-yok"


@pytest.mark.parametrize("yol", PERSONEL_ISI)
def test_personel_kendi_isini_gorebiliyor(yol: str) -> None:
    yanit = _istemci("staff").get(yol)

    assert yanit.status_code == 200, f"{yol} -> {yanit.text}"


@pytest.mark.parametrize("rol", ["admin", "region_manager", "branch_manager"])
def test_mudurler_panel_okumasini_gorebiliyor(rol: str) -> None:
    """Kapı personeli dışarıda bırakırken müdürleri de kapatmasın."""
    istemci = _istemci(rol)

    for yol in PANEL_OKUMA:
        assert istemci.get(yol).status_code == 200, f"{rol} {yol}"


def _hata_kodu(yanit: httpx.Response) -> str:
    """problem+json'da sözleşme `type`tir; başı sabit ön ektir."""
    kod: str = yanit.json()["type"]
    return kod.removeprefix(URN_PREFIX)


def test_uc_nokta_kod_gonderildi_demez() -> None:
    """SMS sağlayıcısı yokken 'gönderildi' yazmak yalan olurdu (ST-067)."""
    yanit = _istemci().post("/api/v1/auth/request-code", json={"phone": TELEFON["admin"]})
    assert yanit.status_code == 200
    govde = yanit.json()
    assert govde["delivered"] is False
    assert "ST-067" in govde["note"]
    assert govde["dev_code"] is not None


def test_health_demo_modunu_saklamiyor() -> None:
    """Açık kapıyı kapalı sanmak, kapalı kapıdan tehlikeli."""
    acik = TestClient(create_app(Settings(environment="staging", demo_show_otp_code=True))).get(
        "/api/v1/health"
    )
    kapali = TestClient(create_app(Settings(environment="staging"))).get("/api/v1/health")

    assert acik.json()["demo_show_otp_code"] is True
    assert kapali.json()["demo_show_otp_code"] is False


def test_uc_nokta_kod_ile_oturum_ve_ben() -> None:
    istemci = _istemci()
    numara = TELEFON["branch_manager"]
    kod = istemci.post("/api/v1/auth/request-code", json={"phone": numara}).json()["dev_code"]
    yanit = istemci.post("/api/v1/auth/verify", json={"phone": numara, "code": kod})
    assert yanit.status_code == 200
    oturum = yanit.json()
    assert oturum["token_type"] == "bearer"
    assert oturum["user"]["roles"][0]["role_label"] == "Şube müdürü"

    ben = istemci.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {oturum['access_token']}"}
    )
    assert ben.status_code == 200
    assert ben.json()["full_name"] == "Ayşe Şube"


def test_uc_nokta_belirtecsiz_istek_403() -> None:
    yanit = _istemci().get("/api/v1/branches")
    assert yanit.status_code == 403
    assert _hata_kodu(yanit) == "oturum-yok"


def _gorulen_kodlar(rol: str) -> list[str]:
    agac = _istemci(rol).get("/api/v1/branches").json()
    return [s["code"] for dugum in agac for s in dugum["branches"]]


def test_tc006_sube_muduru_yalnizca_kendi_subesini_gorur() -> None:
    assert _gorulen_kodlar("branch_manager") == ["KDK"]


def test_tc006_bolge_muduru_kendi_bolgesini_gorur() -> None:
    assert set(_gorulen_kodlar("region_manager")) == {"ATS", "KDK", "USK"}


def test_tc010_kapsam_disi_sube_detayi_403() -> None:
    """403, 404 değil: şube kodları zincir içinde zaten biliniyor."""
    yanit = _istemci("branch_manager").get(f"/api/v1/branches/{BESIKTAS}")
    assert yanit.status_code == 403
    assert _hata_kodu(yanit) == "yetki-yok"
    assert _istemci("branch_manager").get(f"/api/v1/branches/{KADIKOY}").status_code == 200


def test_tc010_sube_muduru_sube_ekleyemez() -> None:
    yanit = _istemci("branch_manager").post(
        "/api/v1/branches",
        json={"code": "YNI", "name": "Yeni Şube"},
    )
    assert yanit.status_code == 403
    assert _hata_kodu(yanit) == "yetki-yok"


def test_tc010_pano_kapsamla_sinirli() -> None:
    hepsi = _istemci("admin").get("/api/v1/dashboard").json()
    sube = _istemci("branch_manager").get("/api/v1/dashboard").json()
    assert len(sube["rows"]) == 1
    assert sube["rows"][0]["branch_name"].startswith("Kadıköy")
    assert sube["kpi"]["total"] <= hepsi["kpi"]["total"]


def test_tc010_aksiyonlar_kapsamla_sinirli() -> None:
    hepsi = _istemci("admin").get("/api/v1/actions/counts").json()
    sube = _istemci("branch_manager").get("/api/v1/actions/counts").json()
    assert sube["open"] <= hepsi["open"]

    adlar = {a["branch_name"] for a in _istemci("branch_manager").get("/api/v1/actions").json()}
    assert all(ad.startswith("Kadıköy") for ad in adlar)
