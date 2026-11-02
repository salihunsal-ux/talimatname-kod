"""Operasyon panosu uç noktası (ST-077, ST-078; FR-1201, FR-1219)."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from talimatname.api.bagimliliklar import organizasyon_servisi, pano_servisi
from talimatname.api.guvenlik import Mudur
from talimatname.services.dashboard import Board, DashboardService
from talimatname.services.organization import (
    OrganizationService,
    erisilebilir_sube_idleri,
)

router = APIRouter(tags=["pano"])

Servis = Annotated[DashboardService, Depends(pano_servisi)]
OrgServis = Annotated[OrganizationService, Depends(organizasyon_servisi)]


class Hucre(BaseModel):
    plan_id: UUID
    run_id: UUID | None = None
    status: Literal["scheduled", "in_progress", "submitted", "missed", "cancelled"] | None = None
    late: bool = False
    result: Literal["passed", "failed"] | None = None
    window_start: datetime | None = None
    window_end: datetime | None = None
    exception: bool = False


class Satir(BaseModel):
    branch_id: UUID
    branch_name: str
    region_name: str | None = None
    cells: list[Hucre]
    exception: bool


class Gostergeler(BaseModel):
    total: int
    submitted: int
    late: int
    missed: int
    open_now: int = Field(description="Henüz penceresi kapanmamış çalıştırma sayısı")
    completion_percent: int | None
    all_clear: bool = Field(description="Kaçırılan ve geç yoksa true: 'her şey yolunda'")


class PlanSutunu(BaseModel):
    id: UUID
    name: str


class PanoYaniti(BaseModel):
    """Şube × liste ızgarası.

    İstisna süzgeci **istemcide** uygulanır: sunucu her satırı `exception`
    bayrağıyla gönderir, panel varsayılanda yalnızca bayraklıları gösterir
    ve "tümünü göster" dediğinde ikinci istek atmaz (FR-1219).
    """

    business_day: date
    plans: list[PlanSutunu]
    rows: list[Satir]
    exception_row_count: int
    kpi: Gostergeler


def _yanit(board: Board) -> PanoYaniti:
    return PanoYaniti(
        business_day=date.fromisoformat(board.business_day),
        plans=[PlanSutunu(id=pid, name=ad) for pid, ad in board.plans],
        rows=[
            Satir(
                branch_id=satir.branch_id,
                branch_name=satir.branch_name,
                region_name=satir.region_name,
                cells=[
                    Hucre(
                        plan_id=hucre.plan_id,
                        run_id=hucre.run_id,
                        status=hucre.status,
                        late=hucre.late,
                        result=hucre.result,
                        window_start=hucre.window_start,
                        window_end=hucre.window_end,
                        exception=hucre.exception,
                    )
                    for hucre in satir.cells
                ],
                exception=satir.exception,
            )
            for satir in board.rows
        ],
        exception_row_count=len(board.exception_rows),
        kpi=Gostergeler(
            total=board.kpi.total,
            submitted=board.kpi.submitted,
            late=board.kpi.late,
            missed=board.kpi.missed,
            open_now=board.kpi.open_now,
            completion_percent=board.kpi.completion_percent,
            all_clear=board.kpi.all_clear,
        ),
    )


@router.get("/dashboard", summary="Operasyon panosu (şube × liste)")
def pano(
    servis: Servis,
    org: OrgServis,
    kullanici: Mudur,
    business_day: date | None = None,
) -> PanoYaniti:
    """Izgara kullanıcının kapsamıyla sınırlı (FR-0205).

    Göstergeler de süzülmüş satırlardan hesaplanır: bölge müdürü kendi
    bölgesinin tamamlanma oranını görür, zincirin değil.
    """
    gun = business_day or datetime.now(UTC).date()
    tahta = servis.board(gun, datetime.now(UTC), erisilebilir_sube_idleri(kullanici, org))
    return _yanit(tahta)
