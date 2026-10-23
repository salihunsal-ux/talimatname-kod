"""Portların PostgreSQL karşılıkları (ADR-0014 md.2).

Servis katmanı bu dosyayı tanımaz: aynı portları bellek içi adaptör de
uyguluyor ve aynı testler ikisini de geçiyor. Buradaki tek iş **eşleme**:
alan nesnesi ↔ satır.

Her çağrı kendi kiracı oturumunu açar (`tenant_session`). Kısa işlemler
tercih edildi: uzun süren bir oturumu servis katmanına taşımak,
kalıcılığı servis katmanına sızdırmak olurdu.
"""

from __future__ import annotations

from datetime import time
from typing import Any
from uuid import UUID, uuid5

from sqlalchemy import delete, select

from talimatname.domain.actions import Action
from talimatname.domain.answers import Answer, RunLock
from talimatname.domain.organization import Branch, Region, Station
from talimatname.domain.plans import Assignment, Plan, Run
from talimatname.domain.templates import (
    ChoiceOption,
    Item,
    Section,
    Template,
    TemplateVersion,
    VersionSettings,
)
from talimatname.domain.users import RoleAssignment, User
from talimatname.domain.window import Anchor, BusinessHours, WindowRule
from talimatname.infra.db import models as m
from talimatname.infra.db.session import tenant_session

WEEKDAYS = (0, 1, 2, 3, 4, 5, 6)

#: Rol atamasının kararlı kimliği: aynı (kullanıcı, rol, kapsam) → aynı satır.
ROLE_NS = UUID("1c0e5a7b-9d34-4f21-8b6e-3a7c2d19f480")


class _TenantRepository:
    def __init__(self, tenant_id: UUID) -> None:
        self._tenant = tenant_id


# --------------------------------------------------------------------- org


def _saatler_json(hours: dict[int, BusinessHours | None]) -> dict[str, Any]:
    return {
        str(gun): None
        if saat is None
        else [saat.open_time.isoformat(), saat.close_time.isoformat()]
        for gun, saat in hours.items()
    }


def _saatler_alan(ham: dict[str, Any]) -> dict[int, BusinessHours | None]:
    sonuc: dict[int, BusinessHours | None] = {}
    for gun in WEEKDAYS:
        deger = ham.get(str(gun))
        sonuc[gun] = (
            None
            if not deger
            else BusinessHours(time.fromisoformat(deger[0]), time.fromisoformat(deger[1]))
        )
    return sonuc


def _branch(satir: m.Branch) -> Branch:
    return Branch(
        id=satir.id,
        code=satir.code,
        name=satir.name,
        timezone=satir.timezone,
        business_hours=_saatler_alan(satir.business_hours),
        region_id=satir.region_id,
        address=satir.address,
        status=satir.status,  # type: ignore[arg-type]
    )


class SqlOrganizationRepository(_TenantRepository):
    def regions(self) -> list[Region]:
        with tenant_session(self._tenant) as o:
            return [
                Region(id=r.id, name=r.name, code=r.code) for r in o.scalars(select(m.Region)).all()
            ]

    def branches(self) -> list[Branch]:
        with tenant_session(self._tenant) as o:
            return [_branch(b) for b in o.scalars(select(m.Branch)).all()]

    def branch(self, branch_id: UUID) -> Branch | None:
        with tenant_session(self._tenant) as o:
            satir = o.get(m.Branch, branch_id)
            return _branch(satir) if satir else None

    def branch_by_code(self, code: str) -> Branch | None:
        with tenant_session(self._tenant) as o:
            satir = o.scalars(select(m.Branch).where(m.Branch.code == code)).first()
            return _branch(satir) if satir else None

    def save_branch(self, branch: Branch) -> None:
        with tenant_session(self._tenant) as o:
            satir = o.get(m.Branch, branch.id) or m.Branch(id=branch.id, tenant_id=self._tenant)
            satir.region_id = branch.region_id
            satir.code = branch.code
            satir.name = branch.name
            satir.timezone = branch.timezone
            satir.address = branch.address
            satir.status = branch.status
            satir.business_hours = _saatler_json(branch.business_hours)
            o.add(satir)

    def stations(self, branch_id: UUID) -> list[Station]:
        with tenant_session(self._tenant) as o:
            return [
                Station(id=s.id, branch_id=s.branch_id, name=s.name, kind=s.kind)  # type: ignore[arg-type]
                for s in o.scalars(select(m.Station).where(m.Station.branch_id == branch_id)).all()
            ]


