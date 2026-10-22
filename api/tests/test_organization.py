"""Organizasyon: alan doğrulaması, servis kuralları ve uç noktalar (ST-002, ST-007)."""

from __future__ import annotations

from datetime import date, time
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from talimatname.api.app import create_app
from talimatname.domain.organization import (
    Branch,
    BusinessHours,
    ValidationError,
    uniform_hours,
)
from talimatname.infra.memory import MemoryOrganizationRepository, sabit_id
from talimatname.services.organization import (
    BranchCodeTaken,
    BranchNotFound,
    OrganizationService,
    RegionNotFound,
)
from talimatname.settings import Settings


def _sube(code: str = "YEN", name: str = "Yeni Şube", **ek: Any) -> Branch:
    alanlar: dict[str, Any] = {
        "id": uuid4(),
        "code": code,
        "name": name,
        "timezone": "Europe/Istanbul",
        "business_hours": uniform_hours(time(8, 0), time(23, 0)),
    }
    alanlar.update(ek)
    return Branch(**alanlar)


def _servis() -> OrganizationService:
    return OrganizationService(MemoryOrganizationRepository())


# --- alan katmanı ----------------------------------------------------


def test_sube_kodu_bicimi() -> None:
    assert _sube(code="kdk").validated().code == "KDK"
    with pytest.raises(ValidationError, match="büyük harf"):
        _sube(code="K").validated()
    with pytest.raises(ValidationError, match="büyük harf"):
        _sube(code="-KDK").validated()
    with pytest.raises(ValidationError, match="büyük harf"):
        _sube(code="KADIKÖY").validated()


def test_sube_adi_temizlenir() -> None:
    assert _sube(name="  Kadıköy   Moda ").validated().name == "Kadıköy Moda"
    with pytest.raises(ValidationError, match="Boş olamaz"):
        _sube(name="   ").validated()


def test_bilinmeyen_saat_dilimi_reddedilir() -> None:
    with pytest.raises(ValidationError, match="saat dilimi"):
        Branch(id=uuid4(), code="ABC", name="Test", timezone="Mars/Olympus").validated()


def test_acilis_ve_kapanis_ayni_olamaz() -> None:
    with pytest.raises(ValidationError, match="aynı saat"):
        _sube(business_hours={0: BusinessHours(time(9, 0), time(9, 0))}).validated()


def test_eksik_gunler_kapali_sayilir() -> None:
    sube = _sube(business_hours={0: BusinessHours(time(9, 0), time(18, 0))}).validated()
    assert sube.open_days == 1
    assert set(sube.business_hours) == {0, 1, 2, 3, 4, 5, 6}


def test_pencere_motoruna_takvim_verir() -> None:
    """Şube, pencere motorunun beklediği takvim görünümünü üretir."""
    takvim = _sube().validated().calendar()
    assert takvim.timezone == "Europe/Istanbul"
    pazartesi = takvim.hours_for(date(2026, 11, 2))
    assert pazartesi is not None
    assert pazartesi.open_time == time(8, 0)


# --- servis katmanı --------------------------------------------------


def test_tc001_bolge_sube_agaci_alfabetik() -> None:
    agac = _servis().tree()
    assert [d.name for d in agac] == ["Anadolu", "Avrupa", "Ege"]
    assert [b.name for b in agac[0].branches] == ["Ataşehir", "Kadıköy", "Üsküdar"]


def test_bolgesiz_sube_sonda_gosterilir() -> None:
    servis = _servis()
    servis.create_branch(_sube(code="SRB", name="Serbest"))
    agac = servis.tree()
    assert agac[-1].name == "Bölgesiz"
    assert [b.code for b in agac[-1].branches] == ["SRB"]


def test_ayni_kod_ikinci_kez_eklenemez() -> None:
    servis = _servis()
    with pytest.raises(BranchCodeTaken):
        servis.create_branch(_sube(code="KDK"))


def test_guncellemede_kod_cakismasi_yakalanir() -> None:
    servis = _servis()
    kadikoy = servis._repo.branch_by_code("KDK")
    assert kadikoy is not None
    with pytest.raises(BranchCodeTaken):
        servis.update_branch(kadikoy.id, code="USK")


