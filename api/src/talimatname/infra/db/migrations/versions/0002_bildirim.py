"""Bildirim kuyruğu ve teslimat izi.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-23

Kuyruk ve iz aynı tablodadır: "ne gönderilecekti" ile "ne oldu" aynı
satırda durur (FR-1005). Yeni tablo da kiracı tablosudur — `tenant_id`,
`ENABLE` + `FORCE ROW LEVEL SECURITY` ve 0001'deki politikanın aynısı.
Tablo listesi burada **yeniden yazılıyor**, modelden okunmuyor: bir göç
kendi sürümündeki şemayı anlatır, ileride değişecek bir listeyi değil.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

APP_ROLE = "talimatname_app"
TABLO = "notification"


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
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("channel", sa.String(10), nullable=False),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("app_user.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(160), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("send_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("branch_id", sa.Uuid()),
        sa.Column("run_id", sa.Uuid()),
        sa.Column("action_id", sa.Uuid()),
        sa.Column("deep_link", sa.String(200)),
        sa.Column("status", sa.String(12), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
        sa.Column("delivered_at", sa.DateTime(timezone=True)),
        sa.Column("error_code", sa.String(40)),
        sa.Column("error_detail", sa.Text()),
    )
    op.create_index("ix_notification_due", TABLO, ["tenant_id", "status", "send_at"])

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
    op.drop_index("ix_notification_due", table_name=TABLO)
    op.drop_table(TABLO)
