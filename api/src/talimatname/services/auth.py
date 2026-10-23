"""Oturum açma ve belirteç (ST-004; FR-0201…0205).

Üç şey burada birleşiyor: OTP kuralı (alan katmanı), kullanıcı deposu ve
belirteç üretimi. SMS **gönderilmiyor**: sağlayıcı bağlı değil (ST-044).
Bunu gizlemiyoruz — yanıt `delivered=False` der ve geliştirme ortamında
kodu açıkça döner ki panel ve mobil geliştirilebilsin.

Belirteç RS256 ile imzalanır (02-repo ortam değişkenleri). Anahtar
yoksa **geliştirmede** geçici bir çift üretilir ve uyarı yazılır;
üretimde ayar zorunludur (settings doğrulaması).
"""

from __future__ import annotations

import secrets
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from uuid import UUID

import jwt
import structlog
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from talimatname.domain.auth import (
    CODE_LENGTH,
    MAX_ATTEMPTS,
    OtpChallenge,
    code_digest,
)
from talimatname.domain.errors import DomainError, ErrorKind
from talimatname.domain.users import User, normalize_phone
from talimatname.services.users import UserRepository
from talimatname.settings import Settings, get_settings

log = structlog.get_logger("auth")

ALGORITHM = "RS256"


class UnknownPhone(DomainError):
    code = "kullanici-bulunamadi"
    title = "Bu numarayla kayıtlı kullanıcı yok"
    kind: ErrorKind = "not_found"


class UserInactive(DomainError):
    code = "kullanici-pasif"
    title = "Kullanıcı pasif: giriş yapamaz"
    kind: ErrorKind = "forbidden"


class ResendTooSoon(DomainError):
    code = "cok-erken-tekrar"
    title = "Yeni kod için biraz bekleyin"
    kind: ErrorKind = "conflict"


class OtpRejected(DomainError):
    code = "kod-gecersiz"
    title = "Kod doğrulanamadı"
    kind: ErrorKind = "forbidden"


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
        "sunucu yeniden başlayınca oturumlar düşer",
    )
    return ozel, acik


def _anahtarlar(ayar: Settings) -> tuple[str, str]:
    if ayar.jwt_private_key and ayar.jwt_public_key:
        return ayar.jwt_private_key, ayar.jwt_public_key
    return _gecici_anahtar()


class AuthService:
    def __init__(
        self,
        users: UserRepository,
        *,
        settings: Settings | None = None,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
        code_factory: Callable[[], str] | None = None,
    ) -> None:
        self._users = users
        self._ayar = settings or get_settings()
        self._now = now
        self._code = code_factory or (
            lambda: "".join(secrets.choice("0123456789") for _ in range(CODE_LENGTH))
        )
        #: Süreç içi: OTP kısa ömürlü ve tek sunucuda yeterli. Çoklu
        #: sunucuda Redis'e taşınacak (ST-044 ile aynı sprintte).
        self._challenges: dict[str, OtpChallenge] = {}

    # --- giriş -------------------------------------------------------

    def request_code(self, phone: str) -> tuple[str, str | None]:
        """Kod ister. Dönen: (normalize telefon, geliştirmede kodun kendisi).

        Kullanıcı yoksa **hata döner**. Numara sızdırmamak için sessiz
        kalmak düşünüldü; v1'de kullanıcıları merkez açıyor, kendi kendine
        kayıt yok — bu yüzden açık hata daha yararlı.
        """
        numara = normalize_phone(phone)
        kullanici = self._users.user_by_phone(numara)
        if kullanici is None:
            raise UnknownPhone(f"Telefon: {numara}")
        if kullanici.status != "active":
            raise UserInactive(f"Durum: {kullanici.status}")

        an = self._now()
        mevcut = self._challenges.get(numara)
        if mevcut is not None:
            if mevcut.blocked(an):
                raise OtpRejected("Çok fazla hatalı deneme; bir süre bekleyin")
            if not mevcut.can_resend(an):
                kalan = int((mevcut.resend_allowed_at() - an).total_seconds())
                raise ResendTooSoon(f"{kalan} saniye sonra yeniden deneyin")

        kod = self._code()
        self._challenges[numara] = OtpChallenge(
            phone=numara,
            digest=code_digest(numara, kod),
            created_at=an,
            blocked_until=mevcut.blocked_until if mevcut else None,
        )
        log.info("auth.kod_uretildi", telefon=numara, gonderildi=False)
        return numara, kod if self._ayar.environment == "dev" else None

    def verify_code(self, phone: str, code: str) -> tuple[User, str]:
        """Kodu doğrular ve belirteç üretir."""
        numara = normalize_phone(phone)
        an = self._now()
        mevcut = self._challenges.get(numara)
        if mevcut is None:
            raise OtpRejected("Önce kod isteyin")

        yeni, hata = mevcut.verify(code, an)
        self._challenges[numara] = yeni
        if hata is not None:
            raise OtpRejected(
                {
                    "blocked": "Çok fazla hatalı deneme; 15 dakika bekleyin",
                    "expired": "Kodun süresi doldu; yeni kod isteyin",
                    "wrong": f"Kod hatalı ({MAX_ATTEMPTS - yeni.attempts} hakkınız kaldı)",
                    "unknown": "Kod doğrulanamadı",
                }[hata]
            )

        kullanici = self._users.user_by_phone(numara)
        if kullanici is None:  # kullanıcı bu arada silinmiş olabilir
            raise UnknownPhone(f"Telefon: {numara}")
        del self._challenges[numara]
        return kullanici, self.issue_token(kullanici)

    # --- belirteç ----------------------------------------------------

    def issue_token(self, user: User) -> str:
        ozel, _ = _anahtarlar(self._ayar)
        an = self._now()
        bitis = an + timedelta(minutes=self._ayar.access_token_minutes)
        return jwt.encode(
            {
                "sub": str(user.id),
                "iat": int(an.timestamp()),
                "exp": int(bitis.timestamp()),
            },
            ozel,
            algorithm=ALGORITHM,
        )

    def user_from_token(self, token: str) -> User:
        _, acik = _anahtarlar(self._ayar)
        try:
            govde = jwt.decode(token, acik, algorithms=[ALGORITHM])
        except jwt.PyJWTError as hata:
            raise TokenInvalid(str(hata)) from hata

        kullanici = self._users.user(UUID(govde["sub"]))
        if kullanici is None:
            raise TokenInvalid("Kullanıcı bulunamadı")
        if kullanici.status != "active":
            # Pasifleştirilen kullanıcının elindeki belirteç anında geçersiz:
            # yetki belirteçten değil, kullanıcıdan okunuyor (FR-0205).
            raise UserInactive(f"Durum: {kullanici.status}")
        return kullanici
