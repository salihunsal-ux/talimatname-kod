"""Plan ve çalıştırma uç noktaları (ST-025, ST-026, ST-029; FR-0501…0521)."""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from typing import Annotated, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field, model_validator

from talimatname.api.bagimliliklar import (
    ayarlar,
    kurulum_servisi,
    organizasyon_servisi,
    plan_servisi,
    sablon_servisi,
    zamanlayici_servisi,
)
from talimatname.api.guvenlik import Gozlemci, Kullanici, Yonetici
from talimatname.api.is_gunu import bugun
from talimatname.domain.plans import Assignment, Plan, Run
from talimatname.domain.window import (
    MAX_TOLERANCE_MINUTES,
    MAX_WINDOW_MINUTES,
    Anchor,
    WindowRule,
)
from talimatname.services.organization import (
    OrganizationService,
    erisilebilir_sube_idleri,
)
from talimatname.services.plans import HORIZON_DAYS, PlanService
from talimatname.services.scheduler import SchedulerService
from talimatname.services.setup import SetupService
from talimatname.services.templates import TemplateService

router = APIRouter(tags=["plan"])

Servis = Annotated[PlanService, Depends(plan_servisi)]
OrgServis = Annotated[OrganizationService, Depends(organizasyon_servisi)]
KurulumServis = Annotated[SetupService, Depends(kurulum_servisi)]
SablonServis = Annotated[TemplateService, Depends(sablon_servisi)]
ZamanlayiciServis = Annotated[SchedulerService, Depends(zamanlayici_servisi)]

GUN_KISA = ("MO", "TU", "WE", "TH", "FR", "SA", "SU")

#: Gün içinde açılabilecek en çok pencere. Sınır keyfi değil: tekrar
#: dizgesi veritabanında 200 karakter ve her saat bir satır yazıyor.
#: Altı pencere, "her 2 saat, 08:00–18:00" gibi gerçek bir kuralı
#: karşılıyor.
MAX_GUNLUK_PENCERE = 6


