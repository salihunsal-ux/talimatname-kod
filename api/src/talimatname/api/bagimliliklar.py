"""Bağımlılıklar: hangi kalıcılık adaptörünün kullanılacağı tek yerde.

`DATABASE_URL` doluysa **PostgreSQL** adaptörleri, boşsa **bellek içi**
adaptörler kullanılır. Servis katmanı ve uç noktalar iki durumda da aynı
kodu çalıştırır (ADR-0014 md.2).

Bellek içi adaptör bir geliştirme kolaylığıdır: veritabanı olmadan panel
açılır, saf alan testleri koşar. Kalıcılık gerektiren her şey — geçmiş,
raporlar, kanıt — PostgreSQL ister.
"""

from __future__ import annotations

from functools import lru_cache

from talimatname.infra.memory import (
    MemoryActionRepository,
    MemoryAnswerRepository,
    MemoryOrganizationRepository,
    MemoryPlanRepository,
    MemoryTemplateRepository,
    MemoryUserRepository,
)
from talimatname.services.actions import ActionRepository, ActionService
from talimatname.services.auth import AuthService
from talimatname.services.dashboard import DashboardService
from talimatname.services.execution import AnswerRepository, ExecutionService
from talimatname.services.organization import OrganizationRepository, OrganizationService
from talimatname.services.plans import PlanRepository, PlanService
from talimatname.services.scheduler import SchedulerService
from talimatname.services.templates import TemplateRepository, TemplateService
from talimatname.services.users import UserRepository, UserService
from talimatname.settings import get_settings


def sql_modu() -> bool:
    """Kalıcı mod mu? Tek karar noktası."""
    return get_settings().database_url is not None


def _kiraci() -> object:
    from talimatname.seed import DEV_TENANT

    return DEV_TENANT


# --- depolar (süreç başına tek örnek) ---------------------------------


@lru_cache
def _org_deposu() -> OrganizationRepository:
    if sql_modu():
        from talimatname.infra.db.adapters import SqlOrganizationRepository

        return SqlOrganizationRepository(_kiraci())  # type: ignore[arg-type]
    return MemoryOrganizationRepository()


@lru_cache
def _kullanici_deposu() -> UserRepository:
    if sql_modu():
        from talimatname.infra.db.adapters import SqlUserRepository

        return SqlUserRepository(_kiraci())  # type: ignore[arg-type]
    return MemoryUserRepository()


@lru_cache
def _sablon_deposu() -> TemplateRepository:
    if sql_modu():
        from talimatname.infra.db.adapters import SqlTemplateRepository

        return SqlTemplateRepository(_kiraci())  # type: ignore[arg-type]
    return MemoryTemplateRepository()


@lru_cache
def _plan_deposu() -> PlanRepository:
    if sql_modu():
        from talimatname.infra.db.adapters import SqlPlanRepository

        return SqlPlanRepository(_kiraci())  # type: ignore[arg-type]
    return MemoryPlanRepository()


@lru_cache
def _cevap_deposu() -> AnswerRepository:
    if sql_modu():
        from talimatname.infra.db.adapters import SqlAnswerRepository

        return SqlAnswerRepository(_kiraci())  # type: ignore[arg-type]
    return MemoryAnswerRepository()


@lru_cache
def _aksiyon_deposu() -> ActionRepository:
    if sql_modu():
        from talimatname.infra.db.adapters import SqlActionRepository

        return SqlActionRepository(_kiraci())  # type: ignore[arg-type]
    return MemoryActionRepository()


# --- servisler --------------------------------------------------------


@lru_cache
def _kimlik_servisi() -> AuthService:
    """Tek örnek: OTP durumu süreç içinde tutuluyor (kısa ömürlü)."""
    return AuthService(_kullanici_deposu())


def kimlik_servisi() -> AuthService:
    return _kimlik_servisi()


def organizasyon_servisi() -> OrganizationService:
    return OrganizationService(_org_deposu())


def kullanici_servisi() -> UserService:
    return UserService(_kullanici_deposu(), _org_deposu())


def sablon_servisi() -> TemplateService:
    return TemplateService(_sablon_deposu())


def aksiyon_servisi() -> ActionService:
    return ActionService(_aksiyon_deposu(), _org_deposu(), _plan_deposu())


def zamanlayici_servisi() -> SchedulerService:
    return SchedulerService(
        _plan_deposu(),
        _org_deposu(),
        _sablon_deposu(),
        ActionService(_aksiyon_deposu(), _org_deposu(), _plan_deposu()),
    )


def plan_servisi() -> PlanService:
    _ilk_tur()
    return PlanService(_plan_deposu(), _org_deposu(), _sablon_deposu())


def yurutme_servisi() -> ExecutionService:
    _ilk_tur()
    return ExecutionService(_cevap_deposu(), _plan_deposu(), _sablon_deposu())


def pano_servisi() -> DashboardService:
    _ilk_tur()
    return DashboardService(_plan_deposu(), _org_deposu())


# --- geliştirme kolaylığı ---------------------------------------------

_ilk_tur_kosuldu = False


def _ilk_tur() -> None:
    """Zamanlayıcı süreci açık değilken ilk istekte bir tur atar.

    Üretimde zamanlayıcı ayrı süreçtir (ST-027); bu kanca yalnızca
    geliştiricinin panelde boş pano görmemesi içindir ve idempotenttir.
    """
    global _ilk_tur_kosuldu
    if not _ilk_tur_kosuldu:
        _ilk_tur_kosuldu = True
        zamanlayici_servisi().tick()
