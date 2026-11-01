"""Portların PostgreSQL karşılıkları (ADR-0014 md.2).

Servis katmanı bu dosyayı tanımaz: aynı portları bellek içi adaptör de
uyguluyor ve aynı testler ikisini de geçiyor. Buradaki tek iş **eşleme**:
alan nesnesi ↔ satır.

Her çağrı kendi kiracı oturumunu açar (`tenant_session`). Kısa işlemler
tercih edildi: uzun süren bir oturumu servis katmanına taşımak,
kalıcılığı servis katmanına sızdırmak olurdu.
"""

from __future__ import annotations

from datetime import date, datetime, time
from typing import Any
from uuid import UUID, uuid5

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError

from talimatname.domain.actions import Action
from talimatname.domain.answers import Answer, RunLock
from talimatname.domain.audit import CODE_PREFIX_LENGTH, AuditEvent, SequenceTaken
from talimatname.domain.chain_anchor import ChainAnchor
from talimatname.domain.evidence import Evidence
from talimatname.domain.exports import ExportJob
from talimatname.domain.notifications import Notification
from talimatname.domain.organization import Branch, Region, Station
from talimatname.domain.plans import Assignment, Plan, Run
from talimatname.domain.setup import AccountSettings
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
        latitude=satir.latitude,
        longitude=satir.longitude,
        status=satir.status,  # type: ignore[arg-type]
    )


class SqlSettingsRepository(_TenantRepository):
    """Marka ayarları: kiracı başına tek satır."""

    def settings(self) -> AccountSettings | None:
        with tenant_session(self._tenant) as o:
            satir = o.get(m.AccountSettings, self._tenant)
            if satir is None:
                return None
            return AccountSettings(
                brand_name=satir.brand_name,
                timezone=satir.timezone,
                default_hours=_saatler_alan(satir.default_hours),
                logo_url=satir.logo_url,
                completed_at=satir.completed_at,
            )

    def save_settings(self, settings: AccountSettings) -> None:
        with tenant_session(self._tenant) as o:
            satir = o.get(m.AccountSettings, self._tenant) or m.AccountSettings(
                tenant_id=self._tenant
            )
            satir.brand_name = settings.brand_name
            satir.timezone = settings.timezone
            satir.default_hours = _saatler_json(settings.default_hours)
            satir.logo_url = settings.logo_url
            satir.completed_at = settings.completed_at
            o.add(satir)


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
            satir.latitude = branch.latitude
            satir.longitude = branch.longitude
            satir.status = branch.status
            satir.business_hours = _saatler_json(branch.business_hours)
            o.add(satir)

    def save_region(self, region: Region) -> None:
        with tenant_session(self._tenant) as o:
            satir = o.get(m.Region, region.id) or m.Region(id=region.id, tenant_id=self._tenant)
            satir.name = region.name
            satir.code = region.code
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

    def run(self, run_id: UUID) -> Run | None:
        with tenant_session(self._tenant) as o:
            satir = o.get(m.Run, run_id)
            return _run(satir) if satir else None

    def runs_for_plan(self, plan_id: UUID, *, since: date | None = None) -> list[Run]:
        sorgu = select(m.Run).where(m.Run.plan_id == plan_id)
        if since is not None:
            sorgu = sorgu.where(m.Run.business_day >= since)
        with tenant_session(self._tenant) as o:
            return [_run(r) for r in o.scalars(sorgu).all()]

    def runs_for_day(self, business_day: date) -> list[Run]:
        with tenant_session(self._tenant) as o:
            return [
                _run(r)
                for r in o.scalars(select(m.Run).where(m.Run.business_day == business_day)).all()
            ]

    def runs_between(self, first_day: date, last_day: date) -> list[Run]:
        with tenant_session(self._tenant) as o:
            satirlar = o.scalars(
                select(m.Run)
                .where(m.Run.business_day >= first_day, m.Run.business_day <= last_day)
                .order_by(m.Run.business_day)
            ).all()
            return [_run(r) for r in satirlar]

    def count_runs_between(
        self, first_day: date, last_day: date, *, branch_ids: set[UUID] | None = None
    ) -> int:
        sorgu = (
            select(func.count())
            .select_from(m.Run)
            .where(m.Run.business_day >= first_day, m.Run.business_day <= last_day)
        )
        if branch_ids is not None:
            if not branch_ids:
                return 0
            sorgu = sorgu.where(m.Run.branch_id.in_(branch_ids))
        with tenant_session(self._tenant) as o:
            return int(o.scalar(sorgu) or 0)

    def save_run(self, run: Run) -> None:
        self.save_runs([run])

    def save_runs(self, runs: list[Run]) -> None:
        """Hepsi **tek işlemde**: uzak veritabanında gidiş-dönüş pahalı.

        Ölçüm (Frankfurt, 56 kayıt): kayıt başına ayrı işlem 14,0 sn;
        tek işlem + tek okuma 0,26 sn.
        """
        if not runs:
            return
        with tenant_session(self._tenant) as o:
            # Var olanları **tek sorguda** okuyoruz: satır başına `get`
            # çağırmak 56 ayrı SELECT demekti ve kazancın çoğunu
            # yiyordu (ölçüm: 58 ms/kayıt → 5 ms/kayıt).
            mevcut = {
                satir.id: satir
                for satir in o.scalars(
                    select(m.Run).where(m.Run.id.in_([run.id for run in runs]))
                ).all()
            }
            for run in runs:
                satir = mevcut.get(run.id) or m.Run(id=run.id, tenant_id=self._tenant)
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
        self.delete_runs([run_id])

    def delete_runs(self, run_ids: list[UUID]) -> None:
        if not run_ids:
            return
        with tenant_session(self._tenant) as o:
            o.execute(delete(m.Run).where(m.Run.id.in_(run_ids)))


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
        not_done_reason=satir.not_done_reason,  # type: ignore[arg-type]
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

    def answers_for_runs(self, run_ids: list[UUID]) -> dict[UUID, list[Answer]]:
        """Çok çalıştırmanın cevapları **tek sorguda** (rapor yolu).

        Çalıştırma başına ayrı sorgu, 200 çalıştırmalık bir ayda 200
        gidiş-dönüş demekti.
        """
        sonuc: dict[UUID, list[Answer]] = {run_id: [] for run_id in run_ids}
        if not run_ids:
            return sonuc
        with tenant_session(self._tenant) as o:
            for satir in o.scalars(select(m.Answer).where(m.Answer.run_id.in_(run_ids))).all():
                sonuc[satir.run_id].append(_answer(satir))
        return sonuc

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
            satir.not_done_reason = answer.not_done_reason
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


