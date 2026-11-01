"""Arka planda üretilen çıktı işleri (ST-102; FR-1217).

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-01

İş kaydı **tabloda** duruyor, süreç içi bir kuyrukta değil: zamanlayıcı
ya da API yeniden başladığında kullanıcının beklediği rapor kaybolmasın
ve "neden gelmedi" sorusunun cevabı kayıtta olsun.

İki indeks var ve ikisi de bir sorguyu karşılıyor: kişinin kendi
listesi (panel) ve sıradaki işler (işçi her turda soruyor).

Kapsam **yazılmıyor**: işte yalnızca isteyenin kimliği var, hangi
şubeleri göreceği üretim anında rolünden okunuyor. Kapsamı donduran
bir kayıt, rolü daralmış birinin eski kapsamıyla rapor almasına yol
açardı.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None

APP_ROLE = "talimatname_app"
TABLO = "export_job"


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
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("params", JSONB, nullable=False, server_default="{}"),
        sa.Column("requested_by", sa.Uuid(), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("run_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("state", sa.String(10), nullable=False, server_default="queued"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("object_key", sa.String(200)),
        sa.Column("size_bytes", sa.Integer()),
        sa.Column("document_code", sa.String(20)),
        sa.Column("error_code", sa.String(60)),
    )
    op.create_index("ix_cikti_kisi", TABLO, ["tenant_id", "requested_by", "requested_at"])
    op.create_index("ix_cikti_durum", TABLO, ["tenant_id", "state", "requested_at"])

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
    op.drop_index("ix_cikti_durum", table_name=TABLO)
    op.drop_index("ix_cikti_kisi", table_name=TABLO)
    op.drop_table(TABLO)
