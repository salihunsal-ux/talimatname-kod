"""Yenileme belirteci ve oturum kaydı (ST-004; FR-0203).

Revision ID: 0011
Revises: 0010
Create Date: 2026-11-08

Oturum tek başına 30 dakikalık bir erişim belirteciydi. İki eksik
vardı: vardiya boyunca açık kalması gereken saha listesi yarım saatte
bir giriş isteyemez, ve JWT durumsuz olduğu için bir oturumu iptal
etmenin yolu yoktu (`docs/04-gereksinimler/08-oturum-suresi-acigi.md`).

Bu tablo yenileme belirtecini tutuyor — **sırrın kendisini değil,
özetini**: veritabanını okuyabilen biri canlı oturumları ele
geçirmesin. Satır güncellenebiliyor (iptal, son kullanım, döndürme),
yani olay günlüğünün aksine ekle-yalnız değil.

`token_digest` tekil: iki oturum aynı sırra sahip olamaz, ve yenileme
tek indeks okumasıyla bulunuyor.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None

APP_ROLE = "talimatname_app"
TABLO = "user_session"


def upgrade() -> None:
    op.create_table(
        TABLO,
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.Uuid(),
            sa.ForeignKey("tenant.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("app_user.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token_digest", sa.String(64), nullable=False),
        sa.Column("kind", sa.String(8), nullable=False, server_default="web"),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("device", sa.String(120)),
        sa.Column("last_used_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_reason", sa.String(24)),
        sa.Column("replaced_by", sa.Uuid()),
        sa.UniqueConstraint("token_digest", name="uq_oturum_ozet"),
    )
    # Kullanıcının oturum listesi (FR-0203) ve süresi geçenlerin
    # süpürülmesi: ikisi de bu indeksi kullanıyor.
    op.create_index("ix_oturum_kullanici", TABLO, ["tenant_id", "user_id", "expires_at"])

    # Günlüğün aksine güncellenebilir: iptal ve döndürme satırı değiştirir.
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
    op.drop_index("ix_oturum_kullanici", table_name=TABLO)
    op.drop_table(TABLO)
