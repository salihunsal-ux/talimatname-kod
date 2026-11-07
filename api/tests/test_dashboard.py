"""Pano okuma modeli testleri (ST-077, ST-078; TC-085, TC-118)."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from conftest import oturum_ac
from talimatname.api.app import create_app
from talimatname.infra.memory import (
    MemoryOrganizationRepository,
    MemoryPlanRepository,
    MemoryTemplateRepository,
    sabit_id,
)
from talimatname.services.dashboard import DashboardService
from talimatname.services.plans import PlanService
from talimatname.settings import Settings

KADIKOY = sabit_id("sube:KDK")
USKUDAR = sabit_id("sube:USK")
BESIKTAS = sabit_id("sube:BSK")


def _servis(*, bugunu_uret: bool = False) -> DashboardService:
    """Pano servisi. `bugunu_uret`, zamanlayıcının yaptığı işi taklit eder:
    tohumda yalnızca dünkü çalıştırmalar var, bugünküler üretimle gelir."""
    plan_deposu = MemoryPlanRepository()
    org = MemoryOrganizationRepository()
    if bugunu_uret:
        PlanService(plan_deposu, org, MemoryTemplateRepository()).generate_all()
    return DashboardService(plan_deposu, org)


def _dun() -> date:
    return datetime.now(UTC).date() - timedelta(days=1)


def test_tc085_izgara_sube_satiri_ve_plan_sutunu() -> None:
    board = _servis().board(_dun(), datetime.now(UTC))

    assert [ad for _, ad in board.plans] == ["Günlük kapanış"]
    assert [r.branch_name for r in board.rows] == ["Beşiktaş", "Kadıköy", "Üsküdar"]
    assert board.rows[0].region_name == "Avrupa"


def test_tc118_istisna_satirlari_isaretlenir() -> None:
    """Geç gönderim ve kaçırma istisnadır; zamanında tamamlanan değil."""
    board = _servis().board(_dun(), datetime.now(UTC))
    istisnalar = {r.branch_name for r in board.exception_rows}

    assert istisnalar == {"Üsküdar", "Beşiktaş"}  # geç+başarısız, kaçırıldı
    kadikoy = next(r for r in board.rows if r.branch_name == "Kadıköy")
    assert kadikoy.exception is False


def test_kpi_tamamlanma_ve_gecikme() -> None:
    kpi = _servis().board(_dun(), datetime.now(UTC)).kpi

    assert kpi.total == 3
    assert kpi.submitted == 2
    assert kpi.late == 1
    assert kpi.missed == 1
    assert kpi.completion_percent == 67


def test_her_sey_yolunda_gun_bitmeden_soylenmez() -> None:
    """Penceresi açık çalıştırma varken 'her şey yolunda' yanıltıcı olur.

    "Şimdi" duvar saatinden değil **verinin kendisinden** alınıyor:
    gece yarısından sonra koşulduğunda tohumun pencereleri çoktan
    kapanmış oluyor ve test saate bağlı kalıyordu.
    """
    servis = _servis(bugunu_uret=True)
    bugun = datetime.now(UTC).date()
    acik = [r for r in servis._plans.runs() if r.business_day == bugun]
    an = min(r.window_start for r in acik) + timedelta(minutes=5)
    board = servis.board(bugun, an)

    assert board.kpi.open_now > 0
    assert board.kpi.all_clear is False
    assert board.kpi.missed == 0


def test_bos_gun_bos_izgara_doner() -> None:
    board = _servis().board(date(2020, 1, 1), datetime.now(UTC))

    assert board.rows == []
    assert board.plans == []
    assert board.kpi.total == 0
    assert board.kpi.completion_percent is None
    assert board.kpi.all_clear is False


def test_plan_kapsamadigi_sube_bos_hucre_sorun_degil() -> None:
    """Boş hücre (plan o şubeyi kapsamıyor) istisna sayılmaz."""
    board = _servis().board(_dun(), datetime.now(UTC))
    hucreler = [c for r in board.rows for c in r.cells]

    assert all(c.status is not None for c in hucreler)  # tohumda hepsi kapsamda
    bos = type(hucreler[0])(plan_id=hucreler[0].plan_id, run_id=None, status=None)
    assert bos.exception is False


# --- uç nokta ---------------------------------------------------------


@pytest.fixture
def istemci() -> TestClient:
    return oturum_ac(TestClient(create_app(Settings())))


def test_uc_nokta_pano(istemci: TestClient) -> None:
    yanit = istemci.get(f"/api/v1/dashboard?business_day={_dun().isoformat()}")

    assert yanit.status_code == 200
    govde = yanit.json()
    assert govde["exception_row_count"] == 2
    assert len(govde["rows"]) == 3
    assert govde["kpi"]["completion_percent"] == 67
    usk = next(r for r in govde["rows"] if r["branch_name"] == "Üsküdar")
    assert usk["cells"][0]["late"] is True
    assert usk["cells"][0]["result"] == "failed"


def test_uc_nokta_varsayilan_gun_bugun(istemci: TestClient) -> None:
    yanit = istemci.get("/api/v1/dashboard")

    assert yanit.status_code == 200
    # Hesabın saat dilimine göre (BR-01), UTC'ye göre değil: İstanbul'da
    # 00:30 ile 03:00 arası UTC hâlâ dünü gösteriyor ve kapanış vardiyası
    # tam o saatlerde çalışıyor.
    bugun_trt = datetime.now(ZoneInfo("Europe/Istanbul")).date()
    assert yanit.json()["business_day"] == bugun_trt.isoformat()
