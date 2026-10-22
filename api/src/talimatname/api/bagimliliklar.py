"""Bağımlılıklar: hangi kalıcılık adaptörünün kullanılacağı tek yerde.

Bugün bellek içi adaptör; `DATABASE_URL` tanımlandığında (ücretsiz bulut
PostgreSQL, ADR-0012 md.2) burada PostgreSQL adaptörü döner. Servis
katmanı ve uç noktalar değişmez.
"""

from __future__ import annotations

from functools import lru_cache

from talimatname.infra.memory import MemoryOrganizationRepository
from talimatname.services.organization import OrganizationService
from talimatname.settings import get_settings


@lru_cache
def _bellek_deposu() -> MemoryOrganizationRepository:
    return MemoryOrganizationRepository()


def organizasyon_servisi() -> OrganizationService:
    ayar = get_settings()
    if ayar.database_url:
        # PostgreSQL adaptörü buraya gelecek; henüz yok, sessizce belleğe
        # düşmek yerine açıkça söyle.
        raise NotImplementedError(
            "PostgreSQL adaptörü henüz yazılmadı; DATABASE_URL'i boş bırakın "
            "(bellek içi tohum veri) — bkz. README · yerel ortam."
        )
    return OrganizationService(_bellek_deposu())
