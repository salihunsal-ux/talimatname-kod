"""İmzalı kısa ömürlü belirteçler: oturum ve kanıt bağlantıları.

Oturum belirteci (ST-004) ve kanıt URL'leri (FR-1305) aynı anahtarla
imzalanıyor, farklı `scope` ile ayrılıyorlar. Tek anahtar yönetmek iki
anahtar yönetmekten güvenli: üretimde döndürülmesi gereken sır sayısı
azaldıkça unutulan sır sayısı da azalır.

`scope` **zorunlu** ve doğrulamada denetleniyor: kanıt görüntüleme
bağlantısı oturum belirteci yerine geçemez, tersi de olmaz.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from functools import lru_cache
from typing import Any

import jwt
import structlog
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from talimatname.domain.errors import DomainError, ErrorKind
from talimatname.settings import Settings

log = structlog.get_logger(__name__)

ALGORITHM = "RS256"


class TokenInvalid(DomainError):
    code = "belirtec-gecersiz"
    title = "Oturum geçersiz ya da süresi doldu"
    kind: ErrorKind = "forbidden"


@lru_cache
def _gecici_anahtar() -> tuple[str, str]:
    """Geliştirme için geçici RSA çifti (süreç ömrü kadar)."""
    anahtar = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    ozel = anahtar.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    acik = (
        anahtar.public_key()
        .public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        .decode()
    )
    log.warning(
        "auth.gecici_anahtar",
        aciklama="JWT_PRIVATE_KEY tanımlı değil: geçici anahtar üretildi, "
        "sunucu yeniden başlayınca oturumlar ve kanıt bağlantıları düşer",
    )
    return ozel, acik


def anahtarlar(ayar: Settings) -> tuple[str, str]:
    """(özel, açık). Ayar yoksa geliştirme anahtarı — üretimde Settings engeller."""
    if ayar.jwt_private_key and ayar.jwt_public_key:
        return ayar.jwt_private_key, ayar.jwt_public_key
    return _gecici_anahtar()


def imzala(
    ayar: Settings,
    *,
    subject: str,
    scope: str,
    ttl: timedelta,
    now: datetime | None = None,
    **ek: Any,
) -> str:
    ozel, _ = anahtarlar(ayar)
    an = now or datetime.now(UTC)
    govde: dict[str, Any] = {
        "sub": subject,
        "scope": scope,
        "iat": int(an.timestamp()),
        "exp": int((an + ttl).timestamp()),
        **ek,
    }
    return jwt.encode(govde, ozel, algorithm=ALGORITHM)


def coz(ayar: Settings, belirtec: str, *, scope: str) -> dict[str, Any]:
    """Belirteci çözer ve **kapsamını denetler**."""
    _, acik = anahtarlar(ayar)
    try:
        govde: dict[str, Any] = jwt.decode(belirtec, acik, algorithms=[ALGORITHM])
    except jwt.PyJWTError as hata:
        raise TokenInvalid(str(hata)) from hata
    if govde.get("scope") != scope:
        raise TokenInvalid(f"Bu bağlantı {scope} için değil")
    return govde
