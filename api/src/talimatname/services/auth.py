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
from uuid import UUID

import structlog

from talimatname.domain.auth import (
    CODE_LENGTH,
    MAX_ATTEMPTS,
    OtpChallenge,
    code_digest,
)
from talimatname.domain.errors import DomainError, ErrorKind
from talimatname.domain.users import User, normalize_phone
from talimatname.services.tokens import TokenInvalid, coz, imzala
from talimatname.services.users import UserRepository
from talimatname.settings import Settings, get_settings

log = structlog.get_logger("auth")

#: Oturum belirtecinin kapsamı; kanıt bağlantısı başka kapsam kullanır.
SCOPE = "session"


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
            # Detay yok: numarayı geri yazmak kullanıcıya bir şey
            # söylemiyordu, ekranda başlığın yerine geçip "Telefon:
            # +90…" diye görünüyordu (bağımsız test turu B08).
            raise UnknownPhone()
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
        # Telefon **yazılmıyor**: kişisel veri ve uygulama günlüğü,
        # denetim günlüğünden daha az korunan bir yer (BR-21).
        log.info("auth.kod_uretildi", kullanici_id=str(kullanici.id), gonderildi=False)
        # Kod yanıta yalnızca geliştirmede ya da demo modunda ekleniyor.
        # Demo modu ayrı bir ayar, çünkü ortam adını giriş davranışı için
        # zorlamak altı ay sonra "burası neden dev?" sorusunu doğuruyor;
        # ayar prod'da açılamıyor (settings.model_post_init).
        gorunur = self._ayar.environment == "dev" or self._ayar.demo_show_otp_code
        return numara, kod if gorunur else None

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
            # Detay yok: numarayı geri yazmak kullanıcıya bir şey
            # söylemiyordu, ekranda başlığın yerine geçip "Telefon:
            # +90…" diye görünüyordu (bağımsız test turu B08).
            raise UnknownPhone()
        del self._challenges[numara]
        return kullanici, self.issue_token(kullanici)

    # --- belirteç ----------------------------------------------------

    def issue_token(self, user: User) -> str:
        return imzala(
            self._ayar,
            subject=str(user.id),
            scope=SCOPE,
            ttl=timedelta(minutes=self._ayar.access_token_minutes),
            now=self._now(),
        )

    def user_id_for(self, phone: str) -> UUID | None:
        """Olay kaydı için kullanıcı kimliği; numara bilinmiyorsa None.

        Kayda telefon yazılmıyor (BR-21); kimlik yazılıyor ki "hangi
        hesap yoklandı" sorusu cevaplanabilsin.
        """
        kullanici = self._users.user_by_phone(normalize_phone(phone))
        return kullanici.id if kullanici is not None else None

    def user_from_token(self, token: str) -> User:
        govde = coz(self._ayar, token, scope=SCOPE)
        kullanici = self._users.user(UUID(govde["sub"]))
        if kullanici is None:
            raise TokenInvalid("Kullanıcı bulunamadı")
        if kullanici.status != "active":
            # Pasifleştirilen kullanıcının elindeki belirteç anında geçersiz:
            # yetki belirteçten değil, kullanıcıdan okunuyor (FR-0205).
            raise UserInactive(f"Durum: {kullanici.status}")
        return kullanici
