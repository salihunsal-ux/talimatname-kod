"""Aksiyon testleri (ST-064, ST-065, ST-152; TC-065…070, BR-10)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from conftest import oturum_ac
from talimatname.api.app import create_app
from talimatname.domain.actions import DUE_HOURS, Action, action_id, due_at, from_missed_run
from talimatname.domain.validation import ValidationError
from talimatname.infra.memory import (
    MemoryActionRepository,
    MemoryOrganizationRepository,
    MemoryPlanRepository,
    MemoryTemplateRepository,
    sabit_id,
)
from talimatname.services.actions import ActionAlreadyClosed, ActionService, BranchUnknown
from talimatname.services.scheduler import SchedulerService
from talimatname.settings import Settings

KADIKOY = sabit_id("sube:KDK")
AN = datetime(2026, 11, 2, 9, 0, tzinfo=UTC)


def _servis(an: datetime = AN) -> tuple[ActionService, MemoryPlanRepository]:
    plan_deposu = MemoryPlanRepository()
    servis = ActionService(
        MemoryActionRepository(),
        MemoryOrganizationRepository(),
        plan_deposu,
        now=lambda: an,
    )
    return servis, plan_deposu


def _aksiyon(**ek: object) -> Action:
    alanlar: dict[str, object] = {
        "id": uuid4(),
        "branch_id": KADIKOY,
        "title": "Test aksiyonu",
        "source": "manual",
        "priority": "normal",
        "opened_at": AN,
        "due_at": due_at("normal", AN),
    }
    alanlar.update(ek)
    return Action(**alanlar)  # type: ignore[arg-type]


# --- alan --------------------------------------------------------------


@pytest.mark.parametrize(("oncelik", "saat"), [("critical", 4), ("high", 24), ("normal", 72)])
def test_br10_vade_oncelige_gore_sabit(oncelik: str, saat: int) -> None:
    assert DUE_HOURS[oncelik] == saat  # type: ignore[index]
    assert due_at(oncelik, AN) == AN + timedelta(hours=saat)  # type: ignore[arg-type]


def test_tc066_kapanis_notu_zorunlu() -> None:
    """FR-0904: 'kapattım' demek yetmiyor, ne yapıldığı yazılıyor."""
    aksiyon = _aksiyon()
    with pytest.raises(ValidationError, match="Kapanış notu"):
        aksiyon.close("  ", AN)
    with pytest.raises(ValidationError, match="Kapanış notu"):
        aksiyon.close("ok", AN)


def test_tc066_kapanis_notu_temizlenir() -> None:
    kapali = _aksiyon().close("  Termostat   değişti  ", AN)

    assert kapali.status == "closed"
    assert kapali.close_note == "Termostat değişti"
    assert kapali.closed_at == AN


def test_vadesi_gecen_acik_aksiyon_gecikmis_sayilir() -> None:
    aksiyon = _aksiyon()

    assert aksiyon.overdue(AN + timedelta(hours=71)) is False
    assert aksiyon.overdue(AN + timedelta(hours=73)) is True


def test_kapali_aksiyon_gecikmis_sayilmaz() -> None:
    kapali = _aksiyon().close("Yapıldı ve kontrol edildi", AN)

    assert kapali.overdue(AN + timedelta(days=30)) is False


def test_kaynakli_aksiyonun_kimligi_kaynaktan_turer() -> None:
    """FR-0903: aynı kaynak iki aksiyon açmaz."""
    run = uuid4()
    ilk = from_missed_run(
        run_id=run, branch_id=KADIKOY, plan_name="Kapanış", business_day="2026-11-02", now=AN
    )
    ikinci = from_missed_run(
        run_id=run,
        branch_id=KADIKOY,
        plan_name="Kapanış",
        business_day="2026-11-02",
        now=AN + timedelta(hours=5),
    )

    assert ilk.id == ikinci.id == action_id("missed_run", run)
    assert ilk.priority == "high"  # BR-10: kaçırma yüksek öncelikli


def test_kaynaksiz_sistem_aksiyonu_olmaz() -> None:
    with pytest.raises(ValidationError, match="kaynağı belirtilmeli"):
        _aksiyon(source="missed_run", source_id=None).validated()


# --- servis ------------------------------------------------------------


def test_tc069_kacirilan_calistirmadan_aksiyon_acilir() -> None:
    servis, plan_deposu = _servis(datetime.now(UTC))
    SchedulerService(
        plan_deposu,
        MemoryOrganizationRepository(),
        MemoryTemplateRepository(),
        servis,
    ).tick()

    acik = servis.list_actions()

    assert len(acik) == 1
    assert acik[0].source == "missed_run"
    assert acik[0].priority == "high"


def test_tc069_tekrar_senkron_yeni_aksiyon_acmaz() -> None:
    servis, plan_deposu = _servis(datetime.now(UTC))
    zamanlayici = SchedulerService(
        plan_deposu, MemoryOrganizationRepository(), MemoryTemplateRepository(), servis
    )

    ilk = zamanlayici.tick()
    ikinci = zamanlayici.tick()

    assert ilk.actions_opened == 1
    assert ikinci.actions_opened == 0
    assert len(servis.list_actions()) == 1


def test_elle_aksiyon_vadesiyle_acilir() -> None:
    servis, _ = _servis()

    aksiyon = servis.create_manual(branch_id=KADIKOY, title="Buzdolabı tamiri", priority="critical")

    assert aksiyon.due_at == AN + timedelta(hours=4)
    assert aksiyon.source == "manual"


def test_olmayan_subeye_aksiyon_acilmaz() -> None:
    servis, _ = _servis()
    with pytest.raises(BranchUnknown):
        servis.create_manual(branch_id=uuid4(), title="Test")


def test_kapali_aksiyon_ikinci_kez_kapatilmaz() -> None:
    servis, _ = _servis()
    aksiyon = servis.create_manual(branch_id=KADIKOY, title="Test")
    servis.close(aksiyon.id, "Yapıldı ve kontrol edildi")

    with pytest.raises(ActionAlreadyClosed):
        servis.close(aksiyon.id, "Tekrar kapatma denemesi")


def test_liste_vadesi_yakin_olani_one_alir() -> None:
    servis, _ = _servis()
    servis.create_manual(branch_id=KADIKOY, title="Normal iş", priority="normal")
    servis.create_manual(branch_id=KADIKOY, title="Kritik iş", priority="critical")

    assert [a.title for a in servis.list_actions()] == ["Kritik iş", "Normal iş"]


def test_sayaclar_acik_gecikmis_ve_kritigi_ayirir() -> None:
    servis, _ = _servis()
    servis.create_manual(branch_id=KADIKOY, title="Kritik", priority="critical")
    kapanacak = servis.create_manual(branch_id=KADIKOY, title="Kapanan")
    servis.close(kapanacak.id, "Tamamlandı ve doğrulandı")

    assert servis.counts() == {"open": 1, "overdue": 0, "critical": 1}


# --- uç noktalar -------------------------------------------------------


@pytest.fixture
def istemci() -> TestClient:
    return oturum_ac(TestClient(create_app(Settings())))


def test_uc_nokta_kacirilan_listeden_aksiyon(istemci: TestClient) -> None:
    istemci.post("/api/v1/scheduler/tick")

    yanit = istemci.get("/api/v1/actions")

    assert yanit.status_code == 200
    kacirilan = next(a for a in yanit.json() if a["source"] == "missed_run")
    assert kacirilan["source_label"] == "Kaçırılan liste"
    assert kacirilan["priority_label"] == "Yüksek"
    assert kacirilan["branch_name"]


def test_uc_nokta_notsuz_kapatma_reddedilir(istemci: TestClient) -> None:
    sube = next(s for d in istemci.get("/api/v1/branches").json() for s in d["branches"])
    aksiyon = istemci.post(
        "/api/v1/actions", json={"branch_id": sube["id"], "title": "Test işi"}
    ).json()

    yanit = istemci.post(f"/api/v1/actions/{aksiyon['id']}/close", json={"note": "ok"})

    assert yanit.status_code == 422


def test_uc_nokta_kapatma_ve_tekrar_kapatma(istemci: TestClient) -> None:
    sube = next(s for d in istemci.get("/api/v1/branches").json() for s in d["branches"])
    aksiyon = istemci.post(
        "/api/v1/actions",
        json={"branch_id": sube["id"], "title": "Kapatılacak iş", "priority": "critical"},
    ).json()
    assert aksiyon["remaining_hours"] == pytest.approx(4.0, abs=0.1)

    kapali = istemci.post(
        f"/api/v1/actions/{aksiyon['id']}/close",
        json={"note": "Teknisyen geldi, termostat değişti"},
    )
    assert kapali.status_code == 200
    assert kapali.json()["status"] == "closed"
    assert kapali.json()["remaining_hours"] is None

    tekrar = istemci.post(
        f"/api/v1/actions/{aksiyon['id']}/close", json={"note": "İkinci deneme notu"}
    )
    assert tekrar.status_code == 409
    assert tekrar.json()["type"] == "urn:talimatname:aksiyon-kapali"