# -------------------------------------------------------------------- user


class SqlUserRepository(_TenantRepository):
    def users(self) -> list[User]:
        with tenant_session(self._tenant) as o:
            satirlar = o.scalars(select(m.AppUser)).all()
            atamalar: dict[UUID, list[RoleAssignment]] = {}
            for a in o.scalars(select(m.RoleAssignment)).all():
                atamalar.setdefault(a.user_id, []).append(
                    RoleAssignment(role=a.role, scope_id=a.scope_id)  # type: ignore[arg-type]
                )
            return [self._user(s, tuple(atamalar.get(s.id, ()))) for s in satirlar]

    def user(self, user_id: UUID) -> User | None:
        return next((k for k in self.users() if k.id == user_id), None)

    def user_by_phone(self, phone: str) -> User | None:
        return next((k for k in self.users() if k.phone == phone), None)

    def save_user(self, user: User) -> None:
        with tenant_session(self._tenant) as o:
            satir = o.get(m.AppUser, user.id) or m.AppUser(id=user.id, tenant_id=self._tenant)
            satir.full_name = user.full_name
            satir.phone = user.phone
            satir.email = user.email
            satir.status = user.status
            satir.language = user.language
            satir.pin_set = user.pin_set
            satir.invited_at = user.invited_at
            satir.masked_at = user.masked_at
            o.add(satir)
            o.flush()
            # Rol atamaları küçük bir küme: sil-yaz en sade ve doğru yol.
            o.execute(delete(m.RoleAssignment).where(m.RoleAssignment.user_id == user.id))
            for atama in user.assignments:
                o.add(
                    m.RoleAssignment(
                        id=uuid5(ROLE_NS, f"{user.id}:{atama.role}:{atama.scope_id}"),
                        tenant_id=self._tenant,
                        user_id=user.id,
                        role=atama.role,
                        scope_type=atama.scope_type,
                        scope_id=atama.scope_id,
                    )
                )

    def next_mask_counter(self) -> int:
        with tenant_session(self._tenant) as o:
            maskeli = o.scalars(select(m.AppUser).where(m.AppUser.status == "masked")).all()
            return 4820 + len(maskeli) + 1

    @staticmethod
    def _user(satir: m.AppUser, atamalar: tuple[RoleAssignment, ...]) -> User:
        return User(
            id=satir.id,
            full_name=satir.full_name,
            phone=satir.phone,
            assignments=atamalar,
            email=satir.email,
            status=satir.status,  # type: ignore[arg-type]
            invited_at=satir.invited_at,
            masked_at=satir.masked_at,
            language=satir.language,
            pin_set=satir.pin_set,
        )


# ---------------------------------------------------------------- template


