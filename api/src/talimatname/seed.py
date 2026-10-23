"""Tohum verisini veritabanına yazar (idempotent).

    python -m talimatname.seed

Bellek içi adaptörün tohumuyla **aynı** veriyi kullanır: Kahve Durağı
örnek zinciri. Böylece iki adaptör aynı veriyle çalışır ve ekranlar
veritabanına geçince değişmez.

Gerçek kişi ya da müşteri verisi yoktur (ADR-0003, ADR-0012 md.3).
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from uuid import UUID

import structlog
from sqlalchemy import text

from talimatname.api.app import configure_logging
from talimatname.infra.db.adapters import (
    SqlOrganizationRepository,
    SqlPlanRepository,
    SqlTemplateRepository,
    SqlUserRepository,
)
from talimatname.infra.db.session import create_db_engine
from talimatname.infra.memory import (
    MemoryOrganizationRepository,
    MemoryPlanRepository,
    MemoryTemplateRepository,
    MemoryUserRepository,
    sabit_id,
)
from talimatname.settings import get_settings

log = structlog.get_logger("seed")

#: Geliştirme kiracısı. Tek hesap; çok kiracılılık şemada ve RLS'te var.
DEV_TENANT = sabit_id("hesap:kahve-duragi")
DEV_TENANT_NAME = "Kahve Durağı (örnek zincir)"


def ensure_tenant(tenant_id: UUID = DEV_TENANT, name: str = DEV_TENANT_NAME) -> bool:
    """Kiracı satırını sahip rolüyle açar; açıldıysa True döner.

    Sahip rolü gerekiyor: `tenant` tablosunda uygulama rolünün yalnızca
    okuma yetkisi var — kiracı yaratmak uygulamanın işi değil.
    """
    motor = create_db_engine(as_owner=True)
    with motor.begin() as baglanti:
        var = baglanti.execute(
            text("SELECT 1 FROM tenant WHERE id = :id"), {"id": tenant_id}
        ).first()
        if var:
            return False
        baglanti.execute(
            text(
                "INSERT INTO tenant (id, name, default_timezone, created_at) "
                "VALUES (:id, :ad, 'Europe/Istanbul', :an)"
            ),
            {"id": tenant_id, "ad": name, "an": datetime.now(UTC)},
        )
        return True


def seed(tenant_id: UUID = DEV_TENANT) -> dict[str, int]:
    """Tohumu yazar. Var olan satırlar üzerine yazılır (idempotent)."""
    org_kaynak = MemoryOrganizationRepository()
    kullanici_kaynak = MemoryUserRepository()
    sablon_kaynak = MemoryTemplateRepository()
    plan_kaynak = MemoryPlanRepository()

    org = SqlOrganizationRepository(tenant_id)
    kullanicilar = SqlUserRepository(tenant_id)
    sablonlar = SqlTemplateRepository(tenant_id)
    planlar = SqlPlanRepository(tenant_id)

    # Bölgeler: adaptörde yazma yok (v1'de bölge yönetimi yok), doğrudan.
    from talimatname.infra.db import models as mdl
    from talimatname.infra.db.session import tenant_session

    with tenant_session(tenant_id) as o:
        for bolge in org_kaynak.regions():
            satir = o.get(mdl.Region, bolge.id) or mdl.Region(id=bolge.id, tenant_id=tenant_id)
            satir.name = bolge.name
            satir.code = bolge.code
            o.add(satir)

    for sube in org_kaynak.branches():
        org.save_branch(sube)

    with tenant_session(tenant_id) as o:
        for sube in org_kaynak.branches():
            for istasyon in org_kaynak.stations(sube.id):
                istasyon_satiri = o.get(mdl.Station, istasyon.id) or mdl.Station(
                    id=istasyon.id, tenant_id=tenant_id
                )
                istasyon_satiri.branch_id = istasyon.branch_id
                istasyon_satiri.name = istasyon.name
                istasyon_satiri.kind = istasyon.kind
                o.add(istasyon_satiri)

    for kullanici in kullanici_kaynak.users():
        kullanicilar.save_user(kullanici)

    for sablon in sablon_kaynak.templates():
        sablonlar.save_template(sablon)
        for surum in sablon_kaynak.versions(sablon.id):
            sablonlar.save_version(surum)

    for plan in plan_kaynak.plans():
        planlar.save_plan(plan)

    return {
        "bolge": len(org_kaynak.regions()),
        "sube": len(org_kaynak.branches()),
        "kullanici": len(kullanici_kaynak.users()),
        "sablon": len(sablon_kaynak.templates()),
        "plan": len(plan_kaynak.plans()),
    }


def main() -> int:
    configure_logging(get_settings().log_level)
    if not get_settings().database_url:
        log.error("seed.database_url_yok", ipucu="api/.env içine DATABASE_URL yazın")
        return 1
    yeni = ensure_tenant()
    sayilar = seed()
    log.info("seed.tamam", kiraci_acildi=yeni, **sayilar)
    return 0


if __name__ == "__main__":  # pragma: no cover - süreç girişi
    sys.exit(main())
