"""Plan ve çalıştırma uç noktaları (ST-025, ST-026, ST-029; FR-0501…0521)."""

from __future__ import annotations

from datetime import UTC, date, datetime, time
from typing import Annotated, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field, model_validator

from talimatname.api.bagimliliklar import (
    organizasyon_servisi,
    plan_servisi,
    sablon_servisi,
    zamanlayici_servisi,
)
from talimatname.api.guvenlik import Kullanici, Yonetici, erisilebilir_sube_idleri
from talimatname.domain.plans import Assignment, Plan, Run
from talimatname.domain.window import Anchor, WindowRule
from talimatname.services.organization import OrganizationService
from talimatname.services.plans import HORIZON_DAYS, PlanService
from talimatname.services.scheduler import SchedulerService
from talimatname.services.templates import TemplateService

router = APIRouter(tags=["plan"])

Servis = Annotated[PlanService, Depends(plan_servisi)]
OrgServis = Annotated[OrganizationService, Depends(organizasyon_servisi)]
SablonServis = Annotated[TemplateService, Depends(sablon_servisi)]
ZamanlayiciServis = Annotated[SchedulerService, Depends(zamanlayici_servisi)]

GUN_KISA = ("MO", "TU", "WE", "TH", "FR", "SA", "SU")


class Zamanlama(BaseModel):
    """Plan editörünün zaman kuralı (FR-0502…0507).

    RRULE metni burada kurulur: arayüz "her gün / haftanın günleri / tek
    seferlik" der, motor RFC 5545 alır. Başlangıç ya sabit saattir ya da
    şubenin çalışma saatinden türetilir ("kapanıştan 60 dk önce").
    """

    repeat: Literal["daily", "weekly", "once"] = "daily"
    weekdays: list[int] = Field(default_factory=list, description="0 = Pazartesi (haftalıkta)")
    starts_on: date
    start_mode: Literal["fixed", "anchor"] = "fixed"
    start_time: time | None = None
    anchor_reference: Literal["open", "close"] | None = None
    anchor_offset_minutes: int = 0
    duration_minutes: int = Field(gt=0, le=24 * 60)
    tolerance_minutes: int = Field(default=0, ge=0, le=24 * 60)

    @model_validator(mode="after")
    def _tutarli(self) -> Zamanlama:
        if self.start_mode == "fixed" and self.start_time is None:
            raise ValueError("Sabit başlangıçta saat verilmeli")
        if self.start_mode == "anchor" and self.anchor_reference is None:
            raise ValueError("Çalışma saatinden türetmede açılış/kapanış seçilmeli")
        if self.repeat == "weekly" and not self.weekdays:
            raise ValueError("Haftalık planda en az bir gün seçilmeli")
        return self

    def rrule(self) -> str:
        if self.repeat == "daily":
            return "FREQ=DAILY"
        if self.repeat == "weekly":
            gunler = ",".join(GUN_KISA[g] for g in sorted(set(self.weekdays)))
            return f"FREQ=WEEKLY;BYDAY={gunler}"
        return "FREQ=DAILY;COUNT=1"  # tek seferlik (FR-0512)

    def to_rule(self) -> WindowRule:
        return WindowRule(
            recurrence=self.rrule(),
            starts_on=self.starts_on,
            duration_minutes=self.duration_minutes,
            tolerance_minutes=self.tolerance_minutes,
            start_time=self.start_time if self.start_mode == "fixed" else None,
            anchor=(
                Anchor(self.anchor_reference, self.anchor_offset_minutes)  # type: ignore[arg-type]
                if self.start_mode == "anchor"
                else None
            ),
        )


class AtamaGirdisi(BaseModel):
    kind: Literal["anyone", "role", "user"] = "anyone"
    role: str | None = None
    user_id: UUID | None = None


class PlanGirdisi(BaseModel):
    name: str = Field(min_length=1, max_length=80, examples=["Günlük kapanış"])
    template_version_id: UUID
    branch_ids: list[UUID] = Field(min_length=1)
    schedule: Zamanlama
    assignment: AtamaGirdisi = AtamaGirdisi()


