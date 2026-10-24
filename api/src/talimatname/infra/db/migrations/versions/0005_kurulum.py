"""Marka ayarları tablosu (kurulum sihirbazı adım 1).

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-24

Sihirbazın sakladığı tek durum burası: zincirin adı, saat dilimi ve
varsayılan çalışma saatleri (FR-1401). İlerleme sayacı **yok** —
hangi adımda kalındığı veriden türetiliyor (şube varsa 2. adım
bitmiştir), böylece panelden elle şube ekleyen bir yöneticide sayaç ile
gerçek ayrışmıyor.

`tenant` tablosuna eklemedik: orası RLS'in kökü ve uygulama rolünün
yalnızca okuma izni var; hesap açmak ya da silmek uygulamanın işi değil.
Marka ayarı ise uygulamanın yazdığı veri, bu yüzden diğer tablolar gibi
kiracıya bağlı ve RLS'li.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

APP_ROLE = "talimatname_app"
TABLO = "account_settings"


def upgrade() -> None:
    op.create_table(
        TABLO,
        sa.Column(
            "tenant_id",
            sa.Uuid(),
            sa.ForeignKey("tenant.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("brand_name", sa.String(120), nullable=False),
        sa.Column("timezone", sa.String(64), nullable=False, server_default="Europe/Istanbul"),
        sa.Column("default_hours", JSONB, nullable=False, server_default="{}"),
        sa.Column("logo_url", sa.String(400)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
    )

    op.execute(f'GRANT SELECT, INSERT, UPDATE, DELETE ON {TABLO} TO "{APP_ROLE}"')
    op.execute(f"ALTER TABLE {TABLO} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {TABLO} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY kiraci_yalitimi ON {TABLO}
        USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
        WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
        """
    )


def downgrade() -> None:
    op.execute(f"DROP POLICY IF EXISTS kiraci_yalitimi ON {TABLO}")
    op.drop_table(TABLO)
