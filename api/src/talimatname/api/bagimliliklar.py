"""Bağımlılıklar: hangi kalıcılık adaptörünün kullanılacağı tek yerde.

Bugün bellek içi adaptör; `DATABASE_URL` tanımlandığında (ücretsiz bulut
PostgreSQL, ADR-0012 md.2) burada PostgreSQL adaptörü döner. Servis
katmanı ve uç noktalar değişmez.
"""

from __future__ import annotations

from functools import lru_cache

from talimatname.infra.memory import (
    MemoryOrganizationRepository,
    MemoryPlanRepository,
    MemoryTemplateRepository,
    MemoryUserRepository,
)
from talimatname.services.dashboard import DashboardService
from talimatname.services.organization import OrganizationService
from talimatname.services.plans import PlanService
from talimatname.services.scheduler import SchedulerService
from talimatname.services.templates import TemplateService
from talimatname.services.users import UserService
from talimatname.settings import get_settings


@lru_cache
def _bellek_deposu() -> MemoryOrganizationRepository:
    return MemoryOrganizationRepository()


@lru_cache
def _bellek_kullanici_deposu() -> MemoryUserRepository:
    return MemoryUserRepository()


def _veritabani_kontrolu() -> None:
    """DATABASE_URL doluysa sessizce belleğe düşme; açıkça söyle."""
    if get_settings().database_url:
        raise NotImplementedError(
            "PostgreSQL adaptörü henüz yazılmadı; DATABASE_URL'i boş bırakın "
            "(bellek içi tohum veri) — bkz. README · veri."
        )


def organizasyon_servisi() -> OrganizationService:
    _veritabani_kontrolu()
    return OrganizationService(_bellek_deposu())


@lru_cache
def _bellek_sablon_deposu() -> MemoryTemplateRepository:
    return MemoryTemplateRepository()


def sablon_servisi() -> TemplateService:
    _veritabani_kontrolu()
    return TemplateService(_bellek_sablon_deposu())


@lru_cache
def _bellek_plan_deposu() -> MemoryPlanRepository:
    return MemoryPlanRepository()


def zamanlayici_servisi() -> SchedulerService:
    _veritabani_kontrolu()
    return SchedulerService(_bellek_plan_deposu(), _bellek_deposu(), _bellek_sablon_deposu())


def plan_servisi() -> PlanService:
    _veritabani_kontrolu()
    _ilk_tur()
    return PlanService(_bellek_plan_deposu(), _bellek_deposu(), _bellek_sablon_deposu())


_ilk_tur_kosuldu = False


def _ilk_tur() -> None:
    """Geliştirme kolaylığı: zamanlayıcı süreci açık değilken bir tur koşar.

    Zamanlayıcı (`python -m talimatname.scheduler`) ayrı süreçte çalışır;
    o çalışmıyorken panelin boş pano göstermemesi için ilk istekte bir tur
    atılır. İdempotent olduğu için iki yol çakışmaz.
    """
    global _ilk_tur_kosuldu
    if not _ilk_tur_kosuldu:
        _ilk_tur_kosuldu = True
        zamanlayici_servisi().tick()


def pano_servisi() -> DashboardService:
    _veritabani_kontrolu()
    _ilk_tur()
    return DashboardService(_bellek_plan_deposu(), _bellek_deposu())


def kullanici_servisi() -> UserService:
    _veritabani_kontrolu()
    return UserService(_bellek_kullanici_deposu(), _bellek_deposu())