class SqlTemplateRepository(_TenantRepository):
    def templates(self) -> list[Template]:
        with tenant_session(self._tenant) as o:
            return [
                Template(id=t.id, name=t.name, category=t.category)
                for t in o.scalars(select(m.Template)).all()
            ]

    def template(self, template_id: UUID) -> Template | None:
        with tenant_session(self._tenant) as o:
            satir = o.get(m.Template, template_id)
            return (
                Template(id=satir.id, name=satir.name, category=satir.category) if satir else None
            )

    def save_template(self, template: Template) -> None:
        with tenant_session(self._tenant) as o:
            satir = o.get(m.Template, template.id) or m.Template(
                id=template.id, tenant_id=self._tenant
            )
            satir.name = template.name
            satir.category = template.category
            o.add(satir)

    def versions(self, template_id: UUID) -> list[TemplateVersion]:
        with tenant_session(self._tenant) as o:
            satirlar = o.scalars(
                select(m.TemplateVersion).where(m.TemplateVersion.template_id == template_id)
            ).all()
            return [self._version(o, s) for s in satirlar]

    def version(self, version_id: UUID) -> TemplateVersion | None:
        with tenant_session(self._tenant) as o:
            satir = o.get(m.TemplateVersion, version_id)
            return self._version(o, satir) if satir else None

    def save_version(self, version: TemplateVersion) -> None:
        with tenant_session(self._tenant) as o:
            satir = o.get(m.TemplateVersion, version.id) or m.TemplateVersion(
                id=version.id, tenant_id=self._tenant
            )
            satir.template_id = version.template_id
            satir.version_no = version.version_no
            satir.status = version.status
            satir.camera_only = version.settings.camera_only
            satir.published_at = version.published_at
            o.add(satir)
            o.flush()
            # Bölüm ve maddeler sürümün parçası: taslak kaydedildiğinde
            # tamamı yeniden yazılır (yayınlanmış sürüm zaten değişmez).
            eski = o.scalars(select(m.Section).where(m.Section.version_id == version.id)).all()
            for bolum in eski:
                o.execute(delete(m.Item).where(m.Item.section_id == bolum.id))
            o.execute(delete(m.Section).where(m.Section.version_id == version.id))
            o.flush()
            for alan_bolum in version.sections:
                o.add(
                    m.Section(
                        id=alan_bolum.id,
                        tenant_id=self._tenant,
                        version_id=version.id,
                        position=alan_bolum.order,
                        title=alan_bolum.title,
                    )
                )
                o.flush()
                for madde in alan_bolum.items:
                    o.add(
                        m.Item(
                            id=madde.id,
                            tenant_id=self._tenant,
                            section_id=alan_bolum.id,
                            position=madde.order,
                            type=madde.type,
                            title=madde.title,
                            hint=madde.hint,
                            required=madde.required,
                            photo_required=madde.photo_required,
                            critical=madde.critical,
                            options=[
                                {"label": o_.label, "passing": o_.passing} for o_ in madde.options
                            ],
                            min_value=madde.min_value,
                            max_value=madde.max_value,
                            unit=madde.unit,
                        )
                    )

    def _version(self, oturum: Any, satir: m.TemplateVersion) -> TemplateVersion:
        bolumler = oturum.scalars(
            select(m.Section).where(m.Section.version_id == satir.id).order_by(m.Section.position)
        ).all()
        sections = []
        for b in bolumler:
            maddeler = oturum.scalars(
                select(m.Item).where(m.Item.section_id == b.id).order_by(m.Item.position)
            ).all()
            sections.append(
                Section(
                    id=b.id,
                    order=b.position,
                    title=b.title,
                    items=tuple(
                        Item(
                            id=i.id,
                            order=i.position,
                            type=i.type,
                            title=i.title,
                            hint=i.hint,
                            required=i.required,
                            photo_required=i.photo_required,
                            critical=i.critical,
                            options=tuple(
                                ChoiceOption(label=s["label"], passing=s["passing"])
                                for s in (i.options or [])
                            ),
                            min_value=i.min_value,
                            max_value=i.max_value,
                            unit=i.unit,
                        )
                        for i in maddeler
                    ),
                )
            )
        return TemplateVersion(
            id=satir.id,
            template_id=satir.template_id,
            version_no=satir.version_no,
            status=satir.status,  # type: ignore[arg-type]
            sections=tuple(sections),
            settings=VersionSettings(camera_only=satir.camera_only),
            published_at=satir.published_at,
        )


# -------------------------------------------------------------------- plan


def _plan(satir: m.Plan) -> Plan:
    return Plan(
        id=satir.id,
        name=satir.name,
        template_version_id=satir.version_id,
        branch_ids=tuple(UUID(b) for b in satir.branch_ids),
        rule=WindowRule(
            recurrence=satir.recurrence,
            starts_on=satir.starts_on,
            duration_minutes=satir.duration_minutes,
            tolerance_minutes=satir.tolerance_minutes,
            start_time=time.fromisoformat(satir.start_time) if satir.start_time else None,
            anchor=(
                Anchor(satir.anchor_reference, satir.anchor_offset_minutes)  # type: ignore[arg-type]
                if satir.anchor_reference
                else None
            ),
        ),
        assignment=Assignment(
            kind=satir.assignment_kind,  # type: ignore[arg-type]
            role=satir.assignment_role,
            user_id=satir.assignment_user_id,
        ),
        active=satir.active,
    )


