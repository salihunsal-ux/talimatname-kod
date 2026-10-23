"""Zamanlayıcı işleri (ST-027; FR-0513, FR-0514).

Zamanlayıcı **iki** iş yapar ve ikisi de idempotenttir:

1. **Ufuk üretimi** — etkin planların önümüzdeki 7 günlük çalıştırmaları
   (FR-0513). Aynı pencere ikinci kez üretilmez.
2. **Kapanış** — toleransı dolmuş, hâlâ başlanmamış ya da yarım kalmış
   çalıştırmaları `missed` olarak **kalıcı** işaretler (FR-0514), ve
   kaçırılan her liste için aksiyon açar (FR-0902; idempotent).

İkinci iş neden gerekli? Pano "kaçırıldı"yı zaten zamandan türetiyor
(`Run.state_at`), yani ekran için yazmaya gerek yok. Ama kaçırma bir
**olaydır**: aksiyon açacak (ST-064) ve bildirim tetikleyecek (ST-066).
Olayın bir kez olması için durumun bir kez yazılması gerekir.

Mimaride zamanlayıcı ayrı bir süreçtir (01-teknik-mimari `SCH`); bu
modül onun iş mantığıdır, döngüsü `talimatname.scheduler`'da.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime

from talimatname.services.actions import ActionService
from talimatname.services.organization import OrganizationRepository
from talimatname.services.plans import HORIZON_DAYS, PlanRepository, PlanService
from talimatname.services.templates import TemplateRepository


@dataclass(frozen=True, slots=True)
class TickResult:
    """Bir turun özeti — günlüğe ve `/scheduler/tick` yanıtına gider."""

    at: datetime
    created: int
    deleted: int
    missed: int
    actions_opened: int = 0

    @property
    def quiet(self) -> bool:
        return (
            self.created == 0
            and self.deleted == 0
            and self.missed == 0
            and self.actions_opened == 0
        )


class SchedulerService:
    def __init__(
        self,
        plans: PlanRepository,
        org: OrganizationRepository,
        templates: TemplateRepository,
        actions: ActionService | None = None,
        *,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._repo = plans
        self._plans = PlanService(plans, org, templates, now=now)
        self._actions = actions
        self._now = now

    def tick(self, *, days: int = HORIZON_DAYS) -> TickResult:
        an = self._now()
        eklenen, silinen = self._plans.generate_all(days=days)
        kacirilan = self.close_expired(an)
        # Kaçırma bir olaydır: aksiyonu burada açılır (FR-0902), çünkü
        # "kaçırıldı" durumunu yazan da bu turdur.
        acilan = self._actions.sync_from_runs() if self._actions else 0
        return TickResult(
            at=an, created=eklenen, deleted=silinen, missed=kacirilan, actions_opened=acilan
        )

    def close_expired(self, now: datetime) -> int:
        """Toleransı dolmuş çalıştırmaları `missed` olarak yazar.

        Yalnızca `scheduled` ve `in_progress` olanlar kapanır: gönderilmiş
        ya da "yapılmayacak" işaretlenmiş çalıştırmaya dokunulmaz.
        """
        sayac = 0
        for run in self._repo.runs():
            if run.status not in ("scheduled", "in_progress"):
                continue
            if now < run.tolerance_end:
                continue
            self._repo.save_run(replace(run, status="missed"))
            sayac += 1
        return sayac