class CalistirmaOzet(BaseModel):
    id: UUID
    plan_id: UUID
    branch_id: UUID
    branch_name: str
    business_day: date
    window_start: datetime
    window_end: datetime
    tolerance_end: datetime
    status: str
    late: bool = False


class PlanOzet(BaseModel):
    id: UUID
    name: str
    template_version_id: UUID
    template_name: str
    branch_ids: list[UUID]
    branch_count: int
    active: bool
    assignment: AtamaGirdisi
    recurrence: str
    duration_minutes: int
    tolerance_minutes: int


class OnizlemeYaniti(BaseModel):
    """7 gün önizleme (FR-0511): kaydetmeden önce ne üretileceği."""

    days: int
    run_count: int
    runs: list[CalistirmaOzet]


def _plan(girdi: PlanGirdisi, plan_id: UUID | None = None) -> Plan:
    return Plan(
        id=plan_id or uuid4(),
        name=girdi.name,
        template_version_id=girdi.template_version_id,
        branch_ids=tuple(girdi.branch_ids),
        rule=girdi.schedule.to_rule(),
        assignment=Assignment(
            kind=girdi.assignment.kind,
            role=girdi.assignment.role,
            user_id=girdi.assignment.user_id,
        ),
    )


def _sube_adlari(org: OrganizationService) -> dict[UUID, str]:
    return {
        sube.id: sube.name for dugum in org.tree(include_inactive=True) for sube in dugum.branches
    }


def _calistirma(run: Run, adlar: dict[UUID, str], simdi: datetime) -> CalistirmaOzet:
    durum, gec = run.state_at(simdi)
    return CalistirmaOzet(
        id=run.id,
        plan_id=run.plan_id,
        branch_id=run.branch_id,
        branch_name=adlar.get(run.branch_id, "—"),
        business_day=run.business_day,
        window_start=run.window_start,
        window_end=run.window_end,
        tolerance_end=run.tolerance_end,
        status=durum,
        late=gec,
    )


def _ozet(plan: Plan, sablon_adi: str) -> PlanOzet:
    return PlanOzet(
        id=plan.id,
        name=plan.name,
        template_version_id=plan.template_version_id,
        template_name=sablon_adi,
        branch_ids=list(plan.branch_ids),
        branch_count=len(plan.branch_ids),
        active=plan.active,
        assignment=AtamaGirdisi(
            kind=plan.assignment.kind,
            role=plan.assignment.role,
            user_id=plan.assignment.user_id,
        ),
        recurrence=plan.rule.recurrence,
        duration_minutes=plan.rule.duration_minutes,
        tolerance_minutes=plan.rule.tolerance_minutes,
    )


def _sablon_adi(sablonlar: TemplateService, version_id: UUID) -> str:
    surum = sablonlar.version(version_id)
    return sablonlar.get(surum.template_id).name


@router.get("/plans", summary="Plan listesi")
def plan_listesi(
    servis: Servis,
    sablonlar: SablonServis,
    org: OrgServis,
    kullanici: Kullanici,
    include_inactive: bool = False,
) -> list[PlanOzet]:
    """Kullanıcının kapsamına **dokunan** planlar.

    Bölge müdürü, kendi şubelerinden en az birini kapsayan planı görür;
    plan başka şubeleri de kapsıyorsa bu bilgi gizlenmez — plan zaten
    merkezin kurduğu ortak bir kuraldır.
    """
    kapsam = erisilebilir_sube_idleri(kullanici, org)
    return [
        _ozet(plan, _sablon_adi(sablonlar, plan.template_version_id))
        for plan in servis.list_plans(include_inactive=include_inactive)
        if kapsam & set(plan.branch_ids)
    ]