def _bildirim(satir: m.Notification) -> Notification:
    return Notification(
        id=satir.id,
        kind=satir.kind,  # type: ignore[arg-type]
        channel=satir.channel,  # type: ignore[arg-type]
        user_id=satir.user_id,
        title=satir.title,
        body=satir.body,
        send_at=satir.send_at,
        created_at=satir.created_at,
        branch_id=satir.branch_id,
        run_id=satir.run_id,
        action_id=satir.action_id,
        deep_link=satir.deep_link,
        status=satir.status,  # type: ignore[arg-type]
        attempts=satir.attempts,
        sent_at=satir.sent_at,
        delivered_at=satir.delivered_at,
        error_code=satir.error_code,
        error_detail=satir.error_detail,
    )


class SqlNotificationRepository(_TenantRepository):
    def notifications(self) -> list[Notification]:
        with tenant_session(self._tenant) as o:
            return [_bildirim(b) for b in o.scalars(select(m.Notification)).all()]

    def notification(self, notification_id: UUID) -> Notification | None:
        with tenant_session(self._tenant) as o:
            satir = o.get(m.Notification, notification_id)
            return _bildirim(satir) if satir else None

    def save_notification(self, notification: Notification) -> None:
        with tenant_session(self._tenant) as o:
            satir = o.get(m.Notification, notification.id) or m.Notification(
                id=notification.id, tenant_id=self._tenant
            )
            satir.kind = notification.kind
            satir.channel = notification.channel
            satir.user_id = notification.user_id
            satir.title = notification.title
            satir.body = notification.body
            satir.send_at = notification.send_at
            satir.created_at = notification.created_at
            satir.branch_id = notification.branch_id
            satir.run_id = notification.run_id
            satir.action_id = notification.action_id
            satir.deep_link = notification.deep_link
            satir.status = notification.status
            satir.attempts = notification.attempts
            satir.sent_at = notification.sent_at
            satir.delivered_at = notification.delivered_at
            satir.error_code = notification.error_code
            satir.error_detail = notification.error_detail
            o.add(satir)


