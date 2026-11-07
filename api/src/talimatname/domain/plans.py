"""Plan ve çalıştırma (CAP-05; FR-0501…0521).

Plan, **şablon sürümü + kapsam + zaman kuralı + atama** demektir. Plandan
türeyen her çalıştırma belirli bir şubeye ve iş gününe aittir; zamanı
pencere motoru hesaplar (`domain/window.py`).

Üç kural burada:

* **Tekillik** (FR-0513): aynı (plan, şube, iş günü, pencere başlangıcı)
  için tek çalıştırma. Üretim tekrar koşturulduğunda kopya çıkmaz.
* **Plan değişikliği geçmişi bozmaz** (FR-0516): başlanmamış çalıştırmalar
  yeniden hesaplanır, başlanmış ya da gönderilmiş olanlar korunur.
* **Durum zamandan türetilir**: "kaçırıldı" bir iş değil, tolerans
  bitiminden sonra bakıldığında ortaya çıkan sonuçtur (BR-02/03).
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from typing import Literal
from uuid import UUID, uuid5

from talimatname.domain.validation import ValidationError, clean_name
from talimatname.domain.window import BranchCalendar, Window, WindowRule, windows

AssignmentKind = Literal["anyone", "role", "user"]
RunStatus = Literal["scheduled", "in_progress", "submitted", "missed", "cancelled"]
RunResult = Literal["passed", "failed"]

#: Durum ve sonucun Türkçe karşılığı. Sunucuda duruyor çünkü PDF
#: (FR-1213) panelden geçmeden üretiliyor; panelin kendi sözlüğü
#: ekran metinleri için ayrı kalıyor.
RUN_STATUS_LABELS: dict[str, str] = {
    "scheduled": "Planlı",
    "in_progress": "Devam ediyor",
    "submitted": "Tamamlandı",
    "missed": "Kaçırıldı",
    "cancelled": "Yapılmayacak",
}

RUN_RESULT_LABELS: dict[str, str] = {
    "passed": "Başarılı",
    "failed": "Başarısız",
}

#: Çalıştırma kimlikleri tohumlanabilir olsun diye sabit ad alanı: aynı
#: (plan, şube, iş günü, pencere) her zaman aynı id'yi verir (FR-0513).
RUN_NAMESPACE = UUID("3a7c1f5e-9b2d-4c8a-8f1e-2d6b4a9c7e30")


@dataclass(frozen=True, slots=True)
class Assignment:
    """Çalıştırmayı kimin yapacağı (v1: FR-0508).

    * `anyone` — şubedeki herkes görür, **ilk açan alır** (çalıştırma kilidi)
    * `role` — o şubede o role sahip herkes
    * `user` — belirli kişi
    """

    kind: AssignmentKind = "anyone"
    role: str | None = None
    user_id: UUID | None = None

    def validated(self) -> Assignment:
        if self.kind == "role" and not self.role:
            raise ValidationError("assignment", "Rol ataması için rol seçilmeli")
        if self.kind == "user" and self.user_id is None:
            raise ValidationError("assignment", "Kişi ataması için kullanıcı seçilmeli")
        return self


@dataclass(frozen=True, slots=True)
class Plan:
    id: UUID
    name: str
    template_version_id: UUID
    branch_ids: tuple[UUID, ...]
    rule: WindowRule
    assignment: Assignment = Assignment()
    active: bool = True

    def validated(self) -> Plan:
        if not self.branch_ids:
            raise ValidationError("branch_ids", "En az bir şube seçilmeli")
        if len(set(self.branch_ids)) != len(self.branch_ids):
            raise ValidationError("branch_ids", "Aynı şube iki kez seçilemez")
        return replace(
            self,
            name=clean_name(self.name, "name"),
            assignment=self.assignment.validated(),
        )


@dataclass(frozen=True, slots=True)
class Run:
    """Tek bir şubenin tek bir iş günündeki çalıştırması."""

    id: UUID
    plan_id: UUID
    template_version_id: UUID
    branch_id: UUID
    business_day: date
    window_start: datetime
    window_end: datetime
    tolerance_end: datetime
    status: RunStatus = "scheduled"
    result: RunResult | None = None
    score_percent: int | None = None
    submitted_at: datetime | None = None
    locked_by: UUID | None = None
    cancel_reason: str | None = None

    @property
    def started(self) -> bool:
        """Dokunulmuş mu? Plan değişikliğinde korunacaklar bunlar."""
        return self.status != "scheduled"

    def writable_from(self, prep_minutes: int) -> datetime:
        """Listeye ilk cevabın yazılabileceği an (BR-02 hazırlık payı).

        Pencere başlangıcından `prep_minutes` kadar önce açılır: vardiya
        erken başladığında liste elde olsun diye. Öncesinde yazmak
        yasak — yoksa akşamki kapanış sabahtan işaretlenebilirdi ve
        "pencere içi" ölçüsü (FR-1203) anlamını yitirirdi.
        """
        return self.window_start - timedelta(minutes=prep_minutes)

    def state_at(self, now: datetime) -> tuple[RunStatus, bool]:
        """(durum, geç mi) — zamana göre türetilmiş görünüm.

        Depodaki `status` niyeti tutar; "kaçırıldı" ve "geç" zamandan
        çıkar. Böylece zamanlayıcı geç kalsa bile pano doğru gösterir.
        """
        if self.status in ("cancelled", "submitted"):
            gec = bool(self.submitted_at and self.submitted_at > self.window_end)
            return self.status, gec
        if now >= self.tolerance_end:
            return "missed", False
        return self.status, False


def run_id(plan_id: UUID, branch_id: UUID, window: Window) -> UUID:
    """Çalıştırmanın tekil kimliği (FR-0513): aynı pencere → aynı id."""
    return uuid5(
        RUN_NAMESPACE,
        f"{plan_id}:{branch_id}:{window.business_day.isoformat()}:{window.window_start.isoformat()}",
    )


def plan_runs(
    plan: Plan,
    branch_id: UUID,
    calendar: BranchCalendar,
    first_day: date,
    last_day: date,
) -> list[Run]:
    """Planın bir şube için [first_day, last_day] aralığındaki çalıştırmaları."""
    return [
        Run(
            id=run_id(plan.id, branch_id, pencere),
            plan_id=plan.id,
            template_version_id=plan.template_version_id,
            branch_id=branch_id,
            business_day=pencere.business_day,
            window_start=pencere.window_start,
            window_end=pencere.window_end,
            tolerance_end=pencere.tolerance_end,
        )
        for pencere in windows(plan.rule, calendar, first_day, last_day)
    ]


def merge_runs(mevcut: list[Run], yeni: list[Run]) -> tuple[list[Run], list[Run]]:
    """Yeniden üretimde korunacak ve yazılacak çalıştırmaları ayırır (FR-0516).

    Dönen: (kaydedilecekler, silinecekler).

    * Başlanmış çalıştırma (durum `scheduled` değil) **asla** silinmez ve
      üzerine yazılmaz: içinde cevap ve kanıt olabilir.
    * Başlanmamış ve artık üretilmeyen çalıştırma silinir — plan
      değişikliğinin amacı budur.
    """
    mevcut_ile = {r.id: r for r in mevcut}
    yeni_ile = {r.id: r for r in yeni}

    kaydedilecek = [r for r in yeni if r.id not in mevcut_ile]
    silinecek = [r for r in mevcut if r.id not in yeni_ile and not r.started]
    return kaydedilecek, silinecek