def _run(satir: m.Run) -> Run:
    return Run(
        id=satir.id,
        plan_id=satir.plan_id,
        template_version_id=satir.version_id,
        branch_id=satir.branch_id,
        business_day=satir.business_day,
        window_start=satir.window_start,
        window_end=satir.window_end,
        tolerance_end=satir.tolerance_end,
        status=satir.status,  # type: ignore[arg-type]
        result=satir.result,  # type: ignore[arg-type]
        score_percent=satir.score_percent,
        submitted_at=satir.submitted_at,
        locked_by=satir.locked_by,
        cancel_reason=satir.cancel_reason,
    )


class SqlPlanRepository(_TenantRepository):
    def plans(self) -> list[Plan]:
        with tenant_session(self._tenant) as o:
            return [_plan(p) for p in o.scalars(select(m.Plan)).all()]

    def plan(self, plan_id: UUID) -> Plan | None:
        with tenant_session(self._tenant) as o:
            satir = o.get(m.Plan, plan_id)
            return _plan(satir) if satir else None

    def save_plan(self, plan: Plan) -> None:
        with tenant_session(self._tenant) as o:
            satir = o.get(m.Plan, plan.id) or m.Plan(id=plan.id, tenant_id=self._tenant)
            satir.version_id = plan.template_version_id
            satir.name = plan.name
            satir.active = plan.active
            satir.branch_ids = [str(b) for b in plan.branch_ids]
            satir.recurrence = plan.rule.recurrence
            satir.starts_on = plan.rule.starts_on
            satir.start_time = plan.rule.start_time.isoformat() if plan.rule.start_time else None
            satir.anchor_reference = plan.rule.anchor.reference if plan.rule.anchor else None
            satir.anchor_offset_minutes = plan.rule.anchor.offset_minutes if plan.rule.anchor else 0
            satir.duration_minutes = plan.rule.duration_minutes
            satir.tolerance_minutes = plan.rule.tolerance_minutes
            satir.assignment_kind = plan.assignment.kind
            satir.assignment_role = plan.assignment.role
            satir.assignment_user_id = plan.assignment.user_id
            o.add(satir)

    def runs(self) -> list[Run]:
        with tenant_session(self._tenant) as o:
            return [_run(r) for r in o.scalars(select(m.Run)).all()]

    def save_run(self, run: Run) -> None:
        with tenant_session(self._tenant) as o:
            satir = o.get(m.Run, run.id) or m.Run(id=run.id, tenant_id=self._tenant)
            satir.plan_id = run.plan_id
            satir.version_id = run.template_version_id
            satir.branch_id = run.branch_id
            satir.business_day = run.business_day
            satir.window_start = run.window_start
            satir.window_end = run.window_end
            satir.tolerance_end = run.tolerance_end
            satir.status = run.status
            satir.result = run.result
            satir.score_percent = run.score_percent
            satir.submitted_at = run.submitted_at
            satir.locked_by = run.locked_by
            satir.cancel_reason = run.cancel_reason
            o.add(satir)

    def delete_run(self, run_id: UUID) -> None:
        with tenant_session(self._tenant) as o:
            o.execute(delete(m.Run).where(m.Run.id == run_id))


# ------------------------------------------------------------------ answer


def _answer(satir: m.Answer) -> Answer:
    return Answer(
        id=satir.id,
        run_id=satir.run_id,
        item_id=satir.item_id,
        state=satir.state,  # type: ignore[arg-type]
        value=satir.value.get("v") if isinstance(satir.value, dict) else satir.value,
        note=satir.note,
        user_id=satir.user_id,
        device_id=satir.device_id,
        answered_at=satir.answered_at,
        device_reported_at=satir.device_reported_at,
        clock_skew_minutes=satir.clock_skew_minutes,
        evidence_count=satir.evidence_count,
    )


