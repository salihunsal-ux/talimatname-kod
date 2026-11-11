"""Plan tekrar dizgesi uzun olabilir (FR-0503).

Revision ID: 0013
Revises: 0012
Create Date: 2026-11-11

Gün içinde birden çok pencere açan planda **satır başına bir RRULE**
yazılıyor (`BYHOUR=9,14` yazmak dakikası farklı saatlerde yanlış
pencere üretirdi). Yedi pencerelik bir kural 265 karakter; sütun 200
idi ve yazma `StringDataRightTruncation` ile düşüyordu.

Sessiz bir kusurdu: plan ekranı altı pencereye izin veriyordu ama
beşin üstü zaten kaydedilemiyordu. Saatlik tuvalet şablonu (yedi
pencere) eklenirken ortaya çıktı.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("plan", "recurrence", type_=sa.Text(), existing_nullable=False)


def downgrade() -> None:
    # Kırpma riski: 200 karakteri aşan kurallar geri alınamaz.
    op.execute("UPDATE plan SET recurrence = left(recurrence, 200)")
    op.alter_column("plan", "recurrence", type_=sa.String(200), existing_nullable=False)