def test_kendi_kodunu_koruyarak_guncelleyebilir() -> None:
    servis = _servis()
    kadikoy = servis._repo.branch_by_code("KDK")
    assert kadikoy is not None
    guncel = servis.update_branch(kadikoy.id, name="Kadıköy Moda")
    assert guncel.name == "Kadıköy Moda"
    assert guncel.code == "KDK"


def test_olmayan_bolge_reddedilir() -> None:
    with pytest.raises(RegionNotFound):
        _servis().create_branch(_sube(code="XYZ", region_id=uuid4()))


def test_olmayan_sube_404() -> None:
    with pytest.raises(BranchNotFound):
        _servis().get(uuid4())


def test_pasiflestirme_veriyi_silmez() -> None:
    """BR-22: pasifleştirme silme değildir; kayıt durur, ağaçtan düşer."""
    servis = _servis()
    kadikoy = sabit_id("sube:KDK")
    servis.set_status(kadikoy, "inactive")

    assert servis.get(kadikoy).status == "inactive"
    aktif = [b.code for d in servis.tree() for b in d.branches]
    assert "KDK" not in aktif
    hepsi = [b.code for d in servis.tree(include_inactive=True) for b in d.branches]
    assert "KDK" in hepsi


def test_istasyonlar_subeye_bagli() -> None:
    servis = _servis()
    istasyonlar = servis.stations(sabit_id("sube:KDK"))
    assert [i.name for i in istasyonlar] == ["Bar", "Depo", "Mutfak", "Salon"]


# --- uç noktalar -----------------------------------------------------


@pytest.fixture
def istemci() -> TestClient:
    return TestClient(create_app(Settings()))


def test_uc_nokta_agaci_doner(istemci: TestClient) -> None:
    yanit = istemci.get("/api/v1/branches")
    assert yanit.status_code == 200
    bolgeler = yanit.json()
    assert {b["name"] for b in bolgeler} == {"Anadolu", "Avrupa", "Ege"}
    assert bolgeler[0]["branches"][0]["open_days"] in (6, 7)


def test_uc_nokta_detayinda_saatler_ve_istasyonlar(istemci: TestClient) -> None:
    yanit = istemci.get(f"/api/v1/branches/{sabit_id('sube:BSK')}")
    assert yanit.status_code == 200
    govde = yanit.json()
    assert govde["code"] == "BSK"
    assert len(govde["business_hours"]) == 7
    assert govde["business_hours"][0]["weekday_name"] == "Pazartesi"
    assert govde["business_hours"][0]["close_time"] == "01:00:00"
    assert len(govde["stations"]) == 4


def test_uc_nokta_bilinmeyen_sube_404_problem(istemci: TestClient) -> None:
    yanit = istemci.get(f"/api/v1/branches/{uuid4()}")
    assert yanit.status_code == 404
    assert yanit.json()["type"] == "urn:talimatname:sube-bulunamadi"


def test_uc_nokta_sube_ekler_ve_cakismayi_bildirir(istemci: TestClient) -> None:
    yeni = {"code": "GOZ", "name": "Göztepe", "region_id": str(sabit_id("bolge:anadolu"))}
    yanit = istemci.post("/api/v1/branches", json=yeni)
    assert yanit.status_code == 201
    assert yanit.json()["code"] == "GOZ"
    assert yanit.json()["open_days"] == 7

    tekrar = istemci.post("/api/v1/branches", json=yeni)
    assert tekrar.status_code == 409
    assert tekrar.json()["type"] == "urn:talimatname:sube-kodu-kullanimda"


def test_uc_nokta_gecersiz_kod_alan_adiyla_doner(istemci: TestClient) -> None:
    yanit = istemci.post("/api/v1/branches", json={"code": "ab cd", "name": "Test"})
    assert yanit.status_code == 422
    govde = yanit.json()
    assert govde["type"] == "urn:talimatname:gecersiz-istek"
    assert govde["errors"][0]["alan"] == "code"
