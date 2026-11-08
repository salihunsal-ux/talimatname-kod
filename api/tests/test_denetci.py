"""Denetçi rolü ve şube denetimi şablonu (FR-0205, BR-26; 02-urun/07 §9).

Denetçi şubeye gidip denetim listesini **kendisi** dolduruyor. Mevcut
roller bunu karşılamıyordu: personel tek şubeye bağlı, bölge müdürü ise
planı değiştirip listeyi iptal edebiliyor. Denetçi gözlemler ve
kaydeder — yönetmez.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from conftest import TELEFON, oturum_ac
from talimatname.api.app import create_app
from talimatname.domain.organization import Branch
from talimatname.domain.users import ROLE_LABELS, ROLE_SCOPE, User, can_access
from talimatname.infra.memory import MemoryOrganizationRepository, MemoryUserRepository, sabit_id
from talimatname.services.library import CATALOG, DENETIM, DENETIM_PROTOKOLU
from talimatname.settings import Settings


def _denetci() -> User:
    kisi = MemoryUserRepository().user_by_phone(TELEFON["auditor"])
    assert kisi is not None, "tohumda denetçi yok"
    return kisi


def _sube(kod: str) -> Branch:
    org = MemoryOrganizationRepository()
    return next(s for s in org.branches() if s.code == kod)


# --- rol --------------------------------------------------------------


def test_denetci_bolge_kapsamli() -> None:
    assert ROLE_SCOPE["auditor"] == "region"
    assert ROLE_LABELS["auditor"] == "Denetçi"


def test_denetci_kendi_bolgesindeki_subeyi_goruyor() -> None:
    kisi = _denetci()

    assert can_access(kisi, _sube("KDK"))  # Anadolu
    assert can_access(kisi, _sube("USK"))  # Anadolu


def test_denetci_baska_bolgeyi_goremiyor() -> None:
    """Kapsam rolün yarısı: denetçi her yeri görmüyor (FR-0205)."""
    assert not can_access(_denetci(), _sube("BSK"))  # Avrupa


# --- şablon -----------------------------------------------------------


def test_denetim_sablonu_kutuphanede() -> None:
    assert DENETIM in CATALOG
    assert DENETIM.key == "sube-denetimi"


def test_sablon_urun_belgesindeki_sayilari_tutuyor() -> None:
    """02-urun/07 §9: 16 cevaplanabilir madde, 3 kritik."""
    maddeler = [m for b in DENETIM.sections for m in b.items]
    cevaplanabilir = [m for m in maddeler if m.type != "instruction"]

    assert len(cevaplanabilir) == 16
    assert sum(1 for m in cevaplanabilir if m.critical) == 3


def test_protokol_talimat_satiri_olarak_duruyor() -> None:
    """Talimat satırı cevaplanmaz ve puanlanmaz (BR-08a, BR-07).

    Denetçinin uyguladığı set listenin **içinde**: ayrı bir belgede
    dursa kimse okumaz, listenin başında durursa her denetimde okunur.
    """
    protokol = DENETIM.sections[0]

    assert protokol.title == "Denetim protokolü"
    assert [m.title for m in protokol.items] == list(DENETIM_PROTOKOLU)
    assert all(m.type == "instruction" for m in protokol.items)
    assert all(not m.required for m in protokol.items)


def test_protokol_habersizlikle_basliyor() -> None:
    """Habersizlik denetimin en kolay kaybedilen parçası: ilk satır."""
    assert DENETIM_PROTOKOLU[0].startswith("Habersiz gel")


# --- yetki sınırları --------------------------------------------------


@pytest.fixture
def denetci() -> TestClient:
    return oturum_ac(TestClient(create_app(Settings())), "auditor")


def test_denetci_panoyu_ve_sube_agacini_goruyor(denetci: TestClient) -> None:
    assert denetci.get("/api/v1/dashboard").status_code == 200
    assert denetci.get("/api/v1/branches").status_code == 200
    assert denetci.get("/api/v1/templates").status_code == 200
    assert denetci.get("/api/v1/reports/monthly?year=2026&month=11").status_code == 200


def test_denetci_plan_yayinlayamiyor(denetci: TestClient) -> None:
    yanit = denetci.post(
        "/api/v1/plans",
        json={
            "name": "Olmaz",
            "template_version_id": str(sabit_id("surum:kapanis")),
            "branch_ids": [],
            "schedule": {"repeat": "daily", "starts_on": "2026-11-08"},
        },
    )

    assert yanit.status_code == 403


def test_denetci_personel_acamiyor(denetci: TestClient) -> None:
    yanit = denetci.post(
        "/api/v1/users",
        json={
            "full_name": "Olmaz Kişi",
            "phone": "0532 999 77 66",
            "assignments": [{"role": "staff", "scope_id": str(sabit_id("sube:KDK"))}],
        },
    )

    assert yanit.status_code == 403


def test_denetci_listeyi_iptal_edemiyor(denetci: TestClient) -> None:
    """ "Yapılmayacak" bir yönetim kararı; denetçi gözlemler, yönetmez."""
    calistirmalar = denetci.get("/api/v1/runs").json()
    if not calistirmalar:
        pytest.skip("bugün çalıştırma yok")

    yanit = denetci.post(f"/api/v1/runs/{calistirmalar[0]['id']}/cancel", json={"reason": "olmaz"})

    assert yanit.status_code == 403


def test_denetci_elle_aksiyon_acabiliyor(denetci: TestClient) -> None:
    """Denetimde bulunan sorun aksiyona dönebilmeli."""
    sube = next(s for d in denetci.get("/api/v1/branches").json() for s in d["branches"])

    yanit = denetci.post(
        "/api/v1/actions",
        json={
            "branch_id": sube["id"],
            "title": "Denetimde görüldü: davlumbaz filtresi kirli",
            "priority": "normal",
        },
    )

    assert yanit.status_code in (200, 201)


def test_kutuphane_penceresi_tekrari_dogru_yaziyor() -> None:
    """Aylık şablon "Günlük · …" diyordu: kütüphanede yalnızca günlük
    şablon varken sabit yazılmıştı."""
    from talimatname.api.routers.setup import _pencere_metni

    assert _pencere_metni(DENETIM).startswith("Aylık ·")


def test_uc_nokta_kutuphanede_denetim_aylik_gorunuyor(denetci: TestClient) -> None:
    yanit = oturum_ac(denetci, "admin").get("/api/v1/setup/library")

    denetim = next(s for s in yanit.json() if s["key"] == "sube-denetimi")
    assert denetim["window"].startswith("Aylık ·")
    assert denetim["item_count"] == 16
