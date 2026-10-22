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
from talimatname.services.organization import OrganizationService
from talimatname.services.plans import PlanService
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


def plan_servisi() -> PlanService:
    _veritabani_kontrolu()
    servis = PlanService(_bellek_plan_deposu(), _bellek_deposu(), _bellek_sablon_deposu())
    _ilk_uretim(servis)
    return servis


_uretildi = False


def _ilk_uretim(servis: PlanService) -> None:
    """Tohum planların çalıştırmaları ilk istekte üretilir.

    Zamanlayıcı (ST-027) yazılınca bu kalkar: üretim o zaman saatlik işin
    sorumluluğu olur. Burada durması, panelin boş bir pano göstermemesi
    içindir ve idempotenttir.
    """
    global _uretildi
    if not _uretildi:
        servis.generate_all()
        _uretildi = True


def kullanici_servisi() -> UserService:
    _veritabani_kontrolu()
    return UserService(_bellek_kullanici_deposu(), _bellek_deposu())