class SqlAnswerRepository(_TenantRepository):
    """Kilit şimdilik bellekte: süreç içi, kısa ömürlü ve kritik değil.

    Kalıcı kilit (çoklu sunucu) Faz B'de gerekecek; o zaman `run` tablosundaki
    `locked_by`/`lock_renewed_at` sütunları kullanılacak — şema hazır.
    """

    def __init__(self, tenant_id: UUID) -> None:
        super().__init__(tenant_id)
        self._locks: dict[UUID, RunLock] = {}

    def answers(self, run_id: UUID) -> list[Answer]:
        with tenant_session(self._tenant) as o:
            return [
                _answer(a)
                for a in o.scalars(select(m.Answer).where(m.Answer.run_id == run_id)).all()
            ]

    def answer(self, answer_id: UUID) -> Answer | None:
        with tenant_session(self._tenant) as o:
            satir = o.get(m.Answer, answer_id)
            return _answer(satir) if satir else None

    def save_answer(self, answer: Answer) -> None:
        with tenant_session(self._tenant) as o:
            satir = o.get(m.Answer, answer.id) or m.Answer(id=answer.id, tenant_id=self._tenant)
            satir.run_id = answer.run_id
            satir.item_id = answer.item_id
            satir.state = answer.state
            satir.value = None if answer.value is None else {"v": answer.value}
            satir.note = answer.note
            satir.user_id = answer.user_id
            satir.device_id = answer.device_id
            satir.answered_at = answer.answered_at
            satir.device_reported_at = answer.device_reported_at
            satir.clock_skew_minutes = answer.clock_skew_minutes
            satir.evidence_count = answer.evidence_count
            o.add(satir)

    def lock(self, run_id: UUID) -> RunLock | None:
        return self._locks.get(run_id)

    def save_lock(self, run_id: UUID, lock: RunLock | None) -> None:
        if lock is None:
            self._locks.pop(run_id, None)
        else:
            self._locks[run_id] = lock


# ------------------------------------------------------------------ action


def _action(satir: m.Action) -> Action:
    return Action(
        id=satir.id,
        branch_id=satir.branch_id,
        title=satir.title,
        source=satir.source,  # type: ignore[arg-type]
        priority=satir.priority,  # type: ignore[arg-type]
        opened_at=satir.opened_at,
        due_at=satir.due_at,
        source_id=satir.source_id,
        description=satir.description,
        assignee_user_id=satir.assignee_user_id,
        status=satir.status,  # type: ignore[arg-type]
        closed_at=satir.closed_at,
        closed_by=satir.closed_by,
        close_note=satir.close_note,
    )


class SqlActionRepository(_TenantRepository):
    def actions(self) -> list[Action]:
        with tenant_session(self._tenant) as o:
            return [_action(a) for a in o.scalars(select(m.Action)).all()]

    def action(self, action_id: UUID) -> Action | None:
        with tenant_session(self._tenant) as o:
            satir = o.get(m.Action, action_id)
            return _action(satir) if satir else None

    def save_action(self, action: Action) -> None:
        with tenant_session(self._tenant) as o:
            satir = o.get(m.Action, action.id) or m.Action(id=action.id, tenant_id=self._tenant)
            satir.branch_id = action.branch_id
            satir.title = action.title
            satir.description = action.description
            satir.source = action.source
            satir.source_id = action.source_id
            satir.priority = action.priority
            satir.status = action.status
            satir.opened_at = action.opened_at
            satir.due_at = action.due_at
            satir.assignee_user_id = action.assignee_user_id
            satir.closed_at = action.closed_at
            satir.closed_by = action.closed_by
            satir.close_note = action.close_note
            o.add(satir)


__all__ = [
    "SqlActionRepository",
    "SqlAnswerRepository",
    "SqlOrganizationRepository",
    "SqlPlanRepository",
    "SqlTemplateRepository",
    "SqlUserRepository",
]
