"""Yapılamadı sebebi: cevapta sebep kodu.

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-24

Senk sözleşmesi (ST-054) manifestte **yapılamadı sebep setini** veriyor
(FR-0701). Cihaz sebebi gösterip gönderecekse sunucunun onu yazacak bir
yeri olmalı; yoksa sözleşme yarım kalır: mobil sebebi sorar, sunucu
atar.

Kod saklanıyor, etiket değil (BR-09, FR-0805): "malzeme yok" yazısı
değişebilir, `no_material` değişmez — sebep dağılımı raporu dönemler
arasında karşılaştırılabilir kalsın.

Sütun boş olabilir: geçmiş cevaplar sebepsiz yazıldı ve geriye dönük
uydurma bir sebep atamak kayda yalan eklemek olurdu.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("answer", sa.Column("not_done_reason", sa.String(20)))


def downgrade() -> None:
    op.drop_column("answer", "not_done_reason")
