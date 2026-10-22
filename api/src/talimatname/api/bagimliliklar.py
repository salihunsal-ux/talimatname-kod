"""Bağımlılıklar: hangi kalıcılık adaptörünün kullanılacağı tek yerde.

Bugün bellek içi adaptör; `DATABASE_URL` tanımlandığında (ücretsiz bulut
PostgreSQL, ADR-0012 md.2) burada PostgreSQL adaptörü döner. Servis
katmanı ve uç noktalar değişmez.
"""

from __future__ import annotations

from functools import lru_cache

from talimatname.infra.memory import MemoryOrganizationRepository, MemoryUserRepository
from talimatname.services.organization import OrganizationService
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


def kullanici_servisi() -> UserService:
    _veritabani_kontrolu()
    return UserService(_bellek_kullanici_deposu(), _bellek_deposu())
