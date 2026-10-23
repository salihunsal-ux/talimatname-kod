"""İlk şema: tablolar, uygulama rolü ve RLS politikaları.

Revision ID: 0001
Revises:
Create Date: 2026-10-23

Üç kısım var ve sırası önemli:

1. **Rol** — `talimatname_app`, `NOBYPASSRLS`. Sahip rolü bu role üye
   yapılır ki uygulama `SET ROLE` ile geçebilsin (bu olmadan
   "permission denied to set role" alınır).
2. **Tablolar** — modellerden.
3. **RLS** — her kiracı tablosunda `ENABLE` + `FORCE` ve tek politika:
   `tenant_id = current_setting('app.tenant_id')`. Ayar yoksa politika
   hiçbir satırı geçirmez (fail-closed).
"""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

APP_ROLE = "talimatname_app"

TENANT_TABLES = (
    "region",
    "branch",
    "station",
    "app_user",
    "role_assignment",
    "template",
    "template_version",
    "section",
    "item",
    "plan",
    "run",
    "answer",
    "action",
)


def _uuid_pk() -> sa.Column[Any]:
    return sa.Column("id", sa.Uuid(), primary_key=True)


def _tenant_fk() -> sa.Column[Any]:
    return sa.Column(
        "tenant_id",
        sa.Uuid(),
        sa.ForeignKey("tenant.id", ondelete="CASCADE"),
        nullable=False,
    )