def _kanit(satir: m.Evidence) -> Evidence:
    return Evidence(
        id=satir.id,
        run_id=satir.run_id,
        answer_id=satir.answer_id,
        item_id=satir.item_id,
        branch_id=satir.branch_id,
        user_id=satir.user_id,
        sha256=satir.sha256,
        content_type=satir.content_type,
        size_bytes=satir.size_bytes,
        storage_key=satir.storage_key,
        created_at=satir.created_at,
        status=satir.status,  # type: ignore[arg-type]
        captured_at=satir.captured_at,
        device_reported_at=satir.device_reported_at,
        clock_skew_minutes=satir.clock_skew_minutes,
        latitude=satir.latitude,
        longitude=satir.longitude,
        distance_meters=satir.distance_meters,
        device_id=satir.device_id,
        from_gallery=satir.from_gallery,
        flags=tuple(satir.flags or ()),
        stored_at=satir.stored_at,
        stamped_at=satir.stamped_at,
        stamped_key=satir.stamped_key,
        thumbnail_key=satir.thumbnail_key,
    )


class SqlEvidenceRepository(_TenantRepository):
    def evidences(self) -> list[Evidence]:
        with tenant_session(self._tenant) as o:
            return [_kanit(k) for k in o.scalars(select(m.Evidence)).all()]

    def evidence(self, evidence_id: UUID) -> Evidence | None:
        with tenant_session(self._tenant) as o:
            satir = o.get(m.Evidence, evidence_id)
            return _kanit(satir) if satir else None

    def evidence_by_digest(self, sha256: str) -> Evidence | None:
        with tenant_session(self._tenant) as o:
            satir = o.scalars(select(m.Evidence).where(m.Evidence.sha256 == sha256)).first()
            return _kanit(satir) if satir else None

    def stored_evidences(self, limit: int) -> list[Evidence]:
        """Eskiden yeniye: kuyruk birikirse önce bekleyen damgalanır."""
        with tenant_session(self._tenant) as o:
            satirlar = o.scalars(
                select(m.Evidence)
                .where(m.Evidence.status == "stored")
                .order_by(m.Evidence.created_at)
                .limit(limit)
            ).all()
            return [_kanit(k) for k in satirlar]

    def pending_evidences(self, before: datetime, limit: int) -> list[Evidence]:
        """Baytı gelmemiş eski kayıtlar: süzgeç yine **depoda** kalıyor."""
        with tenant_session(self._tenant) as o:
            satirlar = o.scalars(
                select(m.Evidence)
                .where(m.Evidence.status == "pending", m.Evidence.created_at < before)
                .order_by(m.Evidence.created_at)
                .limit(limit)
            ).all()
            return [_kanit(k) for k in satirlar]

    def save_evidence(self, evidence: Evidence) -> None:
        with tenant_session(self._tenant) as o:
            satir = o.get(m.Evidence, evidence.id) or m.Evidence(
                id=evidence.id, tenant_id=self._tenant
            )
            satir.run_id = evidence.run_id
            satir.answer_id = evidence.answer_id
            satir.item_id = evidence.item_id
            satir.branch_id = evidence.branch_id
            satir.user_id = evidence.user_id
            satir.sha256 = evidence.sha256
            satir.content_type = evidence.content_type
            satir.size_bytes = evidence.size_bytes
            satir.storage_key = evidence.storage_key
            satir.created_at = evidence.created_at
            satir.status = evidence.status
            satir.captured_at = evidence.captured_at
            satir.device_reported_at = evidence.device_reported_at
            satir.clock_skew_minutes = evidence.clock_skew_minutes
            satir.latitude = evidence.latitude
            satir.longitude = evidence.longitude
            satir.distance_meters = evidence.distance_meters
            satir.device_id = evidence.device_id
            satir.from_gallery = evidence.from_gallery
            satir.flags = list(evidence.flags)
            satir.stored_at = evidence.stored_at
            satir.stamped_at = evidence.stamped_at
            satir.stamped_key = evidence.stamped_key
            satir.thumbnail_key = evidence.thumbnail_key
            o.add(satir)

    def delete_evidence(self, evidence_id: UUID) -> None:
        with tenant_session(self._tenant) as o:
            satir = o.get(m.Evidence, evidence_id)
            if satir is not None:
                o.delete(satir)


