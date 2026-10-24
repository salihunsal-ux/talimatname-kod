"""Plan ve çalıştırma kullanım senaryoları (ST-025, ST-026, ST-028, ST-029).

Çalıştırma üretimi burada **ufuk** kavramıyla çalışır: bugünden itibaren
sabit sayıda gün ileri üretilir (v1: 7 gün, FR-0513). Zamanlayıcı bunu
günde bir çağıracak; bugün panel "önizleme" ve "şimdi üret" için
kullanıyor. İki yol da aynı fonksiyona iner, ikisi de idempotenttir.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from typing import Protocol
from uuid import UUID

from talimatname.domain.errors import DomainError, ErrorKind
from talimatname.domain.plans import Plan, Run, merge_runs, plan_runs
from talimatname.services.organization import OrganizationRepository
from talimatname.services.templates import TemplateRepository

#: Kaç gün ileri çalıştırma üretilir (FR-0513).
HORIZON_DAYS = 7


class PlanNotFound(DomainError):
    code = "plan-bulunamadi"
    title = "Plan bulunamadı"
    kind: ErrorKind = "not_found"


class TemplateNotPublished(DomainError):
    code = "sablon-yayinda-degil"
    title = "Plan yalnızca yayınlanmış bir şablon sürümüne bağlanabilir"
    kind: ErrorKind = "conflict"


class BranchNotInScope(DomainError):
    code = "sube-bulunamadi"
    title = "Seçilen şube bulunamadı"
    kind: ErrorKind = "not_found"


class PlanRepository(Protocol):
    def plans(self) -> list[Plan]: ...

    def plan(self, plan_id: UUID) -> Plan | None: ...

    def save_plan(self, plan: Plan) -> None: ...

    def runs(self) -> list[Run]: ...

    def run(self, run_id: UUID) -> Run | None:
        """Tek çalıştırma. Süzgeç **depoda**: cevap yazan her istek
        tüm çalıştırma tablosunu okumamalı (mobilin en sık yolu)."""
        ...

    def runs_for_plan(self, plan_id: UUID, *, since: date | None = None) -> list[Run]: ...

    def runs_for_day(self, business_day: date) -> list[Run]: ...

    def runs_between(self, first_day: date, last_day: date) -> list[Run]:
        """Aralık okuması: aylık rapor bir ayı okur, tüm tabloyu değil."""
        ...

    def save_run(self, run: Run) -> None: ...

    def save_runs(self, runs: list[Run]) -> None:
        """Toplu yazma: **tek iş birimi**.

        Ufuk üretimi bir seferde onlarca çalıştırma yazıyor; her birini
        ayrı işlemde yazmak uzak veritabanında kayıt başına ~250 ms
        demek (8 şube × 7 gün ≈ 14 sn). Bellek içi adaptörde döngü,
        SQL adaptöründe tek işlem.
        """
        ...

    def delete_run(self, run_id: UUID) -> None: ...

    def delete_runs(self, run_ids: list[UUID]) -> None: ...


class PlanService:
    def __init__(
        self,
        repo: PlanRepository,
        org: OrganizationRepository,
        templates: TemplateRepository,
        *,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._repo = repo
        self._org = org
        self._templates = templates
        self._now = now

    # --- okuma -------------------------------------------------------

    def list_plans(self, *, include_inactive: bool = False) -> list[Plan]:
        return sorted(
            (p for p in self._repo.plans() if include_inactive or p.active),
            key=lambda p: p.name.casefold(),
        )

    def get(self, plan_id: UUID) -> Plan:
        plan = self._repo.plan(plan_id)
        if plan is None:
            raise PlanNotFound(f"Plan id: {plan_id}")
        return plan

    def preview(self, plan: Plan, *, days: int = HORIZON_DAYS) -> list[Run]:
        """Planı **kaydetmeden** üretilecek çalıştırmaları gösterir (FR-0511).

        Plan editöründeki "7 gün önizleme" budur: kullanıcı kuralı yanlış
        kurduğunda bunu kaydetmeden önce görür. Pencere, planın başlangıç
        tarihinden sayılır: ileri tarihli planda boş liste göstermek
        önizlemeyi işe yaramaz hâle getirirdi.
        """
        ilk = max(self._now().date(), plan.rule.starts_on)
        return self._generate(plan, ilk, ilk + timedelta(days=days - 1))

    def runs_for_day(self, business_day: date) -> list[Run]:
        return sorted(
            (r for r in self._repo.runs_for_day(business_day)),
            key=lambda r: (r.window_start, str(r.branch_id)),
        )

    # --- yazma -------------------------------------------------------

    def create(self, plan: Plan) -> Plan:
        hazir = self._validate(plan)
        self._repo.save_plan(hazir)
        self.generate(hazir.id)
        return hazir

    def update(self, plan_id: UUID, **degisiklik: object) -> Plan:
        mevcut = self.get(plan_id)
        guncel = self._validate(replace(mevcut, **degisiklik))  # type: ignore[arg-type]
        self._repo.save_plan(guncel)
        self.generate(plan_id)
        return guncel

    def set_active(self, plan_id: UUID, active: bool) -> Plan:
        return self.update(plan_id, active=active)

    def generate_all(self, *, days: int = HORIZON_DAYS) -> tuple[int, int]:
        """Etkin planların tamamı için üretim — zamanlayıcının işi (ST-027).

        Zamanlayıcı yazılana kadar bunu uygulama açılışı ve uç nokta
        tetikliyor; ikisi de aynı idempotent yolu kullanıyor.
        """
        eklenen = silinen = 0
        for plan in self._repo.plans():
            e, s = self.generate(plan.id, days=days)
            eklenen += e
            silinen += s
        return eklenen, silinen

    def generate(self, plan_id: UUID, *, days: int = HORIZON_DAYS) -> tuple[int, int]:
        """Ufuk içindeki çalıştırmaları üretir; (eklenen, silinen) döner.

        Pasif planda yeni çalıştırma üretilmez; başlanmamış olanlar silinir.
        """
        plan = self.get(plan_id)
        bugun = self._now().date()
        son = bugun + timedelta(days=days - 1)

        yeni = self._generate(plan, bugun, son) if plan.active else []
        mevcut = self._repo.runs_for_plan(plan_id, since=bugun)
        kaydedilecek, silinecek = merge_runs(mevcut, yeni)

        # Toplu: üretim bir seferde onlarca satır yazıyor, her birini
        # ayrı işlemde yazmak uzak veritabanında dakikalara çıkıyordu.
        if kaydedilecek:
            self._repo.save_runs(kaydedilecek)
        if silinecek:
            self._repo.delete_runs([run.id for run in silinecek])
        return len(kaydedilecek), len(silinecek)

    # --- yardımcılar --------------------------------------------------

    def _generate(self, plan: Plan, ilk: date, son: date) -> list[Run]:
        sonuc: list[Run] = []
        for branch_id in plan.branch_ids:
            sube = self._org.branch(branch_id)
            if sube is None or sube.status != "active":
                continue  # pasif şubeye çalıştırma üretilmez
            sonuc.extend(plan_runs(plan, branch_id, sube.calendar(), ilk, son))
        return sorted(sonuc, key=lambda r: (r.window_start, str(r.branch_id)))

    def _validate(self, plan: Plan) -> Plan:
        hazir = plan.validated()
        surum = self._templates.version(hazir.template_version_id)
        if surum is None or surum.status != "published":
            raise TemplateNotPublished(f"Sürüm id: {hazir.template_version_id}")
        bilinen = {b.id for b in self._org.branches()}
        for branch_id in hazir.branch_ids:
            if branch_id not in bilinen:
                raise BranchNotInScope(f"Şube id: {branch_id}")
        return hazir