class Zamanlama(BaseModel):
    """Plan editörünün zaman kuralı (FR-0502…0507).

    RRULE metni burada kurulur: arayüz "her gün / haftanın günleri / tek
    seferlik" der, motor RFC 5545 alır. Başlangıç ya sabit saattir ya da
    şubenin çalışma saatinden türetilir ("kapanıştan 60 dk önce").
    """

    repeat: Literal["daily", "weekly", "monthly", "once"] = "daily"
    weekdays: list[int] = Field(default_factory=list, description="0 = Pazartesi (haftalıkta)")
    times: list[time] = Field(
        default_factory=list,
        description="Gün içinde birden çok pencere; boşsa yalnızca start_time",
    )
    every_hours: int | None = Field(
        default=None, ge=1, le=12, description="Her N saat (başlangıç–bitiş aralığında)"
    )
    until_time: time | None = Field(default=None, description="Her N saat kuralının gün içi sonu")
    month_day: int | None = Field(default=None, ge=1, le=31, description="Ayın günü")
    month_nth: int | None = Field(
        default=None, ge=-1, le=4, description="N'inci hafta günü; -1 = son"
    )
    month_weekday: int | None = Field(default=None, ge=0, le=6, description="0 = Pazartesi")
    ends_on: date | None = Field(default=None, description="Tekrarın son günü (dâhil)")
    starts_on: date
    start_mode: Literal["fixed", "anchor"] = "fixed"
    start_time: time | None = None
    anchor_reference: Literal["open", "close"] | None = None
    anchor_offset_minutes: int = 0
    duration_minutes: int = Field(gt=0, le=MAX_WINDOW_MINUTES)
    tolerance_minutes: int = Field(default=0, ge=0, le=MAX_TOLERANCE_MINUTES)

    @model_validator(mode="after")
    def _pencere_tavani(self) -> Zamanlama:
        """Pencere + tolerans ≤ 24 saat (FR-0504).

        Tek tek sınırlar yetmiyor: 1440 dakikalık pencereye 240 dakika
        tolerans eklenince çalıştırma ertesi gününkiyle çakışıyordu.
        """
        toplam = self.duration_minutes + self.tolerance_minutes
        if toplam > MAX_WINDOW_MINUTES:
            raise ValueError(
                f"pencere ve tolerans toplamı {MAX_WINDOW_MINUTES} dakikayı aşamaz "
                f"(verilen: {toplam})"
            )
        return self

    @model_validator(mode="after")
    def _tutarli(self) -> Zamanlama:
        if self.start_mode == "fixed" and self.start_time is None:
            raise ValueError("Sabit başlangıçta saat verilmeli")
        if self.start_mode == "anchor" and self.anchor_reference is None:
            raise ValueError("Çalışma saatinden türetmede açılış/kapanış seçilmeli")
        if self.repeat == "weekly" and not self.weekdays:
            raise ValueError("Haftalık planda en az bir gün seçilmeli")
        if self.repeat == "monthly":
            ayin_gunu = self.month_day is not None
            ninci = self.month_nth is not None and self.month_weekday is not None
            if ayin_gunu == ninci:
                raise ValueError("Aylık planda ya ayın günü ya da n'inci hafta günü verilmeli")
        if self.times and self.every_hours is not None:
            raise ValueError("Saat listesi ile 'her N saat' birlikte verilmez")
        if self.every_hours is not None and self.until_time is None:
            raise ValueError("'Her N saat' kuralında gün içi bitiş saati verilmeli")
        if self.start_mode == "anchor" and (self.times or self.every_hours is not None):
            raise ValueError(
                "Çalışma saatinden türetilen pencere gün içinde tekrarlanamaz: "
                "açılış/kapanış günde bir kez"
            )
        if self.ends_on is not None and self.ends_on < self.starts_on:
            raise ValueError("Bitiş tarihi başlangıçtan önce olamaz")
        if len(self._saatler()) > MAX_GUNLUK_PENCERE:
            raise ValueError(f"Gün içinde en çok {MAX_GUNLUK_PENCERE} pencere açılabilir")
        return self

    def _saatler(self) -> list[time]:
        """Gün içindeki pencere başlangıçları.

        Tek saatlik planda boş döner: o saat `dtstart`ten geliyor ve
        tekrar dizgesine yazmaya gerek yok.
        """
        if self.every_hours is not None and self.start_time and self.until_time:
            saatler: list[time] = []
            an = datetime.combine(date.min, self.start_time)
            son = datetime.combine(date.min, self.until_time)
            while an <= son:
                saatler.append(an.time())
                an += timedelta(hours=self.every_hours)
            return saatler
        return sorted(set(self.times))

    def _tekrar_govdesi(self) -> str:
        if self.repeat == "weekly":
            gunler = ",".join(GUN_KISA[g] for g in sorted(set(self.weekdays)))
            return f"FREQ=WEEKLY;BYDAY={gunler}"
        if self.repeat == "monthly":
            if self.month_day is not None:
                return f"FREQ=MONTHLY;BYMONTHDAY={self.month_day}"
            assert self.month_nth is not None  # _tutarli garantisi
            assert self.month_weekday is not None
            return f"FREQ=MONTHLY;BYDAY={self.month_nth}{GUN_KISA[self.month_weekday]}"
        if self.repeat == "once":
            return "FREQ=DAILY;COUNT=1"  # tek seferlik (FR-0512)
        return "FREQ=DAILY"

    def rrule(self) -> str:
        """RFC 5545 metni. Arayüz seçenek der, motor kural alır (FR-0503).

        Gün içinde birden çok pencere varsa her saat için ayrı bir
        `RRULE` satırı yazılıyor. `BYHOUR=9,14;BYMINUTE=0,30` yazmak
        dört pencere üretirdi (9:00, 9:30, 14:00, 14:30); satır başına
        bir saat, dakikası farklı saatleri de doğru veriyor.
        """
        govde = self._tekrar_govdesi()
        if self.ends_on is not None:
            govde += f";UNTIL={self.ends_on.strftime('%Y%m%d')}T235959"

        saatler = self._saatler()
        if len(saatler) <= 1:
            return govde
        return "\n".join(
            f"RRULE:{govde};BYHOUR={saat.hour};BYMINUTE={saat.minute}" for saat in saatler
        )

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
    #: Hangi liste olduğu. Saha kartı yalnızca şube adını yazıyordu;
    #: iki liste de "Kadıköy" görünüyor, hangi işin yapılacağı ancak
    #: liste açılınca öğreniliyordu (bağımsız test turu B10).
    plan_name: str
    branch_id: UUID
    branch_name: str
    business_day: date
    window_start: datetime
    window_end: datetime
    tolerance_end: datetime
    #: Yazmanın açıldığı an (pencere başlangıcı eksi hazırlık payı).
    #: Saha istemcisi listeyi bundan önce doldurmaya davet etmemeli.
    writable_from: datetime
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


def _plan_adlari(servis: PlanService) -> dict[UUID, str]:
    return {plan.id: plan.name for plan in servis.list_plans(include_inactive=True)}


