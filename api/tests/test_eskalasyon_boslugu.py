"""Uyarı kime gidiyor, kime gitmiyor (BR-11, FR-0915).

Eskalasyon merdiveni çalışıyordu ama atlanan basamak yalnızca sunucu
günlüğüne yazılıyordu. 7 Kasım'da demoda görüldü: dört şubede müdür
yok, `eskalasyon.alici_yok` uyarıları dakikada bir birikiyor ve kimse
bunu bilmiyor. Kimsenin görmediği bir uyarı, uyarı değildir.
"""

from __future__ import annotations

from datetime import time
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from conftest import oturum_ac
from talimatname.api.app import create_app
from talimatname.domain.escalation_gaps import branch_gap, escalation_gaps
from talimatname.domain.organization import Branch, uniform_hours
from talimatname.domain.users import RoleAssignment, User
from talimatname.settings import Settings

BOLGE = uuid4()


def _sube(ad: str = "Kadıköy", kod: str = "KDK", *, bolge: object = BOLGE) -> Branch:
    return Branch(
        id=uuid4(),
        code=kod,
        name=ad,
        region_id=bolge,  # type: ignore[arg-type]
        timezone="Europe/Istanbul",
        business_hours=uniform_hours(time(7, 0), time(23, 0)),
    )


def _kisi(rol: str, kapsam: object, *, durum: str = "active") -> User:
    return User(
        id=uuid4(),
        full_name="Test Kişi",
        phone=f"+9053200{uuid4().int % 100000:05d}",
        assignments=(RoleAssignment(rol, kapsam),),  # type: ignore[arg-type]
        status=durum,  # type: ignore[arg-type]
    )


def test_sube_muduru_varsa_bosluk_yok() -> None:
    sube = _sube()

    assert branch_gap(sube, [_kisi("branch_manager", sube.id)]) is None


def test_sube_muduru_yoksa_bolgeye_dusuyor() -> None:
    sube = _sube()

    bosluk = branch_gap(sube, [_kisi("region_manager", BOLGE)])

    assert bosluk is not None
    assert bosluk.missing == ("branch_manager",)
    assert bosluk.reached == "region_manager"
    assert not bosluk.critical


def test_bolge_de_yoksa_yoneticiye_dusuyor() -> None:
    sube = _sube()

    bosluk = branch_gap(sube, [_kisi("admin", None)])

    assert bosluk is not None
    assert bosluk.missing == ("branch_manager", "region_manager")
    assert bosluk.reached == "admin"
    assert not bosluk.critical


def test_kimse_yoksa_kritik() -> None:
    """Sessiz kayıp: kaçırılan liste hiçbir yere gitmiyor."""
    bosluk = branch_gap(_sube(), [])

    assert bosluk is not None
    assert bosluk.reached == "hicbiri"
    assert bosluk.critical


def test_pasif_mudur_sayilmiyor() -> None:
    """Pasifleştirilen kullanıcı giriş yapamıyor; uyarı da ona gitmez."""
    sube = _sube()

    bosluk = branch_gap(sube, [_kisi("branch_manager", sube.id, durum="inactive")])

    assert bosluk is not None
    assert "branch_manager" in bosluk.missing


def test_baska_subenin_muduru_sayilmiyor() -> None:
    sube = _sube()
    baska = _sube("Beşiktaş", "BSK")

    assert branch_gap(sube, [_kisi("branch_manager", baska.id)]) is not None


def test_pasif_sube_listelenmiyor() -> None:
    from dataclasses import replace

    kapali = replace(_sube(), status="inactive")

    assert escalation_gaps([kapali], []) == []


def test_kritik_olanlar_once_siralaniyor() -> None:
    bolgeli = _sube("Alsancak", "ALS")
    sessiz = _sube("Zeytinburnu", "ZTB", bolge=uuid4())

    liste = escalation_gaps([bolgeli, sessiz], [_kisi("region_manager", BOLGE)])

    assert [b.branch_name for b in liste] == ["Zeytinburnu", "Alsancak"]


# --- uç nokta ---------------------------------------------------------


@pytest.fixture
def istemci() -> TestClient:
    return oturum_ac(TestClient(create_app(Settings())))


def test_uc_nokta_panoda_bosluklar_gorunuyor(istemci: TestClient) -> None:
    """Tohumda yalnızca Kadıköy ve Beşiktaş'ın müdürü var."""
    govde = istemci.get("/api/v1/dashboard").json()

    bosluklar = govde["escalation_gaps"]
    assert bosluklar, "müdürsüz şubeler panoda görünmüyor"
    adlar = {b["branch_name"] for b in bosluklar}
    assert "Şişli" in adlar
    assert "Kadıköy" not in adlar
    ssl = next(b for b in bosluklar if b["branch_name"] == "Şişli")
    assert ssl["missing"] == ["Şube müdürü", "Bölge müdürü"]
    assert ssl["reached_label"] == "Yönetici"
    assert ssl["critical"] is False


def test_uc_nokta_kapsam_disindaki_sube_gorunmuyor(istemci: TestClient) -> None:
    """Bölge müdürü kendi bölgesinin eksiğini görür, zincirin değil (FR-0205)."""
    bolge = oturum_ac(istemci, "region_manager")

    govde = bolge.get("/api/v1/dashboard").json()

    adlar = {b["branch_name"] for b in govde["escalation_gaps"]}
    assert "Şişli" not in adlar  # Avrupa bölgesi


# --- kurulum sihirbazı ------------------------------------------------


def test_kurulumda_mudursuz_sube_adimi_bitirmiyor(istemci: TestClient) -> None:
    """Tohumda sekiz şube var, ikisinin müdürü: adım bitmiş sayılmamalı.

    Sihirbazı kapatmayı engellemiyor — zorlamak değil, görünür kılmak.
    """
    adimlar = {a["step"]: a for a in istemci.get("/api/v1/setup").json()["steps"]}

    personel = adimlar["staff"]
    assert personel["done"] is False
    assert "şubede müdür yok" in personel["detail"]


def test_kurulum_kapatilabiliyor(istemci: TestClient) -> None:
    """Adım bitmemiş olsa da sihirbaz kapanabilir: tuzak kurmuyoruz."""
    try:
        assert istemci.post("/api/v1/setup/complete").status_code == 200
    finally:
        istemci.post("/api/v1/setup/reopen")