def _olay(satir: m.AuditEvent) -> AuditEvent:
    return AuditEvent(
        id=satir.id,
        sequence=satir.sequence,
        event_type=satir.event_type,
        at=satir.at,
        object_type=satir.object_type,
        object_id=satir.object_id,
        actor_id=satir.actor_id,
        ip=satir.ip,
        device=satir.device,
        before=dict(satir.before or {}),
        after=dict(satir.after or {}),
        prev_hash=satir.prev_hash,
        hash=satir.hash,
    )


def _cikti(satir: m.ExportJob) -> ExportJob:
    return ExportJob(
        id=satir.id,
        kind=satir.kind,  # type: ignore[arg-type]
        params={str(a): str(d) for a, d in (satir.params or {}).items()},
        requested_by=satir.requested_by,
        requested_at=satir.requested_at,
        run_count=satir.run_count,
        state=satir.state,  # type: ignore[arg-type]
        attempts=satir.attempts,
        started_at=satir.started_at,
        finished_at=satir.finished_at,
        object_key=satir.object_key,
        size_bytes=satir.size_bytes,
        document_code=satir.document_code,
        error_code=satir.error_code,
    )


def _cipa(satir: m.AuditAnchor) -> ChainAnchor:
    return ChainAnchor(
        id=satir.id,
        created_at=satir.created_at,
        sequence=satir.sequence,
        chain_hash=satir.chain_hash,
        state=satir.state,  # type: ignore[arg-type]
        token=bytes(satir.token) if satir.token is not None else None,
        stamped_at=satir.stamped_at,
        tsa_name=satir.tsa_name,
        serial=satir.serial,
        error=satir.error,
    )


class SqlAnchorRepository(_TenantRepository):
    """`AnchorRepository` portunun SQL karşılığı (FR-1302).

    Güncelleme yok: tablo ekle-yalnız (göç 0009) ve portta da böyle
    bir yöntem bulunmuyor.
    """

    def save_anchor(self, anchor: ChainAnchor) -> None:
        with tenant_session(self._tenant) as o:
            o.add(
                m.AuditAnchor(
                    id=anchor.id,
                    tenant_id=self._tenant,
                    created_at=anchor.created_at,
                    sequence=anchor.sequence,
                    chain_hash=anchor.chain_hash,
                    state=anchor.state,
                    token=anchor.token,
                    stamped_at=anchor.stamped_at,
                    tsa_name=anchor.tsa_name,
                    serial=anchor.serial,
                    error=anchor.error,
                )
            )

    def anchors(self, *, limit: int = 100) -> list[ChainAnchor]:
        sorgu = select(m.AuditAnchor).order_by(m.AuditAnchor.created_at.desc()).limit(limit)
        with tenant_session(self._tenant) as o:
            return [_cipa(r) for r in o.scalars(sorgu).all()]

    def anchors_since(self, moment: datetime) -> list[ChainAnchor]:
        sorgu = (
            select(m.AuditAnchor)
            .where(m.AuditAnchor.created_at >= moment)
            .order_by(m.AuditAnchor.created_at)
        )
        with tenant_session(self._tenant) as o:
            return [_cipa(r) for r in o.scalars(sorgu).all()]


class SqlExportJobRepository(_TenantRepository):
    """`ExportJobRepository` portunun SQL karşılığı (FR-1217)."""

    def job(self, job_id: UUID) -> ExportJob | None:
        with tenant_session(self._tenant) as o:
            satir = o.get(m.ExportJob, job_id)
            return _cikti(satir) if satir else None

    def jobs_for_user(self, user_id: UUID, *, limit: int = 20) -> list[ExportJob]:
        sorgu = (
            select(m.ExportJob)
            .where(m.ExportJob.requested_by == user_id)
            .order_by(m.ExportJob.requested_at.desc())
            .limit(limit)
        )
        with tenant_session(self._tenant) as o:
            return [_cikti(r) for r in o.scalars(sorgu).all()]

    def save_job(self, job: ExportJob) -> None:
        with tenant_session(self._tenant) as o:
            o.merge(
                m.ExportJob(
                    id=job.id,
                    tenant_id=self._tenant,
                    kind=job.kind,
                    params=dict(job.params),
                    requested_by=job.requested_by,
                    requested_at=job.requested_at,
                    run_count=job.run_count,
                    state=job.state,
                    attempts=job.attempts,
                    started_at=job.started_at,
                    finished_at=job.finished_at,
                    object_key=job.object_key,
                    size_bytes=job.size_bytes,
                    document_code=job.document_code,
                    error_code=job.error_code,
                )
            )

    def queued_jobs(self, limit: int) -> list[ExportJob]:
        sorgu = (
            select(m.ExportJob)
            .where(m.ExportJob.state == "queued")
            .order_by(m.ExportJob.requested_at)
            .limit(limit)
        )
        with tenant_session(self._tenant) as o:
            return [_cikti(r) for r in o.scalars(sorgu).all()]

    def files_before(self, before: datetime, limit: int) -> list[ExportJob]:
        sorgu = (
            select(m.ExportJob)
            .where(
                m.ExportJob.object_key.is_not(None),
                m.ExportJob.finished_at.is_not(None),
                m.ExportJob.finished_at < before,
            )
            .order_by(m.ExportJob.finished_at)
            .limit(limit)
        )
        with tenant_session(self._tenant) as o:
            return [_cikti(r) for r in o.scalars(sorgu).all()]


