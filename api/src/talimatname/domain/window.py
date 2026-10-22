"""Pencere motoru: tekrar kuralı + şube saatleri → çalıştırma pencereleri.

ADR-0005 (RRULE + pencere) ve FR-0501…0507'nin saf karşılığı. Bu modül
I/O yapmaz, saate bakmaz ve hiçbir üst katmanı import etmez: girdisi
veri, çıktısı veri (ADR-0014 md.2-3). Aynı hesabı Flutter tarafı
`spec/fikstur/window.json` dosyasıyla doğrular.

Üç kural burada yaşıyor:

* **İş günü = pencere başlangıç tarihi** (BR-01). 22:00–01:30 penceresi
  gece yarısını aşsa da tek iş günündedir.
* **Kapalı günde çalıştırma üretilmez** (FR-0515): şubenin o gün
  çalışma saati yoksa ya da tarih tatil takvimindeyse pencere yok.
* **Saat dilimi şubenindir** (BR-01). Hesap yerel saatte yapılır,
  sonuç UTC döner; yaz saati geçişleri aşağıda açıkça ele alınır.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from dateutil.rrule import rrulestr

AnchorReference = Literal["open", "close"]


@dataclass(frozen=True, slots=True)
class BusinessHours:
    """Bir haftanın gününe ait açılış/kapanış saati (şube yerel saati)."""

    open_time: time
    close_time: time

    @property
    def crosses_midnight(self) -> bool:
        return self.close_time <= self.open_time


@dataclass(frozen=True, slots=True)
class BranchCalendar:
    """Şubenin saat dilimi, haftalık çalışma saatleri ve kapalı günleri."""

    timezone: str
    hours: Mapping[int, BusinessHours | None]
    closed_dates: frozenset[date] = field(default_factory=frozenset)

    def hours_for(self, day: date) -> BusinessHours | None:
        if day in self.closed_dates:
            return None
        return self.hours.get(day.weekday())

    @property
    def zone(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)


@dataclass(frozen=True, slots=True)
class Anchor:
    """Pencerenin çalışma saatinden türetilmesi: kapanıştan 60 dk önce = ("close", -60)."""

    reference: AnchorReference
    offset_minutes: int = 0


@dataclass(frozen=True, slots=True)
class WindowRule:
    """Planın zaman tarafı: tekrar, pencere başlangıcı, süre, tolerans."""

    recurrence: str
    starts_on: date
    duration_minutes: int
    start_time: time | None = None
    anchor: Anchor | None = None
    tolerance_minutes: int = 0

    def __post_init__(self) -> None:
        if (self.start_time is None) == (self.anchor is None):
            raise ValueError("start_time ya da anchor verilmeli; ikisi birlikte olmaz")
        if self.duration_minutes <= 0:
            raise ValueError("duration_minutes pozitif olmalı")
        if self.tolerance_minutes < 0:
            raise ValueError("tolerance_minutes negatif olamaz")


@dataclass(frozen=True, slots=True)
class Window:
    """Tek bir çalıştırmanın zaman kimliği. Saatler UTC, iş günü yereldir."""

    business_day: date
    window_start: datetime
    window_end: datetime
    tolerance_end: datetime

    def state_at(self, moment: datetime) -> Literal["before", "open", "tolerance", "closed"]:
        """Verilen ana göre pencerenin durumu (BR-02/BR-03'ün zaman tarafı)."""
        if moment < self.window_start:
            return "before"
        if moment < self.window_end:
            return "open"
        if moment < self.tolerance_end:
            return "tolerance"
        return "closed"


def to_utc(naive_local: datetime, zone: ZoneInfo) -> datetime:
    """Yerel saati UTC'ye çevirir; yaz saati boşluğunu ve tekrarını belirli kılar.

    * **Olmayan saat** (ileri alınan gecede 03:00): pencere boşluk kadar
      ileri kayar. Alternatif (çalıştırmayı düşürmek) kabul edilemez;
      kapanış listesi o gece de yapılır.
    * **İki kez yaşanan saat** (geri alınan gecede 02:30): ilk geçiş
      alınır (`fold=0`) — çalıştırma bir kez üretilir, iki kez değil.
    """
    aware = naive_local.replace(tzinfo=zone, fold=0)
    round_trip = aware.astimezone(UTC).astimezone(zone).replace(tzinfo=None)
    if round_trip != naive_local:
        # Saat o gece hiç yaşanmadı: boşluğun ardına taşı.
        gap = round_trip - naive_local
        aware = (naive_local + gap).replace(tzinfo=zone, fold=0)
    return aware.astimezone(UTC)


def _local_start(rule: WindowRule, day: date, hours: BusinessHours) -> datetime:
    """Pencerenin yerel başlangıç anı: sabit saat ya da çalışma saatinden türetme."""
    if rule.start_time is not None:
        return datetime.combine(day, rule.start_time)

    assert rule.anchor is not None  # WindowRule.__post_init__ garantisi
    if rule.anchor.reference == "open":
        base = datetime.combine(day, hours.open_time)
    else:
        base = datetime.combine(day, hours.close_time)
        if hours.crosses_midnight:
            # Gece 01:00'de kapanan şube: kapanış ertesi takvim günündedir.
            base += timedelta(days=1)
    return base + timedelta(minutes=rule.anchor.offset_minutes)


def _business_day(rule: WindowRule, occurrence_day: date, local_start: datetime) -> date:
    """İş gününü belirler (BR-01 ve vardiya gerçeği).

    Kural normalde **pencere başlangıç tarihidir** (BR-01): 22:00–01:30
    penceresi 22:00'nin gününe yazılır. Tek istisna, kapanışa çıpalanmış
    pencerenin gece yarısından *sonra* başlaması: 01:00'de kapanan şubede
    "kapanıştan 60 dk önce" 00:00'a düşer, ama o vardiya bir önceki günün
    vardiyasıdır ve raporu o güne yazılmalıdır.

    Bu istisna BR-01'in lafzında yok; açıkça buraya yazıldı ki iki
    istemci aynı sonucu versin. Sahada doğrulanacak açık karar.
    """
    if rule.anchor is not None and rule.anchor.reference == "close":
        return occurrence_day
    return local_start.date()


def windows(
    rule: WindowRule,
    calendar: BranchCalendar,
    first_day: date,
    last_day: date,
) -> list[Window]:
    """[first_day, last_day] aralığındaki pencereleri iş günü sırasına göre döndürür.

    Aralık **iş günü** olarak yorumlanır: 22:00–01:30 penceresi
    `last_day`'in gecesinde başlıyorsa listeye girer, ertesi sabaha
    sarkan kısmı pencerenin içindedir.

    Tekillik çağıranın işi: aynı (plan, şube, iş günü, `window_start`)
    için tek çalıştırma üretilir (FR-0513). Günde birden çok pencere
    (ör. her 2 saat) normaldir.
    """
    if last_day < first_day:
        return []

    zone = calendar.zone
    rrule_set = rrulestr(
        rule.recurrence,
        dtstart=datetime.combine(rule.starts_on, time(0, 0)),
        forceset=True,
    )
    out: list[Window] = []
    for occurrence in rrule_set.between(
        datetime.combine(first_day, time(0, 0)),
        datetime.combine(last_day, time(23, 59, 59)),
        inc=True,
    ):
        day = occurrence.date()
        hours = calendar.hours_for(day)
        if hours is None:
            continue  # kapalı gün: çalıştırma üretilmez (FR-0515)

        local_start = _local_start(rule, day, hours)
        # Süre ve tolerans **geçen zaman** olarak sayılır: pencere başlangıcı
        # UTC'ye çevrilir, uzunluklar oradan eklenir. Yerel saatte eklemek,
        # yaz saati geçişinin olduğu gece pencereyi 0 ya da 120 dakikaya
        # çevirirdi (ve ileri alınan gecede başlangıç kayarken bitiş
        # kaymadığı için negatif süre üretirdi).
        start = to_utc(local_start, zone)
        end = start + timedelta(minutes=rule.duration_minutes)
        tolerance_end = end + timedelta(minutes=rule.tolerance_minutes)
        out.append(
            Window(
                business_day=_business_day(rule, day, local_start),
                window_start=start,
                window_end=end,
                tolerance_end=tolerance_end,
            )
        )

    out.sort(key=lambda w: (w.business_day, w.window_start))
    return out
