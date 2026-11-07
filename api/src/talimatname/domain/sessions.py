"""Yenileme belirteci ve oturum kaydı (FR-0203).

Bugüne kadar oturum tek başına bir erişim belirteciydi: 30 dakika
yaşıyor, dolunca kullanıcı yeniden giriyordu. İki şey eksikti —
vardiya boyunca açık kalması gereken bir saha listesi yarım saatte bir
giriş isteyemez, ve JWT durumsuz olduğu için bir oturumu **iptal
etmenin yolu yoktu** (`docs/04-gereksinimler/08-oturum-suresi-acigi.md`).

Kurgu: kısa ömürlü erişim belirteci (imzalı, durumsuz) + uzun ömürlü
yenileme belirteci (veritabanında, iptal edilebilir).

**Sır depoda durmuyor, özeti duruyor.** Veritabanını okuyabilen biri
canlı oturumları ele geçirmesin; OTP kodunda da aynı kural var.

**Her yenileme belirteci döndürür** (rotation). Yenileme kullanıldığı
anda iptal olur ve yerine yenisi geçer. Böylece çalınmış bir belirtecin
ikinci kez kullanılması fark edilebiliyor: iptal edilmiş bir belirteç
yeniden sunulursa **o zincirin tamamı** düşürülür, çünkü iki taraftan
biri gerçek kullanıcı değil ve hangisi olduğu bilinemez.
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import Literal
from uuid import UUID

#: İstemci türüne göre ömür (FR-0203). Web kısa: tarayıcı paylaşılan bir
#: makinede açık kalabiliyor. Mobil uzun: cihaz kişiye ait ve vardiya
#: boyunca giriş istemek sahada kullanılamaz.
SessionKind = Literal["web", "mobile"]

TTL: dict[SessionKind, timedelta] = {
    "web": timedelta(hours=12),
    "mobile": timedelta(days=30),
}

#: Yenileme sırrının bayt uzunluğu. 32 bayt = 256 bit entropi.
SECRET_BYTES = 32

#: Cihaz etiketi uzunluğu. User-Agent uzun olabiliyor; kullanıcıya
#: "hangi cihaz" demeye yetecek kadarını tutuyoruz.
DEVICE_MAX = 120


def new_secret() -> str:
    """Tahmin edilemez yenileme sırrı. İstemciye **yalnızca bir kez** verilir."""
    return secrets.token_urlsafe(SECRET_BYTES)


def digest(secret: str) -> str:
    """Depoya yazılan özet. Sırrın kendisi hiçbir yerde saklanmıyor."""
    return hashlib.sha256(secret.encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class Session:
    """Bir cihazın açık oturumu."""

    id: UUID
    user_id: UUID
    token_digest: str
    kind: SessionKind
    issued_at: datetime
    expires_at: datetime
    device: str | None = None
    last_used_at: datetime | None = None
    revoked_at: datetime | None = None
    revoked_reason: str | None = None
    #: Döndürmede yerine geçen oturum. Zinciri izlemek için: çalınmış
    #: bir belirteç ikinci kez sunulunca zincirin tamamı düşürülüyor.
    replaced_by: UUID | None = None

    @property
    def revoked(self) -> bool:
        return self.revoked_at is not None

    def expired(self, now: datetime) -> bool:
        return now >= self.expires_at

    def usable(self, now: datetime) -> bool:
        return not self.revoked and not self.expired(now)

    def used(self, now: datetime, *, replaced_by: UUID) -> Session:
        """Döndürüldü: bu belirteç bir daha kabul edilmez."""
        return replace(
            self,
            last_used_at=now,
            revoked_at=now,
            revoked_reason="rotated",
            replaced_by=replaced_by,
        )

    def revoke(self, now: datetime, reason: str) -> Session:
        if self.revoked:
            return self
        return replace(self, revoked_at=now, revoked_reason=reason)


def open_session(
    *,
    id: UUID,
    user_id: UUID,
    secret: str,
    kind: SessionKind,
    now: datetime,
    device: str | None = None,
) -> Session:
    return Session(
        id=id,
        user_id=user_id,
        token_digest=digest(secret),
        kind=kind,
        issued_at=now,
        expires_at=now + TTL[kind],
        device=(device or "")[:DEVICE_MAX] or None,
    )


__all__ = [
    "DEVICE_MAX",
    "SECRET_BYTES",
    "TTL",
    "Session",
    "SessionKind",
    "digest",
    "new_secret",
    "open_session",
]
