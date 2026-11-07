"""İş gününün bugünü (bağımsız test turu B11'in sunucu tarafı).

`datetime.now(UTC).date()` gece yarısı ile 03:00 arasında bir önceki
günü veriyordu — kapanış vardiyası tam o saatlerde çalışıyor.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

from talimatname.api.is_gunu import VARSAYILAN_DILIM, bugun
from talimatname.domain.setup import AccountSettings


class _SahteKurulum:
    """`SetupService.settings()` kadarını taklit eder."""

    def __init__(self, dilim: str | None) -> None:
        self._dilim = dilim

    def settings(self) -> AccountSettings | None:
        if self._dilim is None:
            return None
        return AccountSettings(brand_name="Demo", timezone=self._dilim)


def _an(iso: str) -> datetime:
    return datetime.fromisoformat(iso)


def test_gece_yarisindan_sonra_gun_bir_geriye_dusmuyor() -> None:
    # İstanbul'da 8 Kasım 00:30 → UTC'de 7 Kasım 21:30.
    with patch("talimatname.api.is_gunu.datetime") as sahte:
        sahte.now.side_effect = lambda tz: _an("2026-11-07T21:30:00+00:00").astimezone(tz)
        gun = bugun(_SahteKurulum("Europe/Istanbul"))  # type: ignore[arg-type]

    assert gun.isoformat() == "2026-11-08"
    assert _an("2026-11-07T21:30:00+00:00").astimezone(UTC).date().isoformat() == "2026-11-07"


def test_ayar_yoksa_varsayilan_dilim() -> None:
    gun = bugun(_SahteKurulum(None))  # type: ignore[arg-type]

    assert gun == datetime.now(ZoneInfo(VARSAYILAN_DILIM)).date()


def test_bozuk_dilim_gun_hesabini_dusurmuyor() -> None:
    """Ayar bozuksa UTC'ye düşmek yerine varsayılan dilim: daha az yanlış."""
    gun = bugun(_SahteKurulum("Mars/Olympus"))  # type: ignore[arg-type]

    assert gun == datetime.now(ZoneInfo(VARSAYILAN_DILIM)).date()