class SqlAuditRepository(_TenantRepository):
    """`AuditRepository` portunun SQL karşılığı (FR-1301).

    Güncelleme ve silme yöntemi **yok**: veritabanı yetkisi de
    vermiyor (göç 0006). İki yerde birden korumak fazlalık değil;
    biri niyeti, öbürü güvenceyi anlatıyor.
    """

    def append(self, event: AuditEvent) -> None:
        try:
            with tenant_session(self._tenant) as o:
                o.add(
                    m.AuditEvent(
                        id=event.id,
                        tenant_id=self._tenant,
                        sequence=event.sequence,
                        event_type=event.event_type,
                        at=event.at,
                        object_type=event.object_type,
                        object_id=event.object_id,
                        actor_id=event.actor_id,
                        ip=event.ip,
                        device=event.device,
                        before=dict(event.before),
                        after=dict(event.after),
                        prev_hash=event.prev_hash,
                        hash=event.hash,
                    )
                )
        except IntegrityError as hata:
            # (kiraci, sira) tekil: başka bir yazma aynı halkayı almış.
            raise SequenceTaken(f"sıra: {event.sequence}") from hata

    def head(self) -> AuditEvent | None:
        with tenant_session(self._tenant) as o:
            satir = o.scalars(
                select(m.AuditEvent).order_by(m.AuditEvent.sequence.desc()).limit(1)
            ).first()
            return _olay(satir) if satir else None

    def events(
        self,
        *,
        object_id: UUID | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int = 200,
    ) -> list[AuditEvent]:
        sorgu = select(m.AuditEvent).order_by(m.AuditEvent.sequence).limit(limit)
        if object_id is not None:
            sorgu = sorgu.where(m.AuditEvent.object_id == object_id)
        if since is not None:
            sorgu = sorgu.where(m.AuditEvent.at >= since)
        if until is not None:
            sorgu = sorgu.where(m.AuditEvent.at <= until)
        with tenant_session(self._tenant) as o:
            return [_olay(k) for k in o.scalars(sorgu).all()]

    def by_hash_prefix(self, prefix: str, *, limit: int = 2) -> list[AuditEvent]:
        """Belge kodu aramasi (FR-1218). Önekte eşitlik, `LIKE` değil.

        `substr(hash, 1, 12) = :onek` ile sorduk ve göç 0007'de aynı
        ifadeye indeks var: parametreli `LIKE 'x%'` planlayıcıda indeksi
        her zaman kullanmıyor ve bu uç nokta **dışarıdan** çağrılıyor —
        tam tarama, doğrulama sayfasını yük bindirme aracına çevirirdi.
        """
        sorgu = (
            select(m.AuditEvent)
            .where(func.substr(m.AuditEvent.hash, 1, CODE_PREFIX_LENGTH) == prefix)
            .order_by(m.AuditEvent.sequence)
            .limit(limit)
        )
        with tenant_session(self._tenant) as o:
            return [_olay(k) for k in o.scalars(sorgu).all()]

    def at_sequence(self, sequence: int) -> AuditEvent | None:
        with tenant_session(self._tenant) as o:
            satir = o.scalars(select(m.AuditEvent).where(m.AuditEvent.sequence == sequence)).first()
            return _olay(satir) if satir else None


__all__ = [
    "SqlActionRepository",
    "SqlAnchorRepository",
    "SqlAnswerRepository",
    "SqlAuditRepository",
    "SqlEvidenceRepository",
    "SqlExportJobRepository",
    "SqlNotificationRepository",
    "SqlOrganizationRepository",
    "SqlPlanRepository",
    "SqlTemplateRepository",
    "SqlUserRepository",
]
