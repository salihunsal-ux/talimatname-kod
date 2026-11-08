"""Operasyon panosu uç noktası (ST-077, ST-078; FR-1201, FR-1219)."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from talimatname.api.bagimliliklar import (
    kullanici_servisi,
    kurulum_servisi,
    organizasyon_servisi,
    pano_servisi,
)
from talimatname.api.guvenlik import Gozlemci
from talimatname.api.is_gunu import bugun
from talimatname.domain.escalation_gaps import STEP_LABELS, EscalationGap, escalation_gaps
from talimatname.services.dashboard import Board, DashboardService
from talimatname.services.organization import (
    OrganizationService,
    erisilebilir_sube_idleri,
)
from talimatname.services.setup import SetupService
from talimatname.services.users import UserService

router = APIRouter(tags=["pano"])

Servis = Annotated[DashboardService, Depends(pano_servisi)]
OrgServis = Annotated[OrganizationService, Depends(organizasyon_servisi)]
KurulumServis = Annotated[SetupService, Depends(kurulum_servisi)]
KisiServis = Annotated[UserService, Depends(kullanici_servisi)]


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
    escalation_gaps: list[EskalasyonBoslugu] = Field(
        description="Uyarının şube müdürüne ulaşmadığı şubeler (BR-11, FR-0915)"
    )


class EskalasyonBoslugu(BaseModel):
    """Bu şubede uyarı kime gidiyor.

    Eskalasyon merdiveni atlanan basamağı yalnızca günlüğe yazıyordu;
    kimsenin görmediği bir uyarı, uyarı değildir.
    """

    branch_id: UUID
    branch_code: str
    branch_name: str
    missing: list[str] = Field(description="Bulunamayan basamakların Türkçe adı")
    reached: str = Field(description="Uyarının gerçekte ulaştığı basamak")
    reached_label: str
    critical: bool = Field(description="Hiç kimseye ulaşmıyor")


def _yanit(board: Board, bosluklar: list[EscalationGap]) -> PanoYaniti:
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
        escalation_gaps=[
            EskalasyonBoslugu(
                branch_id=b.branch_id,
                branch_code=b.branch_code,
                branch_name=b.branch_name,
                missing=[STEP_LABELS[a] for a in b.missing],
                reached=b.reached,
                reached_label=STEP_LABELS[b.reached],
                critical=b.critical,
            )
            for b in bosluklar
        ],
    )


@router.get("/dashboard", summary="Operasyon panosu (şube × liste)")
def pano(
    servis: Servis,
    org: OrgServis,
    kullanici: Gozlemci,
    kurulum: KurulumServis,
    kisiler: KisiServis,
    business_day: date | None = None,
) -> PanoYaniti:
    """Izgara kullanıcının kapsamıyla sınırlı (FR-0205).

    Göstergeler de süzülmüş satırlardan hesaplanır: bölge müdürü kendi
    bölgesinin tamamlanma oranını görür, zincirin değil.
    """
    gun = business_day or bugun(kurulum)
    kapsam = erisilebilir_sube_idleri(kullanici, org)
    tahta = servis.board(gun, datetime.now(UTC), kapsam)
    # Eskalasyon boşlukları da kapsamla sınırlı: bölge müdürü kendi
    # bölgesinin eksiğini görür, zincirin tamamını değil (FR-0205).
    subeler = [s for dugum in org.tree() for s in dugum.branches if s.id in kapsam]
    return _yanit(tahta, escalation_gaps(subeler, kisiler.list_users(include_inactive=True)))