@router.post("/plans", status_code=status.HTTP_201_CREATED, summary="Plan oluştur")
def plan_olustur(
    girdi: PlanGirdisi, servis: Servis, sablonlar: SablonServis, _: Yonetici
) -> PlanOzet:
    """Plan kaydedilir ve ufuk içindeki çalıştırmalar hemen üretilir."""
    plan = servis.create(_plan(girdi))
    return _ozet(plan, _sablon_adi(sablonlar, plan.template_version_id))


@router.post("/plans/preview", summary="Kaydetmeden 7 gün önizleme")
def plan_onizleme(
    girdi: PlanGirdisi,
    servis: Servis,
    org: OrgServis,
    _: Yonetici,
    days: Annotated[int, Query(ge=1, le=30)] = HORIZON_DAYS,
) -> OnizlemeYaniti:
    plan = _plan(girdi)
    runs = servis.preview(plan, days=days)
    adlar = _sube_adlari(org)
    simdi = datetime.now(UTC)
    return OnizlemeYaniti(
        days=days,
        run_count=len(runs),
        runs=[_calistirma(r, adlar, simdi) for r in runs],
    )


@router.post("/plans/{plan_id}/deactivate", summary="Planı durdur")
def plan_durdur(plan_id: UUID, servis: Servis, sablonlar: SablonServis, _: Yonetici) -> PlanOzet:
    """Durdurulan plandan yeni çalıştırma üretilmez; başlanmamışlar silinir."""
    plan = servis.set_active(plan_id, False)
    return _ozet(plan, _sablon_adi(sablonlar, plan.template_version_id))


@router.post("/plans/{plan_id}/activate", summary="Planı yeniden başlat")
def plan_baslat(plan_id: UUID, servis: Servis, sablonlar: SablonServis, _: Yonetici) -> PlanOzet:
    plan = servis.set_active(plan_id, True)
    return _ozet(plan, _sablon_adi(sablonlar, plan.template_version_id))


class UretimYaniti(BaseModel):
    created: int
    deleted: int


class TurYaniti(BaseModel):
    """Zamanlayıcı turunun özeti (ST-027)."""

    at: datetime
    created: int
    deleted: int
    missed: int = Field(description="Toleransı dolduğu için kaçırıldı yazılan çalıştırma sayısı")
    actions_opened: int = Field(default=0, description="Kaçırmadan doğan yeni aksiyon sayısı")


@router.post("/plans/{plan_id}/generate", summary="Çalıştırmaları şimdi üret")
def plan_uret(plan_id: UUID, servis: Servis, _: Yonetici) -> UretimYaniti:
    """Zamanlayıcının (ST-027) yapacağı işin elle tetiklenmesi; idempotenttir."""
    eklenen, silinen = servis.generate(plan_id)
    return UretimYaniti(created=eklenen, deleted=silinen)


@router.post("/scheduler/tick", tags=["zamanlayıcı"], summary="Zamanlayıcı turunu şimdi koş")
def zamanlayici_turu(servis: ZamanlayiciServis, _: Yonetici) -> TurYaniti:
    """Ayrı süreçte koşan zamanlayıcının (ST-027) elle tetiklenmesi.

    Aynı iş mantığı; idempotent olduğu için zamanlayıcı çalışırken de
    güvenle çağrılabilir.
    """
    sonuc = servis.tick()
    return TurYaniti(at=sonuc.at, created=sonuc.created, deleted=sonuc.deleted, missed=sonuc.missed)


@router.get("/runs", summary="Bir iş gününün çalıştırmaları")
def calistirmalar(
    servis: Servis,
    org: OrgServis,
    kullanici: Kullanici,
    business_day: date | None = None,
) -> list[CalistirmaOzet]:
    gun = business_day or datetime.now(UTC).date()
    adlar = _sube_adlari(org)
    kapsam = erisilebilir_sube_idleri(kullanici, org)
    runs = [r for r in servis.runs_for_day(gun) if r.branch_id in kapsam]
    simdi = datetime.now(UTC)
    return [_calistirma(r, adlar, simdi) for r in runs]
