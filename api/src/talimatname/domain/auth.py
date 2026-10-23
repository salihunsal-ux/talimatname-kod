"""Kimlik: OTP akışı ve sınırları (CAP-02; FR-0201, FR-0203, FR-0204).

Saf katman: kod üretmez, saat okumaz, SMS göndermez. Yalnızca **kuralı**
bilir ve kuralın tamamı TC-009'da yazılı:

* 6 haneli kod, **5 dakika** geçerli,
* **3 hatalı** denemeden sonra **15 dakika** blok,
* yeniden gönderim **60 saniye**den önce yok.

Kodun kendisi hiçbir zaman saklanmaz: yalnızca özeti tutulur. Veritabanı
sızsa bile geçerli bir kod elde edilemez.
"""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import Literal

CODE_LENGTH = 6
CODE_TTL = timedelta(minutes=5)
RESEND_AFTER = timedelta(seconds=60)
MAX_ATTEMPTS = 3
BLOCK_FOR = timedelta(minutes=15)

OtpFailure = Literal["expired", "wrong", "blocked", "unknown"]


def code_digest(phone: str, code: str) -> str:
    """Kodun özeti. Telefonla tuzlanır: aynı kod farklı numarada tutmaz."""
    return hmac.new(phone.encode(), code.encode(), hashlib.sha256).hexdigest()


@dataclass(frozen=True, slots=True)
class OtpChallenge:
    """Gönderilmiş bir doğrulama kodunun durumu."""

    phone: str
    digest: str
    created_at: datetime
    attempts: int = 0
    blocked_until: datetime | None = None

    def expired(self, now: datetime) -> bool:
        return now - self.created_at > CODE_TTL

    def blocked(self, now: datetime) -> bool:
        return self.blocked_until is not None and now < self.blocked_until

    def resend_allowed_at(self) -> datetime:
        return self.created_at + RESEND_AFTER

    def can_resend(self, now: datetime) -> bool:
        return now >= self.resend_allowed_at()

    def verify(self, code: str, now: datetime) -> tuple[OtpChallenge, OtpFailure | None]:
        """Kodu dener. Dönen: (yeni durum, hata) — hata None ise doğru."""
        if self.blocked(now):
            return self, "blocked"
        if self.expired(now):
            return self, "expired"
        if hmac.compare_digest(self.digest, code_digest(self.phone, code)):
            return self, None

        deneme = self.attempts + 1
        if deneme >= MAX_ATTEMPTS:
            return (
                replace(self, attempts=deneme, blocked_until=now + BLOCK_FOR),
                "blocked",
            )
        return replace(self, attempts=deneme), "wrong"


@dataclass(frozen=True, slots=True)
class TokenClaims:
    """Belirteç içeriği. Kapsam **belirtece yazılmaz**: roller değişince
    eski belirteç eski yetkiyi taşımasın diye kapsam her istekte
    kullanıcıdan okunur (FR-0205)."""

    user_id: str
    tenant_id: str
    issued_at: datetime
    expires_at: datetime
