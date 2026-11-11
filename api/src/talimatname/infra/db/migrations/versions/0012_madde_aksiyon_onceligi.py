"""Madde başına aksiyon işareti (BR-10; FR-0405).

Revision ID: 0012
Revises: 0011
Create Date: 2026-11-11

Kritik madde başarısız olunca aksiyon açılıyordu, kritik olmayan
olmuyordu. Araya bir boşluk düşüyordu: denetimde "ilaçlama belgesinin
süresi dolmuş" kritik değil — çalıştırmayı da başarısız yapmıyor
(BR-07) — ama takip edilmezse kayda geçip kimseye gitmiyor.

`action_priority` dolu bir madde başarısız cevaplandığında aksiyon
açılır; vade önceliğe göre sabit (kritik 4 sa, yüksek 24, normal 72).
Kritik maddede kullanılmaz: kritik kuralı zaten kendi aksiyonunu
açıyor ve ikisi birden iki kayıt doğururdu.

Sütun **nullable**: var olan maddelerin hepsi işaretsiz, yani
davranış değişmiyor. İşaret şablonu yazan kişinin kararı.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("item", sa.Column("action_priority", sa.String(8), nullable=True))


def downgrade() -> None:
    op.drop_column("item", "action_priority")
