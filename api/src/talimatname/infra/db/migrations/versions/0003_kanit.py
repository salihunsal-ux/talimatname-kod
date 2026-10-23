"""Kanıt tablosu ve şube koordinatları.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-23

İki değişiklik:

1. `branch.latitude` / `branch.longitude` — kanıtın "konum şube dışında"
   bayrağı bir ölçüye dayansın (FR-0615, BR-15). İkisi de boş olabilir;
   tanımsızsa bayrak verilmez.
2. `evidence` — kanıt dosyası ve bağlamı (FR-0606).

`sha256` üzerinde **kiracı içinde tekil** indeks var (FR-0614). Servis
katmanındaki denetim iki eşzamanlı yüklemede kaçabilir; indeks kaçmaz.
Tekilliği veritabanına yazmak, ürünün tek iddiasını koda değil şemaya
bağlamak demek.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

APP_ROLE = "talimatname_app"
TABLO = "evidence"


def upgrade() -> None:
    op.add_column("branch", sa.Column("latitude", sa.Float()))
    op.add_column("branch", sa.Column("longitude", sa.Float()))

    op.create_table(
        TABLO,
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.Uuid(),
            sa.ForeignKey("tenant.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("run_id", sa.Uuid(), sa.ForeignKey("run.id", ondelete="CASCADE"), nullable=False),
        sa.Column("answer_id", sa.Uuid(), nullable=False),
        sa.Column("item_id", sa.Uuid(), nullable=False),
        sa.Column("branch_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid()),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("content_type", sa.String(40), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("storage_key", sa.String(200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(10), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True)),
        sa.Column("device_reported_at", sa.DateTime(timezone=True)),
        sa.Column("clock_skew_minutes", sa.Integer()),
        sa.Column("latitude", sa.Float()),
        sa.Column("longitude", sa.Float()),
        sa.Column("distance_meters", sa.Integer()),
        sa.Column("device_id", sa.Uuid()),
        sa.Column("from_gallery", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("flags", JSONB, nullable=False, server_default="[]"),
        sa.Column("stored_at", sa.DateTime(timezone=True)),
        sa.Column("stamped_at", sa.DateTime(timezone=True)),
        sa.Column("stamped_key", sa.String(200)),
        sa.Column("thumbnail_key", sa.String(200)),
    )
    op.create_index("ux_evidence_digest", TABLO, ["tenant_id", "sha256"], unique=True)
    op.create_index("ix_evidence_run", TABLO, ["tenant_id", "run_id"])

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
    op.drop_index("ix_evidence_run", table_name=TABLO)
    op.drop_index("ux_evidence_digest", table_name=TABLO)
    op.drop_table(TABLO)
    op.drop_column("branch", "longitude")
    op.drop_column("branch", "latitude")
