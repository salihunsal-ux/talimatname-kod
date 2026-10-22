"""Personel, rol ve kapsam testleri (ST-011, ST-013; TC-005…007, TC-010, TC-104)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from talimatname.api.app import create_app
from talimatname.domain.users import (
    RoleAssignment,
    User,
    can_access,
    normalize_phone,
    visible_branches,
)
from talimatname.domain.validation import ValidationError
from talimatname.infra.memory import (
    MemoryOrganizationRepository,
    MemoryUserRepository,
    sabit_id,
)
from talimatname.services.users import (
    MaskedUserImmutable,
    PhoneTaken,
    ScopeNotFound,
    UserNotFound,
    UserService,
)
from talimatname.settings import Settings

KADIKOY = sabit_id("sube:KDK")
BESIKTAS = sabit_id("sube:BSK")
ANADOLU = sabit_id("bolge:anadolu")


def _servis(simdi: datetime | None = None) -> UserService:
    an = simdi or datetime(2026, 11, 2, 9, 0, tzinfo=UTC)
    return UserService(MemoryUserRepository(), MemoryOrganizationRepository(), now=lambda: an)


def _kullanici(**ek: object) -> User:
    alanlar: dict[str, object] = {
        "id": uuid4(),
        "full_name": "Yeni Kişi",
        "phone": "+905320000001",
        "assignments": (RoleAssignment("staff", KADIKOY),),
    }
    alanlar.update(ek)
    return User(**alanlar)  # type: ignore[arg-type]


# --- telefon ---------------------------------------------------------


@pytest.mark.parametrize(
    ("girdi", "beklenen"),
    [
        ("0532 123 45 67", "+905321234567"),
        ("0532-123-45-67", "+905321234567"),
        ("(0532) 123 45 67", "+905321234567"),
        ("5321234567", "+905321234567"),
        ("+905321234567", "+905321234567"),
        ("00905321234567", "+905321234567"),
        ("+49 170 1234567", "+491701234567"),
    ],
)
def test_telefon_e164e_cevrilir(girdi: str, beklenen: str) -> None:
    assert normalize_phone(girdi) == beklenen


def test_gecersiz_telefon_reddedilir() -> None:
    with pytest.raises(ValidationError, match="telefon"):
        normalize_phone("123")


# --- rol ve kapsam ---------------------------------------------------


def test_yonetici_kapsam_almaz() -> None:
    with pytest.raises(ValidationError, match="hesabın tamamını"):
        _kullanici(assignments=(RoleAssignment("admin", KADIKOY),)).validated()


def test_sube_muduru_kapsamsiz_olamaz() -> None:
    with pytest.raises(ValidationError, match="kapsam seçilmeli"):
        _kullanici(assignments=(RoleAssignment("branch_manager"),)).validated()


def test_rolsuz_kullanici_olmaz() -> None:
    with pytest.raises(ValidationError, match="En az bir rol"):
        _kullanici(assignments=()).validated()


def test_tc006_bolge_muduru_yalnizca_kendi_bolgesini_gorur() -> None:
    org = MemoryOrganizationRepository()
    murat = _kullanici(assignments=(RoleAssignment("region_manager", ANADOLU),)).validated()

    gorunur = {b.code for b in visible_branches(murat, org.branches())}
    assert gorunur == {"KDK", "USK", "ATS"}


def test_tc010_sube_muduru_baska_subeyi_goremez() -> None:
    org = MemoryOrganizationRepository()
    ayse = _kullanici(assignments=(RoleAssignment("branch_manager", KADIKOY),)).validated()
    kadikoy = org.branch(KADIKOY)
    besiktas = org.branch(BESIKTAS)
    assert kadikoy is not None
    assert besiktas is not None

    assert can_access(ayse, kadikoy) is True
    assert can_access(ayse, besiktas) is False


def test_yonetici_tum_subeleri_gorur() -> None:
    org = MemoryOrganizationRepository()
    cem = _kullanici(assignments=(RoleAssignment("admin"),)).validated()
    assert len(visible_branches(cem, org.branches())) == len(org.branches())


def test_pasif_kullanici_hicbir_subeyi_goremez() -> None:
    org = MemoryOrganizationRepository()
    kadikoy = org.branch(KADIKOY)
    assert kadikoy is not None
    pasif = _kullanici(assignments=(RoleAssignment("admin"),), status="inactive").validated()
    assert can_access(pasif, kadikoy) is False


# --- servis ----------------------------------------------------------


def test_tc005_davet_kuyruga_alinir_gonderilmez() -> None:
    an = datetime(2026, 11, 2, 9, 0, tzinfo=UTC)
    servis = _servis(an)
    kullanici = servis.invite(_kullanici())
    assert kullanici.invited_at == an
    assert kullanici.status == "active"


def test_ayni_telefon_ikinci_kez_davet_edilemez() -> None:
    servis = _servis()
    with pytest.raises(PhoneTaken):
        servis.invite(_kullanici(phone="0532 111 00 01"))


def test_olmayan_kapsam_reddedilir() -> None:
    servis = _servis()
    with pytest.raises(ScopeNotFound):
        servis.invite(_kullanici(assignments=(RoleAssignment("staff", uuid4()),)))


def test_tc007_pasiflestirme_kaydi_silmez() -> None:
    servis = _servis()
    emre = next(k for k in servis.list() if k.full_name.startswith("Emre"))

    servis.set_status(emre.id, "inactive")

    assert servis.get(emre.id).status == "inactive"
    assert emre.id not in {k.id for k in servis.list()}
    assert emre.id in {k.id for k in servis.list(include_inactive=True)}


def test_subeye_gore_suzme() -> None:
    servis = _servis()
    kadikoy_ekibi = {k.full_name for k in servis.list(branch_id=KADIKOY)}
    # Kadıköy'ün kendi ekibi + Anadolu bölge müdürü + yönetici
    assert "Ayşe Şube" in kadikoy_ekibi
    assert "Emre Personel" in kadikoy_ekibi
    assert "Murat Bölge" in kadikoy_ekibi
    assert "Cem Yönetici" in kadikoy_ekibi
    assert "Deniz Şube" not in kadikoy_ekibi


def test_role_gore_suzme() -> None:
    servis = _servis()
    assert {k.full_name for k in servis.list(role="branch_manager")} == {
        "Ayşe Şube",
        "Deniz Şube",
    }


def test_tc104_maskeleme_kisi_verisini_siler_kaydi_birakir() -> None:
    an = datetime(2027, 5, 1, 12, 0, tzinfo=UTC)
    servis = _servis(an)
    emre = next(k for k in servis.list() if k.full_name.startswith("Emre"))

    maskeli = servis.mask(emre.id)

    assert maskeli.id == emre.id  # kayıt aynı: cevaplar ve kanıtlar bağlı kalır
    assert maskeli.full_name.startswith("Eski personel #")
    assert maskeli.phone is None
    assert maskeli.email is None
    assert maskeli.assignments == ()
    assert maskeli.masked_at == an


def test_maskeli_kullanici_degistirilemez() -> None:
    servis = _servis()
    emre = next(k for k in servis.list() if k.full_name.startswith("Emre"))
    servis.mask(emre.id)
    with pytest.raises(MaskedUserImmutable):
        servis.update(emre.id, full_name="Yeni Ad")


def test_olmayan_kullanici() -> None:
    with pytest.raises(UserNotFound):
        _servis().get(uuid4())


# --- uç noktalar -----------------------------------------------------


@pytest.fixture
def istemci() -> TestClient:
    return TestClient(create_app(Settings()))


def test_uc_nokta_personel_listesi(istemci: TestClient) -> None:
    yanit = istemci.get("/api/v1/users")
    assert yanit.status_code == 200
    adlar = [k["full_name"] for k in yanit.json()]
    assert adlar == sorted(adlar, key=str.casefold)
    assert yanit.json()[0]["assignments"][0]["role_label"]


def test_uc_nokta_davet_gonderildi_demez(istemci: TestClient) -> None:
    """Kanal bağlı değilken 'gönderildi' denmez — kuyruğa alındı denir."""
    yanit = istemci.post(
        "/api/v1/users",
        json={
            "full_name": "Test Kişi",
            "phone": "0532 999 00 11",
            "assignments": [{"role": "staff", "scope_id": str(KADIKOY)}],
        },
    )
    assert yanit.status_code == 201
    govde = yanit.json()
    assert govde["invite_sent"] is False
    assert "ST-044" in govde["invite_note"]
    assert govde["user"]["phone"] == "+905329990011"


def test_uc_nokta_rol_kapsam_hatasi_alan_adiyla_doner(istemci: TestClient) -> None:
    yanit = istemci.post(
        "/api/v1/users",
        json={
            "full_name": "Test",
            "phone": "0532 999 00 12",
            "assignments": [{"role": "admin", "scope_id": str(KADIKOY)}],
        },
    )
    assert yanit.status_code == 422
    assert yanit.json()["errors"][0]["alan"] == "scope_id"


def test_uc_nokta_maskeleme(istemci: TestClient) -> None:
    liste = istemci.get("/api/v1/users").json()
    hedef = next(k for k in liste if k["full_name"].startswith("Zeynep"))

    yanit = istemci.post(f"/api/v1/users/{hedef['id']}/mask")

    assert yanit.status_code == 200
    assert yanit.json()["status"] == "masked"
    assert yanit.json()["phone"] is None
