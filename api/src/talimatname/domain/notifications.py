"""Bildirim alanı (CAP-10; FR-0509, FR-1001…1008).

Ürünün vaadi WhatsApp'ı bırakmak değil, **hatırlatmayı sisteme
devretmek**. Bu yüzden bildirim burada birinci sınıf bir kayıttır:
kuyruğa girer, bir kanaldan gönderilmeye çalışılır ve sonucu —
başarısızlık dahil — saklanır (FR-1005).

Üç karar bu dosyada:

* **Kanal bağımsızlığı** (FR-1007). Alan katmanı "push" ya da "SMS"
  göndermez; bir bildirim üretir, kanalı seçer, gönderimi altyapıya
  bırakır. WhatsApp v1.x'te yeni bir sürücü olacak, yeni bir kavram değil.
* **Tekillik**. Zamanlayıcı dakikada bir koşuyor; aynı çalıştırmanın
  açılış hatırlatması her turda yeniden üretilmemeli. Kimlik
  (tür, alıcı, konu, dilim) beşlisinden türetiliyor — tekrar çağrı kopya
  üretmez, var olanı bulur.
* **Sessiz saatler sabit** (FR-1004, 23:00–07:00). Yöneticiye giden
  bildirim sabaha ertelenir; **kritik olan ertelenmez**. Ayarlanabilir
  politika v1.1'de.

Gönderimin kendisi burada yok: saf alan kodu I/O yapmaz, saat okumaz.
Zaman her zaman dışarıdan verilir.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, time, timedelta
from typing import Literal
from uuid import UUID, uuid5
from zoneinfo import ZoneInfo

from talimatname.domain.validation import ValidationError

Channel = Literal["push", "sms", "email"]

#: Bildirim türleri. Metin değil **tür** sözleşmedir: istemci buna göre
#: ikon seçer, derin bağlantı kurar, sessiz saat kuralını uygular.
NotificationKind = Literal[
    "run_opened",
    "reminder",
    "window_closing",
    "run_missed",
    "action_opened",
    "critical_failed",
    "daily_digest",
    "export_ready",
]

#: Teslimat durumu (FR-1005). "sent" **sürücüye verildi** demektir,
#: "delivered" cihazın aldığını onayladı demektir. İkisini ayırmak şart:
#: sürücü yokken "gönderildi" yazmak yalan olurdu.
DeliveryStatus = Literal["queued", "sent", "delivered", "failed", "suppressed"]

NOTIFICATION_NAMESPACE = UUID("8f2b5d41-6c3e-4a97-9b18-5e7d2a4c6f83")

#: Sessiz saatler (FR-1004). Sabit; kullanıcı başına ayar v1.1.
QUIET_START = time(23, 0)
QUIET_END = time(7, 0)

#: Pencere bitişine ne kadar kala ikinci hatırlatma gider (FR-0509).
REMINDER_BEFORE_CLOSE = timedelta(minutes=30)

#: Beklemeye gelmeyen türler: kritik olay anında gider.
CRITICAL_KINDS: frozenset[str] = frozenset({"critical_failed", "run_missed"})

#: Bir pencereye bağlı iş bildirimleri. Bunlar **ertelenmez**: kapanış
#: listesi zaten gece yapılan iştir, hatırlatmasını sabaha ötelemek
#: ürünün tek işini susturmak olur — pencere o saatte kapanmış olacak.
#: FR-1004'ün ertelediği şey yönetici bildirimleridir, vardiyadaki
#: kişinin hatırlatması değil.
WORK_KINDS: frozenset[str] = frozenset({"run_opened", "reminder", "window_closing"})

#: Kişinin **kendi** istediği işin bitişi (FR-1217). Erteleme, kimsenin
#: istemediği bir bildirimi uygun saate taşımak içindir; raporunu
#: bekleyen kişiyi sabaha kadar bekletmek için değil.
SELF_REQUESTED_KINDS: frozenset[str] = frozenset({"export_ready"})

#: Sessiz saat kuralının dışında kalan her şey.
QUIET_HOURS_EXEMPT: frozenset[str] = CRITICAL_KINDS | WORK_KINDS | SELF_REQUESTED_KINDS


def notification_id(kind: str, user_id: UUID, subject_id: UUID, slot: str = "") -> UUID:
    """Tekil kimlik: aynı (tür, alıcı, konu, dilim) her zaman aynı id.

    `slot` aynı konuya birden çok bildirim gerektiğinde ayırır — bir
    çalıştırmanın açılış ve "30 dk kaldı" hatırlatmaları gibi.
    """
    return uuid5(NOTIFICATION_NAMESPACE, f"{kind}:{user_id}:{subject_id}:{slot}")


def quiet_hours(an: datetime, zone: str) -> bool:
    """Yerel saatle sessiz aralıkta mı? Aralık gece yarısını aşıyor."""
    yerel = an.astimezone(ZoneInfo(zone)).time()
    return yerel >= QUIET_START or yerel < QUIET_END


def defer_past_quiet_hours(an: datetime, zone: str) -> datetime:
    """Sessiz saatteki gönderimi ertesi sabah 07:00'ye öteler.

    Dışarıdan verilen `an` UTC; dönen de UTC. Hesap yerel saatte yapılır:
    sessiz saat duvar saatidir, zincirin bulunduğu yerin saatidir.
    """
    tz = ZoneInfo(zone)
    yerel = an.astimezone(tz)
    if yerel.time() >= QUIET_START:
        hedef = (yerel + timedelta(days=1)).replace(
            hour=QUIET_END.hour, minute=QUIET_END.minute, second=0, microsecond=0
        )
    elif yerel.time() < QUIET_END:
        hedef = yerel.replace(hour=QUIET_END.hour, minute=QUIET_END.minute, second=0, microsecond=0)
    else:
        return an
    return hedef.astimezone(an.tzinfo)


@dataclass(frozen=True, slots=True)
class Notification:
    """Kuyruğa girmiş tek bir bildirim ve teslimat izi (FR-1005)."""

    id: UUID
    kind: NotificationKind
    channel: Channel
    user_id: UUID
    title: str
    body: str
    send_at: datetime
    created_at: datetime
    branch_id: UUID | None = None
    run_id: UUID | None = None
    action_id: UUID | None = None
    deep_link: str | None = None
    status: DeliveryStatus = "queued"
    attempts: int = 0
    sent_at: datetime | None = None
    delivered_at: datetime | None = None
    error_code: str | None = None
    error_detail: str | None = None

    def validated(self) -> Notification:
        if not self.title.strip():
            raise ValidationError("title", "Bildirim başlığı boş olamaz")
        return replace(self, title=self.title.strip(), body=self.body.strip())

    @property
    def critical(self) -> bool:
        return self.kind in CRITICAL_KINDS

    @property
    def deferrable(self) -> bool:
        """Sessiz saatte beklemeye alınabilir mi? (FR-1004)"""
        return self.kind not in QUIET_HOURS_EXEMPT

    def due(self, now: datetime) -> bool:
        return self.status == "queued" and self.send_at <= now

    def sent(self, now: datetime) -> Notification:
        """Sürücüye verildi. **Teslim edildi demek değil** (FR-1005)."""
        return replace(self, status="sent", attempts=self.attempts + 1, sent_at=now)

    def delivered(self, now: datetime) -> Notification:
        return replace(self, status="delivered", delivered_at=now)

    def failed(self, now: datetime, code: str, detail: str | None = None) -> Notification:
        return replace(
            self,
            status="failed",
            attempts=self.attempts + 1,
            sent_at=now,
            error_code=code,
            error_detail=detail,
        )

    def suppressed(self, code: str) -> Notification:
        """Gönderilmedi ve gönderilmeyecek: alıcının kanalı yok gibi."""
        return replace(self, status="suppressed", error_code=code)


def reminder_slots(
    window_start: datetime,
    window_end: datetime,
) -> list[tuple[NotificationKind, datetime, str]]:
    """İki sabit hatırlatma (FR-0509): açılış ve bitişe 30 dk kala.

    Pencere 30 dakikadan kısaysa ikinci hatırlatma açılışla çakışır;
    o durumda tek hatırlatma gider — aynı anda iki bildirim göndermek
    kullanıcıyı eğitmez, köreltir.
    """
    slotlar: list[tuple[NotificationKind, datetime, str]] = [("run_opened", window_start, "acilis")]
    kapanis_oncesi = window_end - REMINDER_BEFORE_CLOSE
    if kapanis_oncesi > window_start:
        slotlar.append(("window_closing", kapanis_oncesi, "kapanis-30"))
    return slotlar
