"""Aksiyon kullanım senaryoları (ST-064, ST-065, ST-069, ST-152).

Otomatik oluşturma **idempotenttir**: aksiyonun kimliği kaynağından
türer, yani zamanlayıcı kaç tur atarsa atsın kaçırılan bir liste için
tek aksiyon açılır (FR-0903).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID, uuid4

from talimatname.domain.actions import Action, ActionSource, Priority, due_at, from_missed_run
from talimatname.domain.errors import DomainError, ErrorKind
from talimatname.services.organization import OrganizationRepository
from talimatname.services.plans import PlanRepository


class ActionNotFound(DomainError):
    code = "aksiyon-bulunamadi"
    title = "Aksiyon bulunamadı"
    kind: ErrorKind = "not_found"


class ActionAlreadyClosed(DomainError):
    code = "aksiyon-kapali"
    title = "Aksiyon zaten kapatılmış"
    kind: ErrorKind = "conflict"


class BranchUnknown(DomainError):
    code = "sube-bulunamadi"
    title = "Şube bulunamadı"
    kind: ErrorKind = "not_found"


class ActionRepository(Protocol):
    def actions(self) -> list[Action]: ...

    def action(self, action_id: UUID) -> Action | None: ...

    def save_action(self, action: Action) -> None: ...


class ActionService:
    def __init__(
        self,
        repo: ActionRepository,
        org: OrganizationRepository,
        plans: PlanRepository,
        *,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._repo = repo
        self._org = org
        self._plans = plans
        self._now = now

    # --- okuma -------------------------------------------------------

    def list_actions(
        self,
        *,
        branch_id: UUID | None = None,
        status: str | None = "open",
        only_overdue: bool = False,
    ) -> list[Action]:
        """Varsayılan: açık aksiyonlar, **vadesi yakın olan önce**."""
        an = self._now()
        sonuc = self._repo.actions()
        if status in ("open", "closed"):
            sonuc = [a for a in sonuc if a.status == status]
        if branch_id is not None:
            sonuc = [a for a in sonuc if a.branch_id == branch_id]
        if only_overdue:
            sonuc = [a for a in sonuc if a.overdue(an)]
        return sorted(sonuc, key=lambda a: (a.status == "closed", a.due_at))

    def get(self, action_id: UUID) -> Action:
        aksiyon = self._repo.action(action_id)
        if aksiyon is None:
            raise ActionNotFound(f"Aksiyon id: {action_id}")
        return aksiyon

    def counts(self, branch_ids: set[UUID] | None = None) -> dict[str, int]:
        """`branch_ids` verilirse sayaçlar o şubelerle sınırlı (kapsam, FR-0205)."""
        an = self._now()
        acik = [a for a in self._repo.actions() if a.status == "open"]
        if branch_ids is not None:
            acik = [a for a in acik if a.branch_id in branch_ids]
        return {
            "open": len(acik),
            "overdue": sum(1 for a in acik if a.overdue(an)),
            "critical": sum(1 for a in acik if a.priority == "critical"),
        }

    # --- yazma -------------------------------------------------------

    def create_manual(
        self,
        *,
        branch_id: UUID,
        title: str,
        priority: Priority = "normal",
        description: str | None = None,
        assignee_user_id: UUID | None = None,
    ) -> Action:
        """Elle aksiyon (FR-0908). Yetki denetimi uç noktada yapılır."""
        if all(b.id != branch_id for b in self._org.branches()):
            raise BranchUnknown(f"Şube id: {branch_id}")
        an = self._now()
        aksiyon = Action(
            id=uuid4(),
            branch_id=branch_id,
            title=title,
            source="manual",
            priority=priority,
            opened_at=an,
            due_at=due_at(priority, an),
            description=description,
            assignee_user_id=assignee_user_id,
        ).validated()
        self._repo.save_action(aksiyon)
        return aksiyon

    def close(self, action_id: UUID, note: str, by: UUID | None = None) -> Action:
        aksiyon = self.get(action_id)
        if aksiyon.status == "closed":
            raise ActionAlreadyClosed(f"Aksiyon id: {action_id}")
        kapali = aksiyon.close(note, self._now(), by)
        self._repo.save_action(kapali)
        return kapali

    def sync_from_runs(self) -> int:
        """Kaçırılan çalıştırmalar için aksiyon açar; açılan sayısını döner.

        Zamanlayıcı her turda çağırır. Kimlik çalıştırmadan türediği için
        tekrar çağrı yeni aksiyon üretmez (FR-0903).
        """
        plan_adlari = {p.id: p.name for p in self._plans.plans()}
        mevcut = {a.id for a in self._repo.actions()}
        an = self._now()
        acilan = 0
        for run in self._plans.runs():
            if run.status != "missed":
                continue
            aksiyon = from_missed_run(
                run_id=run.id,
                branch_id=run.branch_id,
                plan_name=plan_adlari.get(run.plan_id, "Liste"),
                business_day=run.business_day,
                now=an,
            )
            if aksiyon.id in mevcut:
                continue
            self._repo.save_action(aksiyon)
            mevcut.add(aksiyon.id)
            acilan += 1
        return acilan

    @staticmethod
    def source_label(source: ActionSource) -> str:
        from talimatname.domain.actions import SOURCE_LABELS

        return SOURCE_LABELS[source]
