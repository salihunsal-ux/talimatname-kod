"""Plan penceresi ve toleransı iş kuralına çekilir (FR-0504, FR-0506).

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-02

Tolerans 0–240 dk (FR-0506) ve pencere + tolerans ≤ 24 saat (FR-0504)
kuralları koda sonradan eklendi. Kod bunu bir **değişmez** olarak
uyguluyor: kuralı bozan bir plan nesnesi kurulamıyor.

Bunun sinsi tarafı şu: değişmez, yalnızca yeni kayıtları değil
**okunan** kayıtları da bağlar. Kuraldan önce yazılmış bir satır,
düzeltmeden sonra okunamaz hâle geliyor — plan listesi ve pano
tamamen düşüyor. Demo sunucusunda tam olarak bu oldu (500), çünkü
sınama için kuralı bozan iki plan açılmıştı.

Bu yüzden göç iki iş yapıyor:

1. Var olan satırları kurala çekiyor. Önce tolerans kırpılıyor
   (vazgeçilebilir olan o), yetmezse pencere. Veri kaybı sayılır
   ama alternatifi okunamayan satır.
2. Kısıtı veritabanına da koyuyor. İkinci bir doğruluk kaynağı
   oluyor — sınır değişirse göç gerekecek. Kabul ediyoruz: bu
   kuralın ihlali "sessiz kötü satır" değil, "okumayı düşüren
   satır" olduğu için yazma anında reddedilmesi daha ucuz.

Geri alma kırpılan değerleri geri getirmez; yalnızca kısıtı düşürür.
"""

from __future__ import annotations

from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None

MAX_TOLERANS = 240
MAX_PENCERE = 24 * 60
KISIT = "ck_plan_pencere_siniri"


def upgrade() -> None:
    op.execute(
        f"UPDATE plan SET duration_minutes = {MAX_PENCERE} WHERE duration_minutes > {MAX_PENCERE}"
    )
    op.execute(
        f"UPDATE plan SET tolerance_minutes = {MAX_TOLERANS} "
        f"WHERE tolerance_minutes > {MAX_TOLERANS}"
    )
    op.execute(
        f"UPDATE plan SET tolerance_minutes = GREATEST(0, {MAX_PENCERE} - duration_minutes) "
        f"WHERE duration_minutes + tolerance_minutes > {MAX_PENCERE}"
    )
    op.create_check_constraint(
        KISIT,
        "plan",
        f"tolerance_minutes BETWEEN 0 AND {MAX_TOLERANS} "
        f"AND duration_minutes > 0 "
        f"AND duration_minutes + tolerance_minutes <= {MAX_PENCERE}",
    )


def downgrade() -> None:
    op.drop_constraint(KISIT, "plan", type_="check")
