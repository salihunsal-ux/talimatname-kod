"""Ekle-yalnız olay günlüğü ve hash zinciri (ST-099; FR-1301).

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-31

İki şey burada veritabanına yazılı, koda değil:

**Ekle-yalnızlık.** Uygulama rolüne yalnızca SELECT ve INSERT
veriliyor; UPDATE ve DELETE yok (TC-100). Kodda silme yöntemi
bulunmaması iyi niyettir, yetkinin olmaması güvencedir: uygulamada
bir açık bulan da günlüğü düzeltemez.

**Zincirin çatallanmaması.** `(tenant_id, sequence)` tekil. İki istek
aynı anda yazmaya kalkarsa ikincisi tekillik hatası alır ve servis
yeni başı okuyup tekrar dener — iki ayrı dalın oluşması, zincirin
doğrulanamaz hâle gelmesi demek olurdu.

`created_at` yok: olayın zamanı `at` ve **sunucu saatidir** (FR-1301).
Cihaz saati kanıt kaydında ayrıca duruyor; günlükte iki zaman tutmak,
hangisinin delil olduğunu belirsizleştirirdi.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

APP_ROLE = "talimatname_app"
TABLO = "audit_event"


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
        sa.Column("sequence", sa.BigInteger(), nullable=False),
        sa.Column("event_type", sa.String(40), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("object_type", sa.String(30), nullable=False),
        sa.Column("object_id", sa.Uuid()),
        sa.Column("actor_id", sa.Uuid()),
        sa.Column("ip", sa.String(45)),
        sa.Column("device", sa.String(120)),
        sa.Column("before", JSONB, nullable=False, server_default="{}"),
        sa.Column("after", JSONB, nullable=False, server_default="{}"),
        sa.Column("prev_hash", sa.String(64), nullable=False),
        sa.Column("hash", sa.String(64), nullable=False),
        sa.UniqueConstraint("tenant_id", "sequence", name="uq_audit_sira"),
    )
    op.create_index("ix_audit_nesne", TABLO, ["tenant_id", "object_id"])
    op.create_index("ix_audit_zaman", TABLO, ["tenant_id", "at"])

    # Ekle-yalnız: UPDATE ve DELETE **verilmiyor** (TC-100).
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
    op.drop_index("ix_audit_zaman", table_name=TABLO)
    op.drop_index("ix_audit_nesne", table_name=TABLO)
    op.drop_table(TABLO)
