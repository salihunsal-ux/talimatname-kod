"""Oturumsuz uç noktalar için kaba hız sınırı (FR-1218).

Doğrulama sayfası oturum istemiyor: denetçi panele giremez. Oturumsuz
bir uç nokta da sınırsız olamaz — belge kodu 48 bit, tahmin edilemez
ama deneme sayısı sınırsızsa uç nokta bedava bir yük kapısı olur.

**Bu sınırın ne olmadığını yazmak önemli:** süreç içinde, bellekte
tutuluyor. Yeniden başlatmada sıfırlanır, birden fazla kopya (replica)
çalıştığında her biri kendi sayacını tutar ve `X-Forwarded-For`
başlığını değiştiren biri sayacı atlatabilir. Yani gerçek savunma ters
vekilde ya da kenar katmanındadır; buradaki sınır **en ucuz saldırıyı**
kapatıyor, hepsini değil. Redis'e taşımak için ayrı bir karar gerekir
(tek süreçlik ürün için bugün fazlalık).
"""

from __future__ import annotations

from collections import OrderedDict, deque
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from talimatname.domain.errors import DomainError, ErrorKind

#: İzlenen en çok anahtar. IP döndüren bir saldırı sözlüğü şişiremesin:
#: dolduğunda en eski dokunulan anahtar düşüyor. Sınırsız sözlük,
#: sınırın kendisini bellek tüketme aracına çevirirdi.
MAX_KEYS = 10_000


class TooManyAttempts(DomainError):
    code = "cok-fazla-deneme"
    title = "Çok fazla deneme"
    kind: ErrorKind = "too_many"


class HizSiniri:
    """Kayan pencere: anahtar başına son `period` içindeki deneme sayısı."""

    def __init__(
        self,
        *,
        limit: int,
        period: timedelta,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._limit = limit
        self._period = period
        self._now = now
        self._pencere: OrderedDict[str, deque[datetime]] = OrderedDict()

    def izin_ver(self, anahtar: str) -> bool:
        simdi = self._now()
        sinir = simdi - self._period
        damgalar = self._pencere.get(anahtar)
        if damgalar is None:
            damgalar = deque()
            self._pencere[anahtar] = damgalar
        while damgalar and damgalar[0] < sinir:
            damgalar.popleft()
        self._pencere.move_to_end(anahtar)
        self._budama()
        if len(damgalar) >= self._limit:
            return False
        damgalar.append(simdi)
        return True

    def zorunlu_kil(self, anahtar: str | None) -> None:
        """Sınırı aşan isteği reddeder. IP okunamazsa sınır **uygulanmaz**.

        IP'siz isteği engellemek, vekil yapılandırması bozulduğunda
        sayfayı herkese kapatmak olurdu; günlüğe yazılıyor ve
        görünür kalıyor.
        """
        if anahtar is None:
            return
        if not self.izin_ver(anahtar):
            raise TooManyAttempts(detail="Kısa süre içinde çok fazla deneme yapıldı")

    def sifirla(self) -> None:
        """Testler için: süreç ömrü boyunca yaşayan sayacı temizler."""
        self._pencere.clear()

    def _budama(self) -> None:
        while len(self._pencere) > MAX_KEYS:
            self._pencere.popitem(last=False)


__all__ = ["HizSiniri", "TooManyAttempts"]
