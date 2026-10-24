"""Kurulum sihirbazı servisi (ST-008; FR-1401, FR-0105, FR-0106).

Sihirbaz **kendi veri yolunu kurmaz**: şubeyi `OrganizationRepository`e,
şablonu şablon servisine, planı plan servisine yazar. Kendi yazma yolu
olsaydı, panelden eklenen şube ile sihirbazdan eklenen şube zamanla
farklı kurallardan geçerdi.

Sakladığı tek şey marka ayarları (`AccountSettings`): zincirin adı,
saat dilimi ve varsayılan çalışma saatleri. Varsayılan saatler Excel'de
boş bırakılan satırlar için kullanılıyor — zincirlerin çoğunda şubeler
aynı saatlerde açılıyor ve her satıra aynı saati yazdırmak yalnızca
yükleme hatası üretir.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime, time, timedelta
from typing import Protocol
from uuid import UUID, uuid4

import structlog

from talimatname.domain.errors import DomainError, ErrorKind
from talimatname.domain.organization import Branch, Region
from talimatname.domain.plans import Plan
from talimatname.domain.setup import (
    AccountSettings,
    BranchRow,
    ImportReport,
    SetupProgress,
    progress,
)
from talimatname.domain.window import BusinessHours, WindowRule
from talimatname.services.imports import ImportFailed, branch_template, parse_branches
from talimatname.services.library import (
    CATALOG,
    LibraryTemplate,
    find,
    find_by_name,
    plan_name,
)
from talimatname.services.organization import OrganizationRepository
from talimatname.services.plans import HORIZON_DAYS, PlanRepository, PlanService
from talimatname.services.templates import TemplateRepository, TemplateService
from talimatname.services.users import UserRepository

log = structlog.get_logger(__name__)


class LibraryTemplateNotFound(DomainError):
    code = "kutuphane-sablonu-yok"
    title = "Kütüphanede böyle bir şablon yok"
    kind: ErrorKind = "not_found"


class NoPendingTemplate(DomainError):
    code = "plansiz-sablon-yok"
    title = "Planı bekleyen yayınlanmış şablon yok"
    kind: ErrorKind = "not_found"


class NoBranches(DomainError):
    code = "sube-yok"
    title = "Önce en az bir şube eklenmeli"
    kind: ErrorKind = "invalid"


@dataclass(frozen=True, slots=True)
class PublishResult:
    """Yayın özeti: kaç çalıştırma hazır ve ilk pencere ne zaman açılıyor."""

    runs_ready: int
    first_window: datetime | None


class SettingsRepository(Protocol):
    """Marka ayarlarının kalıcılık portu."""

    def settings(self) -> AccountSettings | None: ...

    def save_settings(self, settings: AccountSettings) -> None: ...


class SetupService:
    def __init__(
        self,
        repo: SettingsRepository,
        org: OrganizationRepository,
        templates: TemplateRepository,
        plans: PlanRepository,
        users: UserRepository,
        *,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._repo = repo
        self._org = org
        self._templates = templates
        self._plans = plans
        self._users = users
        self._now = now

    # --- okuma -------------------------------------------------------

    def settings(self) -> AccountSettings | None:
        return self._repo.settings()

    def progress(self) -> SetupProgress:
        """Adımların durumu — veriden türetilir, sayaç tutulmaz."""
        ayar = self._repo.settings()
        yayinda = sum(
            1
            for sablon in self._templates.templates()
            for surum in self._templates.versions(sablon.id)
            if surum.status == "published"
        )
        etkin = sum(1 for plan in self._plans.plans() if plan.active)
        durum = progress(
            settings=ayar,
            branch_count=len(self._org.branches()),
            published_template_count=yayinda,
            active_plan_count=etkin,
            staff_count=len(self._users.users()),
        )
        return replace(durum, completed_at=ayar.completed_at if ayar else None)

    def template_file(self) -> bytes:
        """Doldurulacak Excel şablonu (FR-0105)."""
        ayar = self._repo.settings()
        return branch_template(
            brand_name=ayar.brand_name if ayar else "Talimatname",
            default_timezone=ayar.timezone if ayar else "Europe/Istanbul",
            default_hours=ayar.default_hours if ayar else {},
        )

    # --- yazma -------------------------------------------------------

    def save_brand(
        self,
        *,
        brand_name: str,
        timezone: str,
        open_time: time | None = None,
        close_time: time | None = None,
        closed_days: tuple[int, ...] = (),
        logo_url: str | None = None,
    ) -> AccountSettings:
        """Adım 1. Saatler verilmezse mevcut varsayılan korunur."""
        mevcut = self._repo.settings()
        saatler = dict(mevcut.default_hours) if mevcut else {}
        if open_time is not None and close_time is not None:
            saatler = {gun: BusinessHours(open_time, close_time) for gun in range(7)}
        for gun in closed_days:
            saatler[gun] = None

        ayar = AccountSettings(
            brand_name=brand_name,
            timezone=timezone,
            default_hours=saatler,
            logo_url=logo_url,
            completed_at=mevcut.completed_at if mevcut else None,
        ).validated()
        self._repo.save_settings(ayar)
        return ayar

    def import_branches(
        self,
        data: bytes,
        *,
        apply: bool = True,
        raise_on_reject: bool = True,
    ) -> ImportReport:
        """Adım 2. Dosyayı okur, doğrular ve (istenirse) uygular.

        `apply=False` **kuru çalıştırma**: kullanıcı neyin olacağını
        yazmadan önce görsün. Sihirbaz önce bunu çağırıyor; onaylayınca
        aynı dosyayı `apply=True` ile gönderiyor.

        `raise_on_reject=False` yalnızca hata raporu üretirken: reddedilen
        dosyanın raporu da indirilebilmeli, yoksa kullanıcı neyi
        düzelteceğini göremez.
        """
        ayar = self._repo.settings()
        rapor = parse_branches(
            data,
            default_timezone=ayar.timezone if ayar else "Europe/Istanbul",
            default_hours=ayar.default_hours if ayar else {},
        )
        if rapor.rejected and raise_on_reject:
            # FR-0106: beşte birinden fazlası hatalıysa sorun satırlarda
            # değil dosyadadır; yarısını almak zarar verir.
            log.warning(
                "kurulum.dosya_reddedildi",
                toplam=rapor.total,
                hatali=rapor.error_rows,
            )
            raise ImportFailed(
                f"{rapor.total} satırın {rapor.error_rows} tanesi hatalı; dosya kabul edilmedi",
                errors=[
                    {"row": h.row, "field": h.field, "message": h.message} for h in rapor.errors
                ],
            )
        if not apply or rapor.rejected:
            return rapor

        bolgeler = {bolge.name.casefold(): bolge for bolge in self._org.regions()}
        yeni, guncel = 0, 0
        for satir in rapor.rows:
            bolge_id = self._bolge_id(satir, bolgeler)
            mevcut = self._org.branch_by_code(satir.code)
            if mevcut is None:
                self._org.save_branch(self._yeni_sube(satir, bolge_id))
                yeni += 1
            else:
                self._org.save_branch(self._guncelle(mevcut, satir, bolge_id))
                guncel += 1

        log.info("kurulum.subeler_yuklendi", yeni=yeni, guncel=guncel, hatali=rapor.error_rows)
        return replace(rapor, created=yeni, updated=guncel)

    # --- adım 3: kütüphane ------------------------------------------

    def library(self) -> tuple[LibraryTemplate, ...]:
        return CATALOG

    def use_template(self, key: str) -> tuple[UUID, UUID]:
        """Kütüphane şablonunu hesaba kopyalar ve **yayınlar**.

        Yayınlıyoruz çünkü sihirbazın amacı bir saat içinde çalışan bir
        liste; taslak bırakmak kullanıcıyı editörde ikinci bir tura
        sokardı. Kopya bağımsız: bizim kütüphaneyi güncellememiz
        zincirin listesini değiştirmez (ADR-0010).
        """
        sablon = find(key)
        if sablon is None:
            raise LibraryTemplateNotFound(f"anahtar: {key}")

        servis = TemplateService(self._templates, now=self._now)
        kopya, surum = sablon.copy_for_account()
        self._templates.save_template(kopya)
        self._templates.save_version(surum)
        yayin = servis.publish(surum.id)
        log.info("kurulum.sablon_kopyalandi", anahtar=key, sablon=str(kopya.id))
        return kopya.id, yayin.id

    # --- adım 4: plan önerisi ---------------------------------------

    def pending_version(self) -> UUID | None:
        """Planı olmayan ilk yayınlanmış sürüm.

        Sihirbaz "hangi şablonu seçmiştim" diye bir durum tutmuyor:
        hesapta yayınlanmış ama planı olmayan sürüm zaten odur.
        Tarayıcı kapanıp açılsa da adım 4 aynı yeri gösteriyor (TC-004).
        """
        planli = {plan.template_version_id for plan in self._plans.plans()}
        for sablon in self._templates.templates():
            for surum in self._templates.versions(sablon.id):
                if surum.status == "published" and surum.id not in planli:
                    return surum.id
        return None

    def plan_proposal(self, version_id: UUID | None = None) -> Plan:
        """Şube saatlerinden türetilmiş plan **önerisi** (kaydetmez).

        Pencere `anchor` ile şube saatine bağlanıyor: tek plan, her
        şubede kendi kapanışına göre açılıyor. Sabit saat yazsaydık
        09:00 açılan şube ile 11:00 açılan şube aynı planı paylaşamazdı.
        """
        surum_id = version_id or self.pending_version()
        if surum_id is None:
            raise NoPendingTemplate("Planı olmayan yayınlanmış şablon yok")
        surum = self._templates.version(surum_id)
        sablon_kaydi = self._templates.template(surum.template_id) if surum else None
        sablon = find_by_name(sablon_kaydi.name) if sablon_kaydi else None
        if sablon is None:
            raise LibraryTemplateNotFound(
                f"sürüm {surum_id} kütüphane şablonundan gelmiyor; planı plan ekranından kurun"
            )
        version_id = surum_id
        subeler = [sube.id for sube in self._org.branches() if sube.status == "active"]
        if not subeler:
            raise NoBranches("Plan önerisi için şube gerekiyor")
        ayar = self._repo.settings()
        return Plan(
            id=uuid4(),
            name=plan_name(sablon, ayar.brand_name if ayar else None),
            template_version_id=version_id,
            branch_ids=tuple(subeler),
            rule=WindowRule(
                recurrence=sablon.plan.recurrence,
                starts_on=self._now().date(),
                duration_minutes=sablon.plan.duration_minutes,
                anchor=sablon.plan.anchor,
                tolerance_minutes=sablon.plan.tolerance_minutes,
            ),
        ).validated()

    def create_plan(self, plan: Plan) -> Plan:
        """Öneriyi (düzenlenmiş hâliyle) kaydeder."""
        servis = PlanService(self._plans, self._org, self._templates, now=self._now)
        kayitli = servis.create(plan)
        log.info("kurulum.plan_olusturuldu", plan=str(kayitli.id), sube=len(kayitli.branch_ids))
        return kayitli

    # --- yayın --------------------------------------------------------

    def publish(self, *, days: int = HORIZON_DAYS) -> tuple[AccountSettings, PublishResult]:
        """Sihirbazı kapatır ve çalıştırmaların hazır olduğunu doğrular.

        Üretim idempotent ve plan kaydedilirken zaten koşuyor; burada
        **üretilen** değil **hazır olan** sayılıyor. "7 yeni çalıştırma"
        demek, ikinci kez basıldığında sıfır göstermek demekti — oysa
        kullanıcının sorusu "liste hazır mı", "kaç tane yazdın" değil.
        """
        servis = PlanService(self._plans, self._org, self._templates, now=self._now)
        servis.generate_all(days=days)

        bugun = self._now().date()
        son = bugun + timedelta(days=days - 1)
        kosular = [r for r in self._plans.runs() if bugun <= r.business_day <= son]
        ilk = min((r.window_start for r in kosular), default=None)
        ayar = self.complete()
        log.info("kurulum.yayinlandi", calistirma=len(kosular), ilk_pencere=str(ilk))
        return ayar, PublishResult(runs_ready=len(kosular), first_window=ilk)

    def complete(self) -> AccountSettings:
        """Sihirbazı kapatır (yayın sonrası). Marka ayarı yoksa oluşturulur."""
        mevcut = self._repo.settings() or AccountSettings(brand_name="Talimatname").validated()
        kapali = replace(mevcut, completed_at=self._now())
        self._repo.save_settings(kapali)
        log.info("kurulum.tamamlandi")
        return kapali

    def reopen(self) -> AccountSettings | None:
        """Sihirbazı yeniden açar: yeni şube turu için gerekebiliyor."""
        mevcut = self._repo.settings()
        if mevcut is None:
            return None
        acik = replace(mevcut, completed_at=None)
        self._repo.save_settings(acik)
        return acik

    # --- yardımcılar --------------------------------------------------

    def _bolge_id(self, satir: BranchRow, bolgeler: dict[str, Region]) -> UUID | None:
        """Bölge adı yazılmışsa bulur, yoksa **oluşturur**.

        Excel'de bölge adı serbest metin; kullanıcıdan önce bölgeleri
        tanımlamasını istemek, iki adımlı bir işi dört adıma çıkarırdı.
        """
        if not satir.region:
            return None
        anahtar = satir.region.casefold()
        mevcut = bolgeler.get(anahtar)
        if mevcut is not None:
            return mevcut.id
        bolge = Region(id=uuid4(), name=satir.region).validated()
        self._org.save_region(bolge)
        bolgeler[anahtar] = bolge
        return bolge.id

    @staticmethod
    def _yeni_sube(satir: BranchRow, region_id: UUID | None) -> Branch:
        return Branch(
            id=uuid4(),
            code=satir.code,
            name=satir.name,
            timezone=satir.timezone,
            business_hours=satir.hours,
            region_id=region_id,
            address=satir.address,
            latitude=satir.latitude,
            longitude=satir.longitude,
        ).validated()

    @staticmethod
    def _guncelle(mevcut: Branch, satir: BranchRow, region_id: UUID | None) -> Branch:
        """Var olan şube **güncellenir**, kopyası açılmaz.

        Şube kodu zincirin kendi anahtarı (FR-0103); aynı kodla gelen
        satır "yeni şube" değil, "bu şubenin güncel hâli"dir. Dosyayı
        ikinci kez yüklemek bu yüzden zarar vermiyor.
        """
        return replace(
            mevcut,
            name=satir.name,
            timezone=satir.timezone,
            business_hours=satir.hours,
            region_id=region_id if region_id is not None else mevcut.region_id,
            address=satir.address if satir.address is not None else mevcut.address,
            latitude=satir.latitude if satir.latitude is not None else mevcut.latitude,
            longitude=satir.longitude if satir.longitude is not None else mevcut.longitude,
        ).validated()
