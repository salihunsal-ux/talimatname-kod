"""Bildirim servisi: kuyruk, kanal sürücüleri ve teslimat izi (ST-044).

Kanal bağımsızlığı (FR-1007) burada bir **port**la sağlanıyor:
`ChannelDriver`. Uygulama katmanı "push gönder" demez; bildirimi kuyruğa
koyar, servis sürücüyü bulur. WhatsApp v1.x'te eklenecek olan yeni bir
sürücüdür, bu dosyada değişiklik değil.

**Sürücü yoksa ne olur?** Bildirim `failed` olur, hata kodu
`surucu-yok` yazılır ve kuyrukta iz kalır. Ürün kararı: gönderilmemiş
bir bildirimi gönderilmiş saymıyoruz. Panelde de "gönderildi" yazmıyor;
FCM/APNs (ST-046) ve SMS (ST-067) bağlanana kadar bu kayıtlar neyin
eksik olduğunun listesidir.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

import structlog

from talimatname.domain.errors import DomainError, ErrorKind
from talimatname.domain.notifications import (
    Channel,
    Notification,
    NotificationKind,
    defer_past_quiet_hours,
    notification_id,
    quiet_hours,
)
from talimatname.domain.users import User
from talimatname.services.users import UserRepository

log = structlog.get_logger(__name__)


class NotificationNotFound(DomainError):
    code = "bildirim-bulunamadi"
    title = "Bildirim bulunamadı"
    kind: ErrorKind = "not_found"


class NotificationRepository(Protocol):
    def notifications(self) -> list[Notification]: ...
    def notification(self, notification_id: UUID) -> Notification | None: ...
    def save_notification(self, notification: Notification) -> None: ...


@dataclass(frozen=True, slots=True)
class DriverResult:
    """Sürücünün dönüşü: başardı mı, başaramadıysa hangi kodla."""

    ok: bool
    code: str | None = None
    detail: str | None = None

    @classmethod
    def basarili(cls) -> DriverResult:
        return cls(True)

    @classmethod
    def hata(cls, code: str, detail: str | None = None) -> DriverResult:
        return cls(False, code, detail)


class ChannelDriver(Protocol):
    """Tek bir kanalın gönderim portu (FR-1007).

    `send` **teslim garantisi vermez**: sürücüye verildiğini bildirir.
    Teslim/okunma geri bildirimi kanalın kendi geri çağrısıyla gelir
    (FCM için ST-046) ve `mark_delivered` ile işlenir.
    """

    channel: Channel

    def send(self, notification: Notification, user: User) -> DriverResult: ...


class NotificationService:
    def __init__(
        self,
        repo: NotificationRepository,
        users: UserRepository,
        *,
        drivers: Iterable[ChannelDriver] = (),
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._repo = repo
        self._users = users
        self._drivers: dict[Channel, ChannelDriver] = {d.channel: d for d in drivers}
        self._now = now

    # --- okuma -------------------------------------------------------

    def list_notifications(
        self,
        *,
        user_id: UUID | None = None,
        status: str | None = None,
        limit: int = 200,
    ) -> list[Notification]:
        """Teslimat izi (FR-1005): en yeni önce."""
        kayitlar = [
            b
            for b in self._repo.notifications()
            if (user_id is None or b.user_id == user_id) and (status is None or b.status == status)
        ]
        kayitlar.sort(key=lambda b: b.created_at, reverse=True)
        return kayitlar[:limit]

    def get(self, notification_id_: UUID) -> Notification:
        kayit = self._repo.notification(notification_id_)
        if kayit is None:
            raise NotificationNotFound(f"id: {notification_id_}")
        return kayit

    def driver_names(self) -> list[str]:
        """Bağlı kanallar. Boş liste dürüst bir cevaptır: hiçbiri."""
        return sorted(self._drivers)

    def counts(self) -> dict[str, int]:
        kayitlar = self._repo.notifications()
        return {
            "queued": sum(1 for b in kayitlar if b.status == "queued"),
            "sent": sum(1 for b in kayitlar if b.status in ("sent", "delivered")),
            "failed": sum(1 for b in kayitlar if b.status == "failed"),
            "total": len(kayitlar),
        }

    # --- yazma -------------------------------------------------------

    def queue(
        self,
        *,
        kind: NotificationKind,
        user: User,
        subject_id: UUID,
        title: str,
        body: str,
        send_at: datetime,
        timezone: str,
        slot: str = "",
        channel: Channel = "push",
        branch_id: UUID | None = None,
        run_id: UUID | None = None,
        action_id: UUID | None = None,
        deep_link: str | None = None,
    ) -> Notification:
        """Kuyruğa koyar. **İdempotent**: aynı dilim ikinci kez kopya üretmez.

        Zamanlayıcı dakikada bir koşuyor; bu yüzden tekrar çağrı var
        olanı döndürür, yeniden göndermez.
        """
        kimlik = notification_id(kind, user.id, subject_id, slot)
        mevcut = self._repo.notification(kimlik)
        if mevcut is not None:
            return mevcut

        an = self._now()
        kayit = Notification(
            id=kimlik,
            kind=kind,
            channel=channel,
            user_id=user.id,
            title=title,
            body=body,
            send_at=send_at,
            created_at=an,
            branch_id=branch_id,
            run_id=run_id,
            action_id=action_id,
            deep_link=deep_link,
        ).validated()

        # Sessiz saat: yönetim bildirimleri sabaha ötelenir. Pencereye bağlı
        # iş hatırlatmaları ve kritik olaylar ötelenmez (FR-1004).
        if kayit.deferrable and quiet_hours(kayit.send_at, timezone):
            kayit = replace(kayit, send_at=defer_past_quiet_hours(kayit.send_at, timezone))

        self._repo.save_notification(kayit)
        return kayit

    def dispatch(self, now: datetime | None = None, limit: int = 100) -> dict[str, int]:
        """Zamanı gelmiş bildirimleri sürücülere verir.

        Dönen sayaçlar zamanlayıcı günlüğüne yazılır; `failed` sayısı
        sıfırdan büyükse bu bir uyarıdır, gürültü değil.
        """
        an = now or self._now()
        sayac = {"sent": 0, "failed": 0, "suppressed": 0}
        for kayit in sorted(self._repo.notifications(), key=lambda b: b.send_at):
            if not kayit.due(an) or sum(sayac.values()) >= limit:
                continue
            guncel = self._gonder(kayit, an)
            self._repo.save_notification(guncel)
            if guncel.status == "sent":
                sayac["sent"] += 1
            elif guncel.status == "suppressed":
                sayac["suppressed"] += 1
            else:
                sayac["failed"] += 1
        return sayac

    def mark_delivered(self, notification_id_: UUID, now: datetime | None = None) -> Notification:
        """Kanalın geri bildirimi: cihaz aldı (FR-1005)."""
        kayit = self.get(notification_id_).delivered(now or self._now())
        self._repo.save_notification(kayit)
        return kayit

    # --- iç ----------------------------------------------------------

    def _gonder(self, kayit: Notification, an: datetime) -> Notification:
        kullanici = self._users.user(kayit.user_id)
        if kullanici is None or kullanici.status != "active":
            return kayit.suppressed("alici-pasif")

        surucu = self._drivers.get(kayit.channel)
        if surucu is None:
            # Sessizce "gönderildi" demek yerine eksiği kayda geçiriyoruz.
            log.warning(
                "bildirim.surucu_yok", kanal=kayit.channel, tur=kayit.kind, id=str(kayit.id)
            )
            return kayit.failed(an, "surucu-yok", f"{kayit.channel} sürücüsü bağlı değil")

        sonuc = surucu.send(kayit, kullanici)
        if sonuc.ok:
            return kayit.sent(an)
        return kayit.failed(an, sonuc.code or "gonderim-hatasi", sonuc.detail)
