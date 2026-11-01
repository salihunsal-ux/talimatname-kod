"""Belge kodu aramasi icin indeks (ST-101; FR-1218).

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-01

Doğrulama sayfası elindeki kâğıttaki kodla kaydı buluyor; kod, olay
özetinin ilk 12 basamağı. Aramanın `substr(hash, 1, 12) = :onek`
ifadesiyle yapılması ve indeksin **aynı ifadede** olması bilinçli:

* `hash LIKE :onek || '%'` parametreli hâlde planlayıcıda indeksi
  her zaman kullanmıyor; ifade üstündeki eşitlik kullanıyor.
* Uç nokta oturum **istemiyor** (denetçi panele giremez). İndekssiz
  bir tam tarama, dışarıdan tetiklenebilen bir yük kapısı olurdu.

Kiracı önde: politika zaten kiracıyı süzüyor, indeks de aynı sırayla
başlamalı ki tek kiracının satırlarına inilsin.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

TABLO = "audit_event"


def upgrade() -> None:
    op.create_index(
        "ix_audit_kod",
        TABLO,
        [sa.text("tenant_id"), sa.text("substr(hash, 1, 12)")],
    )


def downgrade() -> None:
    op.drop_index("ix_audit_kod", table_name=TABLO)
