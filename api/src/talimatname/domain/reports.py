"""Rapor alanı (CAP-12; FR-1207, FR-1220; UC-15, UC-16).

İki rapor burada ve ikisinin de ortak derdi aynı: **sayılar bir yerden
gelmeli ve o yer tek olmalı.** Pano "kaçırıldı"yı zamandan türetiyor
(`Run.state_at`); aylık özet de aynı fonksiyonu kullanıyor, kendi
tanımını yazmıyor. İki ayrı "geç" tanımı, iki ayrı gerçek demek.

* **Aylık özet** (FR-1220): bir ayın zamanında / geç / kaçırıldı /
  yapılmayacak dağılımı, başarısız çalıştırma ve yapılamadı sayısı,
  şube kırılımı. Denetim konuşmasının açılış sayfası.
* **Ölçüm günlüğü** (FR-1207): sıcaklık ve sayı maddelerinin zaman
  serisi, aralık dışı olanlar işaretli. Gıda güvenliği denetiminde
  istenen şey tam olarak bu.

Saf: depo bilmez, saat okumaz. "Şimdi" dışarıdan verilir — çünkü
"kaçırıldı mı" sorusunun cevabı ne zaman sorduğuna bağlı.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal
from uuid import UUID

from talimatname.domain.answers import Answer
from talimatname.domain.plans import Run
from talimatname.domain.templates import Item

#: Ölçüm günlüğüne giren madde türleri (FR-1207).
MEASURED_TYPES: frozenset[str] = frozenset({"temperature", "number"})

RunOutcome = Literal["on_time", "late", "missed", "cancelled", "open"]


def outcome(run: Run, now: datetime) -> RunOutcome:
    """Çalıştırmanın rapordaki karşılığı — tek tanım.

    `Run.state_at` panonun da kullandığı türetme; rapor kendi tanımını
    yazmıyor ki iki ekran aynı güne farklı cevap vermesin.
    """
    durum, gec = run.state_at(now)
    if durum == "submitted":
        return "late" if gec else "on_time"
    if durum == "missed":
        return "missed"
    if durum == "cancelled":
        return "cancelled"
    return "open"


@dataclass(frozen=True, slots=True)
class Counters:
    """Bir kümenin (hesap ya da şube) sayıları."""

    total: int = 0
    on_time: int = 0
    late: int = 0
    missed: int = 0
    cancelled: int = 0
    open: int = 0
    failed: int = 0
    not_done_items: int = 0

    @property
    def closed(self) -> int:
        """Sonucu belli olanlar: açık pencereler yüzdeyi bozmamalı."""
        return self.on_time + self.late + self.missed

    @property
    def on_time_percent(self) -> int | None:
        """Zamanında tamamlanma yüzdesi. Kapanmış çalıştırma yoksa **None**.

        Sıfır göstermek "hiçbiri zamanında değil" demek olurdu; oysa
        henüz ölçecek bir şey yok.
        """
        if self.closed == 0:
            return None
        return round(self.on_time / self.closed * 100)

    def plus(self, sonuc: RunOutcome, *, failed: bool, not_done: int) -> Counters:
        return Counters(
            total=self.total + 1,
            on_time=self.on_time + (sonuc == "on_time"),
            late=self.late + (sonuc == "late"),
            missed=self.missed + (sonuc == "missed"),
            cancelled=self.cancelled + (sonuc == "cancelled"),
            open=self.open + (sonuc == "open"),
            failed=self.failed + failed,
            not_done_items=self.not_done_items + not_done,
        )


@dataclass(frozen=True, slots=True)
class BranchSummary:
    branch_id: UUID
    branch_code: str
    branch_name: str
    counters: Counters


@dataclass(frozen=True, slots=True)
class MonthlySummary:
    """FR-1220'nin tek sayfası: ay, toplam ve şube kırılımı."""

    year: int
    month: int
    first_day: date
    last_day: date
    counters: Counters
    branches: tuple[BranchSummary, ...]

    @property
    def worst_branches(self) -> tuple[BranchSummary, ...]:
        """Zamanındalığı en düşük şubeler önce; ölçülemeyenler sonda.

        Denetim konuşması "hangi şube" sorusuyla başlıyor; sıralamayı
        rapora koymak, o soruyu ekranda cevaplamak demek.
        """
        olculen = [b for b in self.branches if b.counters.on_time_percent is not None]
        olculemeyen = [b for b in self.branches if b.counters.on_time_percent is None]
        return (
            *sorted(olculen, key=lambda b: (b.counters.on_time_percent or 0, b.branch_code)),
            *sorted(olculemeyen, key=lambda b: b.branch_code),
        )


@dataclass(frozen=True, slots=True)
class Measurement:
    """Tek ölçüm: ne, nerede, ne zaman, kaç — ve aralıkta mı (FR-1207)."""

    run_id: UUID
    branch_id: UUID
    item_id: UUID
    item_title: str
    measured_at: datetime | None
    value: float
    unit: str | None
    min_value: float | None
    max_value: float | None

    @property
    def out_of_range(self) -> bool:
        if self.min_value is not None and self.value < self.min_value:
            return True
        return self.max_value is not None and self.value > self.max_value


def measurement(answer: Answer, item: Item, run: Run) -> Measurement | None:
    """Cevabı ölçüme çevirir; ölçüm değilse ya da sayı değilse `None`.

    Sayıya çevrilemeyen değeri **atlıyoruz**: ölçüm günlüğü denetime
    gidiyor, içinde "bilinmiyor" satırı olmamalı.
    """
    if item.type not in MEASURED_TYPES:
        return None
    try:
        sayi = float(answer.value)
    except (TypeError, ValueError):
        return None
    return Measurement(
        run_id=run.id,
        branch_id=run.branch_id,
        item_id=item.id,
        item_title=item.title,
        measured_at=answer.answered_at,
        value=sayi,
        unit=item.unit,
        min_value=item.min_value,
        max_value=item.max_value,
    )
