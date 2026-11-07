"""Oturum yenileme ve iptal (ST-004; FR-0203).

Erişim belirteci kısa ömürlü ve durumsuz; yenileme belirteci uzun
ömürlü ve **iptal edilebilir**. Bu ikisini birbirine bağlayan yer
burası.

Üç kural:

1. **Döndürme.** Her yenileme eskisini iptal eder ve yenisini verir.
2. **Tekrar kullanım zinciri düşürür.** Döndürülmüş bir belirteç
   yeniden sunulursa, o zincirdeki bütün oturumlar iptal edilir:
   belirteç iki yerde, biri gerçek kullanıcı değil ve hangisi olduğu
   bilinemez. Kullanıcıyı yeniden giriş yapmaya zorlamak, saldırganın
   elinde çalışır bir oturum bırakmaktan iyidir.
3. **Yetki belirteçten değil kullanıcıdan okunur.** Pasifleştirilen
   kullanıcı yenileyemez (FR-0205).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID, uuid4

import structlog

from talimatname.domain.errors import DomainError, ErrorKind
from talimatname.domain.sessions import Session, SessionKind, digest, new_secret, open_session
from talimatname.domain.users import User

log = structlog.get_logger("sessions")


class SessionInvalid(DomainError):
    code = "oturum-gecersiz"
    title = "Oturum geçersiz ya da süresi doldu"
    kind: ErrorKind = "forbidden"


class SessionRepository(Protocol):
    def save_session(self, session: Session) -> None: ...

    def session_by_digest(self, token_digest: str) -> Session | None: ...

    def session(self, session_id: UUID) -> Session | None: ...

    def sessions_for_user(self, user_id: UUID) -> list[Session]: ...


class SessionService:
    def __init__(
        self,
        repo: SessionRepository,
        *,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._repo = repo
        self._now = now

    # --- açma --------------------------------------------------------

    def open(
        self, user: User, *, kind: SessionKind = "web", device: str | None = None
    ) -> tuple[Session, str]:
        """Yeni oturum. Dönen sır istemciye **yalnızca burada** verilir."""
        sir = new_secret()
        oturum = open_session(
            id=uuid4(),
            user_id=user.id,
            secret=sir,
            kind=kind,
            now=self._now(),
            device=device,
        )
        self._repo.save_session(oturum)
        log.info("oturum.acildi", kullanici_id=str(user.id), tur=kind)
        return oturum, sir

    # --- yenileme ----------------------------------------------------

    def rotate(self, secret: str, *, device: str | None = None) -> tuple[Session, str]:
        """Yenileme belirtecini döndürür. Dönen: (yeni oturum, yeni sır)."""
        an = self._now()
        mevcut = self._repo.session_by_digest(digest(secret))
        if mevcut is None:
            raise SessionInvalid("Yenileme belirteci tanınmadı")

        if mevcut.revoked_reason == "rotated":
            # Tekrar kullanım: belirteç iki elde. Zinciri düşür.
            dusen = self._zinciri_dusur(mevcut, an)
            log.warning(
                "oturum.tekrar_kullanim",
                kullanici_id=str(mevcut.user_id),
                dusen=dusen,
            )
            raise SessionInvalid("Bu belirteç daha önce kullanıldı; oturumlar kapatıldı")
        if not mevcut.usable(an):
            raise SessionInvalid("Oturumun süresi doldu ya da kapatıldı")

        sir = new_secret()
        yeni = open_session(
            id=uuid4(),
            user_id=mevcut.user_id,
            secret=sir,
            kind=mevcut.kind,
            now=an,
            device=device or mevcut.device,
        )
        self._repo.save_session(mevcut.used(an, replaced_by=yeni.id))
        self._repo.save_session(yeni)
        return yeni, sir

    # --- kapatma -----------------------------------------------------

    def revoke(self, secret: str, *, reason: str = "logout") -> Session | None:
        """Bu oturumu kapatır. Tanınmayan belirteç sessizce geçilir.

        Çıkış isteği hata döndürmemeli: istemci zaten belirteci atıyor
        ve "çıkamadın" demek kullanıcıya yapacak bir şey bırakmıyor.
        """
        mevcut = self._repo.session_by_digest(digest(secret))
        if mevcut is None or mevcut.revoked:
            return None
        kapali = mevcut.revoke(self._now(), reason)
        self._repo.save_session(kapali)
        return kapali

    def revoke_session(self, user_id: UUID, session_id: UUID, *, reason: str = "remote") -> Session:
        """Uzaktan sonlandırma (FR-0203): kullanıcı kendi oturumunu kapatır."""
        mevcut = self._repo.session(session_id)
        if mevcut is None or mevcut.user_id != user_id:
            raise SessionInvalid("Oturum bulunamadı")
        kapali = mevcut.revoke(self._now(), reason)
        self._repo.save_session(kapali)
        return kapali

    def revoke_all(self, user_id: UUID, *, reason: str = "logout_all") -> int:
        an = self._now()
        sayac = 0
        for oturum in self._repo.sessions_for_user(user_id):
            if oturum.revoked:
                continue
            self._repo.save_session(oturum.revoke(an, reason))
            sayac += 1
        return sayac

    # --- okuma -------------------------------------------------------

    def active(self, user_id: UUID) -> list[Session]:
        """Kullanıcının açık oturumları, yenisi önce (FR-0203 cihaz listesi)."""
        an = self._now()
        return sorted(
            (o for o in self._repo.sessions_for_user(user_id) if o.usable(an)),
            key=lambda o: o.issued_at,
            reverse=True,
        )

    # --- yardımcı ----------------------------------------------------

    def _zinciri_dusur(self, baslangic: Session, an: datetime) -> int:
        """Döndürme zincirini baştan sona iptal eder.

        Hem ileri (yerine geçenler) hem de aynı kullanıcının diğer açık
        oturumları: çalınan belirteçle yeni oturum açılmış olabilir ve
        hangisinin kime ait olduğu ayırt edilemiyor.
        """
        sayac = 0
        for oturum in self._repo.sessions_for_user(baslangic.user_id):
            if oturum.revoked:
                continue
            self._repo.save_session(oturum.revoke(an, "reuse"))
            sayac += 1
        return sayac