def _calistirma(
    run: Run,
    adlar: dict[UUID, str],
    simdi: datetime,
    plan_adlari: dict[UUID, str],
) -> CalistirmaOzet:
    durum, gec = run.state_at(simdi)
    return CalistirmaOzet(
        id=run.id,
        plan_id=run.plan_id,
        plan_name=plan_adlari.get(run.plan_id, "Liste"),
        branch_id=run.branch_id,
        branch_name=adlar.get(run.branch_id, "—"),
        business_day=run.business_day,
        window_start=run.window_start,
        window_end=run.window_end,
        tolerance_end=run.tolerance_end,
        writable_from=run.writable_from(ayarlar().run_prep_minutes),
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
    kullanici: Gozlemci,
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
        runs=[_calistirma(r, adlar, simdi, {plan.id: plan.name}) for r in runs],
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
    reminders_queued: int = Field(default=0, description="Kuyruğa konan hatırlatma sayısı")
    sent: int = Field(default=0, description="Kanala verilen bildirim sayısı")
    failed: int = Field(
        default=0, description="Gönderilemeyen bildirim: sürücü yoksa hepsi buraya düşer"
    )
    stamped: int = Field(default=0, description="Damgalanan kanıt sayısı (ST-040)")
    swept: int = Field(
        default=0, description="Baytı hiç gelmediği için silinen bekleyen kanıt sayısı"
    )
    recovered: int = Field(
        default=0,
        description=(
            "Baytı depoda bulunup tamamlanan kanıt sayısı: istemci `complete` demeden düşmüş"
        ),
    )
    anchored: int = Field(default=0, description="Bu turda günlük kökü çıpalandı mı (FR-1302)")
    exports_done: int = Field(default=0, description="Üretilen arka plan çıktısı (FR-1217)")
    exports_failed: int = Field(
        default=0, description="Üretilemeyen çıktı: sebebi iş kaydında duruyor"
    )
    export_files_swept: int = Field(
        default=0, description="Süresi dolduğu için silinen çıktı dosyası sayısı"
    )


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
    return TurYaniti(
        at=sonuc.at,
        created=sonuc.created,
        deleted=sonuc.deleted,
        missed=sonuc.missed,
        actions_opened=sonuc.actions_opened,
        reminders_queued=sonuc.reminders_queued,
        sent=sonuc.sent,
        failed=sonuc.failed,
        stamped=sonuc.stamped,
        swept=sonuc.swept,
        recovered=sonuc.recovered,
        anchored=sonuc.anchored,
        exports_done=sonuc.exports_done,
        exports_failed=sonuc.exports_failed,
        export_files_swept=sonuc.export_files_swept,
    )


@router.get("/runs", summary="Bir iş gününün çalıştırmaları")
def calistirmalar(
    servis: Servis,
    org: OrgServis,
    kullanici: Kullanici,
    kurulum: KurulumServis,
    business_day: date | None = None,
) -> list[CalistirmaOzet]:
    """Gün verilmezse "şu an çalışılabilir olanlar", verilirse tam o gün.

    Saha istemcisi bunu gün vermeden çağırıyor ve sorduğu şey "bugünün
    iş günü hangisi" değil, **"şimdi neyi doldurabilirim"**. Kapanış
    vardiyası gece yarısını aşıyor: 22:00–01:30 penceresinin iş günü
    dünse, saat 00:30'da liste hâlâ açıktır ama artık "bugün" değildir.
    Yalnızca bugünü döndürmek kartı personelin elindeyken ekrandan
    siliyordu (BR-01, bağımsız test turu B11'in ikinci yüzü).

    Bu yüzden gün verilmediğinde dünün **hâlâ açık** çalıştırmaları da
    listeye giriyor. Gün açıkça verildiğinde (pano, raporlar) anlam
    değişmiyor: tam o iş günü.
    """
    adlar = _sube_adlari(org)
    kapsam = erisilebilir_sube_idleri(kullanici, org)
    simdi = datetime.now(UTC)

    gun = business_day or bugun(kurulum)
    runs = list(servis.runs_for_day(gun))
    if business_day is None:
        runs += [r for r in servis.runs_for_day(gun - timedelta(days=1)) if r.tolerance_end > simdi]
    runs = sorted(
        (r for r in runs if r.branch_id in kapsam),
        key=lambda r: (r.window_start, str(r.branch_id)),
    )

    plan_adlari = _plan_adlari(servis)
    return [_calistirma(r, adlar, simdi, plan_adlari) for r in runs]
