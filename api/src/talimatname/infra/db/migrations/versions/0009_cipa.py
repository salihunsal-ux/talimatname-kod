"""Günlük kökünün dış damgası (ST-103; FR-1302).

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-01

Hash zinciri kayıtları tek tek değiştirmeyi görünür kılıyor ama
veritabanına yazabilen birinin zinciri baştan hesaplamasını
engellemiyordu. Bu tablo o boşluğu kapatıyor: günün kökü dışarıdaki
bir otoriteye tarihletiliyor ve damga burada duruyor.

Tablo **ekle-yalnız**, günlüğün kendisi gibi: uygulama rolüne
`UPDATE`/`DELETE` verilmiyor. Bir çıpayı sonradan düzeltebilmek,
çıpanın anlamını ortadan kaldırırdı.

Başarısız denemeler de satır açıyor (`state='failed'`): çıpasız bir
gün, çıpalı sanılmasın.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None

APP_ROLE = "talimatname_app"
TABLO = "audit_anchor"


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
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sequence", sa.BigInteger(), nullable=False),
        sa.Column("chain_hash", sa.String(64), nullable=False),
        sa.Column("state", sa.String(10), nullable=False, server_default="ok"),
        # Damga birkaç kilobayt (sertifika zinciri dahil). Nesne
        # deposuna koymadık: çıpa kaydıyla damga birlikte durmalı,
        # yoksa biri kaybolunca öteki işe yaramaz.
        sa.Column("token", sa.LargeBinary()),
        sa.Column("stamped_at", sa.DateTime(timezone=True)),
        sa.Column("tsa_name", sa.String(200)),
        sa.Column("serial", sa.String(64)),
        sa.Column("error", sa.String(200)),
    )
    op.create_index("ix_cipa_zaman", TABLO, ["tenant_id", "created_at"])

    # Ekle-yalnız: günlükle aynı kural (göç 0006).
    op.execute(f'GRANT SELECT, INSERT ON {TABLO} TO "{APP_ROLE}"')
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
    op.drop_index("ix_cipa_zaman", table_name=TABLO)
    op.drop_table(TABLO)
