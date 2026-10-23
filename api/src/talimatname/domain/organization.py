"""Organizasyon: bölge, şube, istasyon (CAP-01, FR-0102…0106).

Saf katman: doğrulama kuralları burada, kalıcılık yok. Şube kodunun
benzersizliği gibi "başka satırlara bakmayı" gerektiren kurallar servis
katmanındadır; burada tek bir varlığın kendi içinde tutarlılığı vardır.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from datetime import time
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from talimatname.domain.validation import ValidationError, clean_name
from talimatname.domain.window import BranchCalendar, BusinessHours

Status = Literal["active", "inactive"]
StationKind = Literal["kitchen", "bar", "hall", "storage", "restroom", "other"]

# Şube kodu: hesap içinde benzersiz, insanlar okur ve yazar (Excel içe
# aktarmada eşleştirme anahtarı). Kısa, büyük harf, boşluksuz.
BRANCH_CODE = re.compile(r"^[A-Z0-9][A-Z0-9-]{1,15}$")

WEEKDAYS = (0, 1, 2, 3, 4, 5, 6)


def _check_timezone(value: str) -> str:
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError) as hata:
        raise ValidationError("timezone", f"Bilinmeyen saat dilimi: {value}") from hata
    return value


@dataclass(frozen=True, slots=True)
class Region:
    id: UUID
    name: str
    code: str | None = None

    def validated(self) -> Region:
        return replace(self, name=clean_name(self.name, "name"))


@dataclass(frozen=True, slots=True)
class Station:
    id: UUID
    branch_id: UUID
    name: str
    kind: StationKind = "other"

    def validated(self) -> Station:
        return replace(self, name=clean_name(self.name, "name", max_length=40))


@dataclass(frozen=True, slots=True)
class Branch:
    """Şube: planların kapsamı, çalıştırmaların sahibi.

    `business_hours` haftanın gününe göre açılış/kapanış; kapalı gün
    `None`. Pencere motoru (FR-0501…0507) bu takvimi kullanır, bu yüzden
    şube saatini doğru tutmak planlamanın ön koşuludur.
    """

    id: UUID
    code: str
    name: str
    timezone: str
    business_hours: dict[int, BusinessHours | None] = field(default_factory=dict)
    region_id: UUID | None = None
    address: str | None = None
    #: Kanıt konum bayrağının ölçüsü (FR-0615, BR-15). Tanımsızsa
    #: 'uzak' bayrağı **verilmez**: ölçüsüz şüphe işareti anlamsız.
    latitude: float | None = None
    longitude: float | None = None
    status: Status = "active"

    def validated(self) -> Branch:
        code = self.code.strip().upper()
        if not BRANCH_CODE.match(code):
            raise ValidationError(
                "code",
                "2–16 karakter, büyük harf, rakam ve tire; harf ya da rakamla başlar",
            )
        hours = {gun: self.business_hours.get(gun) for gun in WEEKDAYS}
        for gun, saat in hours.items():
            if saat is not None and saat.open_time == saat.close_time:
                raise ValidationError(
                    "business_hours",
                    f"{gun}. gün: açılış ve kapanış aynı saat olamaz",
                )
        return replace(
            self,
            code=code,
            name=clean_name(self.name, "name"),
            timezone=_check_timezone(self.timezone),
            business_hours=hours,
            address=self.address.strip() if self.address else None,
        )

    def calendar(self, closed_dates: frozenset[object] = frozenset()) -> BranchCalendar:
        """Pencere motorunun beklediği takvim görünümü."""
        return BranchCalendar(
            timezone=self.timezone,
            hours=self.business_hours,
            closed_dates=closed_dates,  # type: ignore[arg-type]
        )

    @property
    def open_days(self) -> int:
        return sum(1 for saat in self.business_hours.values() if saat is not None)


def uniform_hours(
    open_time: time, close_time: time, *, closed: tuple[int, ...] = ()
) -> dict[int, BusinessHours | None]:
    """Her gün aynı saatler; `closed` içindeki günler kapalı.

    Kurulum sihirbazının varsayılanı (FR-1401): zincirlerin çoğu tek
    saat girip tek tek düzeltiyor.
    """
    return {
        gun: (None if gun in closed else BusinessHours(open_time, close_time)) for gun in WEEKDAYS
    }