def upgrade() -> None:
    # --- 1. uygulama rolü ------------------------------------------------
    op.execute(
        f"""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{APP_ROLE}') THEN
                CREATE ROLE "{APP_ROLE}" NOLOGIN NOBYPASSRLS;
            END IF;
            -- Sahip rolü uygulama rolüne üye olmalı: SET ROLE bunu ister.
            EXECUTE format('GRANT %I TO %I', '{APP_ROLE}', current_user);
        END
        $$;
        """
    )

    # --- 2. tablolar -----------------------------------------------------
    op.create_table(
        "tenant",
        _uuid_pk(),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("default_timezone", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "region",
        _uuid_pk(),
        _tenant_fk(),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("code", sa.String(16)),
    )
    op.create_table(
        "branch",
        _uuid_pk(),
        _tenant_fk(),
        sa.Column("region_id", sa.Uuid(), sa.ForeignKey("region.id", ondelete="SET NULL")),
        sa.Column("code", sa.String(16), nullable=False),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("timezone", sa.String(64), nullable=False),
        sa.Column("address", sa.String(200)),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("business_hours", JSONB, nullable=False),
        sa.UniqueConstraint("tenant_id", "code", name="uq_branch_tenant_code"),
    )
    op.create_table(
        "station",
        _uuid_pk(),
        _tenant_fk(),
        sa.Column(
            "branch_id", sa.Uuid(), sa.ForeignKey("branch.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("name", sa.String(40), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
    )
    op.create_table(
        "app_user",
        _uuid_pk(),
        _tenant_fk(),
        sa.Column("full_name", sa.String(80), nullable=False),
        sa.Column("phone", sa.String(20)),
        sa.Column("email", sa.String(160)),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("language", sa.String(8), nullable=False),
        sa.Column("pin_set", sa.Boolean(), nullable=False),
        sa.Column("invited_at", sa.DateTime(timezone=True)),
        sa.Column("masked_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("tenant_id", "phone", name="uq_user_tenant_phone"),
    )
    op.create_table(
        "role_assignment",
        _uuid_pk(),
        _tenant_fk(),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("app_user.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("role", sa.String(24), nullable=False),
        sa.Column("scope_type", sa.String(12), nullable=False),
        sa.Column("scope_id", sa.Uuid()),
    )
    op.create_table(
        "template",
        _uuid_pk(),
        _tenant_fk(),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("category", sa.String(40)),
    )
    op.create_table(
        "template_version",
        _uuid_pk(),
        _tenant_fk(),
        sa.Column(
            "template_id",
            sa.Uuid(),
            sa.ForeignKey("template.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version_no", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("camera_only", sa.Boolean(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("template_id", "version_no", name="uq_version_template_no"),
    )
    op.create_table(
        "section",
        _uuid_pk(),
        _tenant_fk(),
        sa.Column(
            "version_id",
            sa.Uuid(),
            sa.ForeignKey("template_version.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(80), nullable=False),
    )
    op.create_table(
        "item",
        _uuid_pk(),
        _tenant_fk(),
        sa.Column(
            "section_id", sa.Uuid(), sa.ForeignKey("section.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("type", sa.String(16), nullable=False),
        sa.Column("title", sa.String(160), nullable=False),
        sa.Column("hint", sa.Text()),
        sa.Column("required", sa.Boolean(), nullable=False),
        sa.Column("photo_required", sa.Boolean(), nullable=False),
        sa.Column("critical", sa.Boolean(), nullable=False),
        sa.Column("options", JSONB, nullable=False),
        sa.Column("min_value", sa.Float()),
        sa.Column("max_value", sa.Float()),
        sa.Column("unit", sa.String(16)),
    )
    op.create_table(
        "plan",
        _uuid_pk(),
        _tenant_fk(),
        sa.Column("version_id", sa.Uuid(), sa.ForeignKey("template_version.id"), nullable=False),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("branch_ids", JSONB, nullable=False),
        sa.Column("recurrence", sa.String(200), nullable=False),
        sa.Column("starts_on", sa.Date(), nullable=False),
        sa.Column("start_time", sa.String(8)),
        sa.Column("anchor_reference", sa.String(8)),
        sa.Column("anchor_offset_minutes", sa.Integer(), nullable=False),
        sa.Column("duration_minutes", sa.Integer(), nullable=False),
        sa.Column("tolerance_minutes", sa.Integer(), nullable=False),
        sa.Column("assignment_kind", sa.String(12), nullable=False),
        sa.Column("assignment_role", sa.String(24)),
        sa.Column("assignment_user_id", sa.Uuid()),
    )
    op.create_table(
        "run",
        _uuid_pk(),
        _tenant_fk(),
        sa.Column(
            "plan_id", sa.Uuid(), sa.ForeignKey("plan.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("version_id", sa.Uuid(), sa.ForeignKey("template_version.id"), nullable=False),
        sa.Column(
            "branch_id", sa.Uuid(), sa.ForeignKey("branch.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("business_day", sa.Date(), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("tolerance_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("result", sa.String(10)),
        sa.Column("score_percent", sa.Integer()),
        sa.Column("submitted_at", sa.DateTime(timezone=True)),
        sa.Column("locked_by", sa.Uuid()),
        sa.Column("lock_renewed_at", sa.DateTime(timezone=True)),
        sa.Column("cancel_reason", sa.String(200)),
    )
    op.create_index("ix_run_day", "run", ["tenant_id", "business_day"])
    op.create_index("ix_run_plan_branch", "run", ["plan_id", "branch_id"])
    op.create_table(
        "answer",
        _uuid_pk(),
        _tenant_fk(),
        sa.Column("run_id", sa.Uuid(), sa.ForeignKey("run.id", ondelete="CASCADE"), nullable=False),
        sa.Column("item_id", sa.Uuid(), sa.ForeignKey("item.id"), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("value", JSONB),
        sa.Column("note", sa.Text()),
        sa.Column("user_id", sa.Uuid()),
        sa.Column("device_id", sa.Uuid()),
        sa.Column("answered_at", sa.DateTime(timezone=True)),
        sa.Column("device_reported_at", sa.DateTime(timezone=True)),
        sa.Column("clock_skew_minutes", sa.Integer()),
        sa.Column("evidence_count", sa.Integer(), nullable=False),
    )
    op.create_index("ix_answer_run", "answer", ["run_id"])
    op.create_table(
        "action",
        _uuid_pk(),
        _tenant_fk(),
        sa.Column(
            "branch_id", sa.Uuid(), sa.ForeignKey("branch.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("title", sa.String(160), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("source_id", sa.Uuid()),
        sa.Column("priority", sa.String(10), nullable=False),
        sa.Column("status", sa.String(10), nullable=False),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("assignee_user_id", sa.Uuid()),
        sa.Column("closed_at", sa.DateTime(timezone=True)),
        sa.Column("closed_by", sa.Uuid()),
        sa.Column("close_note", sa.Text()),
    )
    op.create_index("ix_action_open", "action", ["tenant_id", "status", "due_at"])

    # --- 3. yetkiler ve RLS ---------------------------------------------
    op.execute(f'GRANT USAGE ON SCHEMA public TO "{APP_ROLE}"')
    op.execute(f'GRANT SELECT ON tenant TO "{APP_ROLE}"')
    for tablo in TENANT_TABLES:
        op.execute(f'GRANT SELECT, INSERT, UPDATE, DELETE ON {tablo} TO "{APP_ROLE}"')
        op.execute(f"ALTER TABLE {tablo} ENABLE ROW LEVEL SECURITY")
        # FORCE: sahip rolü de politikaya tabi olsun (yanlışlıkla sahip
        # bağlantısıyla çalışıldığında sessizce her şeyi görmeyelim).
        op.execute(f"ALTER TABLE {tablo} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY kiraci_yalitimi ON {tablo}
            USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
            WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
            """
        )


def downgrade() -> None:
    for tablo in reversed(TENANT_TABLES):
        op.execute(f"DROP POLICY IF EXISTS kiraci_yalitimi ON {tablo}")
    op.drop_index("ix_action_open", table_name="action")
    op.drop_table("action")
    op.drop_index("ix_answer_run", table_name="answer")
    op.drop_table("answer")
    op.drop_index("ix_run_plan_branch", table_name="run")
    op.drop_index("ix_run_day", table_name="run")
    op.drop_table("run")
    op.drop_table("plan")
    op.drop_table("item")
    op.drop_table("section")
    op.drop_table("template_version")
    op.drop_table("template")
    op.drop_table("role_assignment")
    op.drop_table("app_user")
    op.drop_table("station")
    op.drop_table("branch")
    op.drop_table("region")
    op.drop_table("tenant")
    # Rol silinmeden önce yetkileri geri alınmalı: PostgreSQL, üzerinde
    # yetki kalan rolü düşürmez ("privileges for schema public").
    op.execute(
        f"""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{APP_ROLE}') THEN
                EXECUTE 'DROP OWNED BY "{APP_ROLE}"';
                EXECUTE format('REVOKE %I FROM %I', '{APP_ROLE}', current_user);
                EXECUTE 'DROP ROLE "{APP_ROLE}"';
            END IF;
        END
        $$;
        """
    )
