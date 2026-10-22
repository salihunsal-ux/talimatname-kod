"""Operasyon panosu okuma modeli (ST-077, ST-078; FR-1201, FR-1219).

Pano **istisna odaklıdır**: varsayılan görünüm yalnızca sorunlu satırları
listeler, "her şey yolunda" ise bunu açıkça söyler (E-4). 100 şubelik bir
zincirde 100 yeşil hücreye bakmak kimsenin işine yaramıyor; bakılması
gereken üç satırı bulmak yarıyor.

Burası yazma yapmaz: çalıştırmaları, planları ve şubeleri birleştirip
ızgaraya çevirir.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from talimatname.domain.plans import Run, RunResult, RunStatus
from talimatname.services.organization import OrganizationRepository
from talimatname.services.plans import PlanRepository

#: Izgarada "sorun" sayılan durumlar: bakılması gerekenler.
EXCEPTION_STATES: frozenset[str] = frozenset({"missed", "failed"})


@dataclass(frozen=True, slots=True)
class Cell:
    plan_id: UUID
    run_id: UUID | None
    status: RunStatus | None
    late: bool = False
    result: RunResult | None = None
    window_start: datetime | None = None
    window_end: datetime | None = None

    @property
    def exception(self) -> bool:
        if self.status is None:
            return False  # plan o şubeyi kapsamıyor: boş hücre sorun değil
        return self.status in EXCEPTION_STATES or (self.result == "failed") or self.late


@dataclass(frozen=True, slots=True)
class Row:
    branch_id: UUID
    branch_name: str
    region_name: str | None
    cells: list[Cell] = field(default_factory=list)

    @property
    def exception(self) -> bool:
        return any(c.exception for c in self.cells)


@dataclass(frozen=True, slots=True)
class Kpi:
    total: int
    submitted: int
    late: int
    missed: int
    open_now: int
    completion_percent: int | None

    @property
    def all_clear(self) -> bool:
        """ "Her şey yolunda" yalnızca **gün bittiğinde** söylenebilir.

        Henüz penceresi açık çalıştırma varken bunu demek yanıltıcı
        olurdu: sorun yok değil, daha olmadı.
        """
        return self.total > 0 and self.missed == 0 and self.late == 0 and self.open_now == 0


@dataclass(frozen=True, slots=True)
class Board:
    business_day: str
    plans: list[tuple[UUID, str]]
    rows: list[Row]
    kpi: Kpi

    @property
    def exception_rows(self) -> list[Row]:
        return [r for r in self.rows if r.exception]


class DashboardService:
    def __init__(self, plans: PlanRepository, org: OrganizationRepository) -> None:
        self._plans = plans
        self._org = org

    def board(self, business_day: object, now: datetime) -> Board:
        runs = [r for r in self._plans.runs() if r.business_day == business_day]
        planlar = {p.id: p for p in self._plans.plans()}
        # Sütunlar: o gün çalıştırması olan planlar (alfabetik).
        kolonlar = sorted(
            {r.plan_id for r in runs},
            key=lambda pid: planlar[pid].name.casefold() if pid in planlar else "",
        )

        bolgeler = {bolge.id: bolge.name for bolge in self._org.regions()}
        subeler = {b.id: b for b in self._org.branches()}
        bolge_adi = {
            b.id: (bolgeler.get(b.region_id) if b.region_id else None) for b in subeler.values()
        }

        hucreler: dict[tuple[UUID, UUID], Run] = {(r.branch_id, r.plan_id): r for r in runs}
        satirlar: list[Row] = []
        for branch_id in sorted(
            {r.branch_id for r in runs},
            key=lambda bid: subeler[bid].name.casefold() if bid in subeler else "",
        ):
            sube = subeler.get(branch_id)
            satirlar.append(
                Row(
                    branch_id=branch_id,
                    branch_name=sube.name if sube else "—",
                    region_name=bolge_adi.get(branch_id),
                    cells=[
                        self._cell(hucreler.get((branch_id, pid)), pid, now) for pid in kolonlar
                    ],
                )
            )

        return Board(
            business_day=str(business_day),
            plans=[(pid, planlar[pid].name if pid in planlar else "—") for pid in kolonlar],
            rows=satirlar,
            kpi=self._kpi(runs, now),
        )

    @staticmethod
    def _cell(run: Run | None, plan_id: UUID, now: datetime) -> Cell:
        if run is None:
            return Cell(plan_id=plan_id, run_id=None, status=None)
        durum, gec = run.state_at(now)
        return Cell(
            plan_id=plan_id,
            run_id=run.id,
            status=durum,
            late=gec,
            result=run.result,
            window_start=run.window_start,
            window_end=run.window_end,
        )

    @staticmethod
    def _kpi(runs: list[Run], now: datetime) -> Kpi:
        durumlar = [run.state_at(now) for run in runs]
        gonderilen = sum(1 for d, _ in durumlar if d == "submitted")
        gec = sum(1 for d, g in durumlar if d == "submitted" and g)
        kacirilan = sum(1 for d, _ in durumlar if d == "missed")
        acik = sum(1 for d, _ in durumlar if d in ("scheduled", "in_progress"))
        sayilan = len([d for d, _ in durumlar if d != "cancelled"])
        return Kpi(
            total=len(runs),
            submitted=gonderilen,
            late=gec,
            missed=kacirilan,
            open_now=acik,
            completion_percent=round(gonderilen / sayilan * 100) if sayilan else None,
        )
