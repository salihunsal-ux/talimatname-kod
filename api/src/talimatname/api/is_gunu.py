"""İş gününün bugünü (BR-01).

`datetime.now(UTC).date()` **UTC** gün verir: İstanbul'da 8 Kasım 00:30,
UTC'de hâlâ 7 Kasım 21:30'dur. Tarih parametresi verilmeyen uç noktalar
(`GET /runs`, `GET /dashboard`) gece yarısı ile 03:00 arasında bir
önceki günü döndürüyordu — kapanış vardiyası tam o saatlerde çalışıyor
(bağımsız test turu B11'in sunucu tarafı).

Saat dilimi hesabın ayarından geliyor. Şube bazlı saat dilimi (BR-01)
v1'de tek hesap-tek dilim olarak uygulanıyor; şubeler farklı dilimlere
dağıldığında bu yardımcı şubeyi de parametre alacak.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from talimatname.services.setup import SetupService

VARSAYILAN_DILIM = "Europe/Istanbul"


def bugun(kurulum: SetupService) -> date:
    """Hesabın saat dilimine göre bugünün iş günü."""
    ayar = kurulum.settings()
    ad = ayar.timezone if ayar else VARSAYILAN_DILIM
    try:
        dilim = ZoneInfo(ad)
    except (ZoneInfoNotFoundError, ValueError):
        # Ayar bozuksa gün hesabı düşmesin; UTC'ye düşmek yerine
        # varsayılan dilim daha az yanlış.
        dilim = ZoneInfo(VARSAYILAN_DILIM)
    return datetime.now(dilim).date()


def bugun_utc() -> date:
    """Kurulum servisi olmayan yerler için UTC gün (eski davranış)."""
    return datetime.now(UTC).date()
