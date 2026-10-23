"""Sabah özeti (ST-143; FR-1212, BR-27).

Her gün yerel 07:00: bölge müdürüne kendi bölgesi, yöneticiye tüm hesap.
İçerik **önceki iş gününden**: kaçırılan ve başarısız çalıştırmalar,
gecikmiş aksiyonlar.

İki karar:

* **Sorun yoksa da gider.** "Her şey yolunda" bir bilgidir: özet gelmezse
  kullanıcı sistemin çalışıp çalışmadığını bilemez. Sessizlik, iyi haber
  ile bozuk entegrasyon arasında ayrım yapmaz.
* **Bir kişiye günde bir özet.** Kimlik (kullanıcı, iş günü) ikilisinden
  türüyor; zamanlayıcı dakikada bir koşsa da ikinci özet üretilmez.

Özet 07:00'den **önce** kuyruğa girer ve gönderim zamanı 07:00'dir:
kuyruğa koymak gönderim değildir, zaman bildirimin kendi alanındadır.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID, uuid5
from zoneinfo import ZoneInfo

from talimatname.domain.notifications import NOTIFICATION_NAMESPACE, Channel
from talimatname.domain.organization import Branch
from talimatname.domain.users import can_access
from talimatname.services.actions import ActionRepository
from talimatname.services.escalation import overdue_actions
from talimatname.services.notifications import NotificationService
from talimatname.services.organization import OrganizationRepository
from talimatname.services.plans import PlanRepository
from talimatname.services.users import UserRepository

#: Özetin yerel gönderim saati (BR-27). Ayarlanabilir aralık v1.1.
DIGEST_AT = time(7, 0)

#: Özeti kaç dakika öncesinden kuyruğa koyarız. Zamanlayıcı turu
#: kaçarsa özet gecikmesin diye küçük bir pencere.
PREPARE_WITHIN = timedelta(minutes=30)

#: Özeti alan roller (FR-1212). Şube müdürü almaz: ona kaçırma anında gitti.
DIGEST_ROLES = ("region_manager", "admin")


@dataclass(frozen=True, slots=True)
class DigestContent:
    """Özetin gövdesi. Sayılar, cümle değil: metin dışarıda kuruluyor."""

    business_day: date
    missed: int
    failed: int
    overdue_actions: int
    branch_count: int

    @property
    def all_clear(self) -> bool:
        return self.missed == 0 and self.failed == 0 and self.overdue_actions == 0


class DigestService:
    def __init__(
        self,
        plans: PlanRepository,
        org: OrganizationRepository,
        users: UserRepository,
        actions: ActionRepository,
        notifications: NotificationService,
        *,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._plans = plans
        self._org = org
        self._users = users
        self._actions = actions
        self._bildirim = notifications
        self._now = now

    def schedule(self, now: datetime | None = None) -> int:
        """Zamanı gelen özetleri kuyruğa koyar; kuyruğa konan sayısını döner."""
        an = now or self._now()
        subeler = self._org.branches()
        sayac = 0
        for kisi in self._users.users():
            if kisi.status != "active" or not any(r in DIGEST_ROLES for r in kisi.roles):
                continue
            kapsam = [s for s in subeler if can_access(kisi, s)]
            if not kapsam:
                continue
            zaman = self._gonderim_ani(kapsam, an)
            if zaman is None:
                continue
            icerik = self.content(kapsam, zaman)
            baslik, govde = _metin(icerik)
            kanallar: tuple[Channel, ...] = ("push", "email")
            for kanal in kanallar:
                self._bildirim.queue(
                    kind="daily_digest",
                    user=kisi,
                    subject_id=_ozet_konusu(kisi.id, icerik.business_day),
                    slot=kanal,
                    channel=kanal,
                    title=baslik,
                    body=govde,
                    send_at=zaman,
                    timezone=_en_erken_dilim(kapsam),
                    deep_link="talimatname://dashboard",
                )
                sayac += 1
        return sayac

    def content(self, kapsam: list[Branch], gonderim: datetime) -> DigestContent:
        """Önceki iş gününün özeti (BR-27)."""
        dilim = ZoneInfo(_en_erken_dilim(kapsam))
        gun = (gonderim.astimezone(dilim).date()) - timedelta(days=1)
        idler = {s.id for s in kapsam}

        calistirmalar = [
            r for r in self._plans.runs() if r.branch_id in idler and r.business_day == gun
        ]
        aksiyonlar = [a for a in self._actions.actions() if a.branch_id in idler]

        return DigestContent(
            business_day=gun,
            missed=sum(1 for r in calistirmalar if r.status == "missed"),
            failed=sum(1 for r in calistirmalar if r.result == "failed"),
            overdue_actions=len(overdue_actions(aksiyonlar, gonderim)),
            branch_count=len(kapsam),
        )

    # --- iç ------------------------------------------------------------

    def _gonderim_ani(self, kapsam: list[Branch], an: datetime) -> datetime | None:
        """Bugünün 07:00'si yaklaştıysa onu, geçtiyse yarınkini döndürür.

        Geçmiş bir özeti şimdi göndermiyoruz: dünkü sabah özeti bugün
        öğlen gelirse okunmaz, güveni aşındırır.
        """
        dilim = ZoneInfo(_en_erken_dilim(kapsam))
        yerel = an.astimezone(dilim)
        hedef = yerel.replace(hour=DIGEST_AT.hour, minute=DIGEST_AT.minute, second=0, microsecond=0)
        if yerel > hedef:
            return None
        if hedef - yerel > PREPARE_WITHIN:
            return None
        return hedef.astimezone(UTC)


def _en_erken_dilim(kapsam: list[Branch]) -> str:
    """Bölge için **en erken** şubenin dilimi (BR-27).

    Bir bölge birden çok saat diliminde olabilir; özet en erken açılan
    şubeye göre gider ki ilk vardiyanın haberi geç kalmasın.
    """
    simdi = datetime.now(UTC)
    return min(
        (s.timezone for s in kapsam),
        key=lambda tz: simdi.astimezone(ZoneInfo(tz)).utcoffset() or timedelta(0),
        default="Europe/Istanbul",
    )


def _ozet_konusu(user_id: UUID, gun: date) -> UUID:
    """(kullanıcı, iş günü) → tekil konu: günde tek özet."""
    return uuid5(NOTIFICATION_NAMESPACE, f"ozet:{user_id}:{gun.isoformat()}")


def _metin(icerik: DigestContent) -> tuple[str, str]:
    if icerik.all_clear:
        return (
            "Sabah özeti: her şey yolunda",
            f"{icerik.business_day} · {icerik.branch_count} şubede kaçırılan liste, "
            "başarısız liste ve gecikmiş aksiyon yok.",
        )
    parcalar = []
    if icerik.missed:
        parcalar.append(f"{icerik.missed} kaçırılan liste")
    if icerik.failed:
        parcalar.append(f"{icerik.failed} başarısız liste")
    if icerik.overdue_actions:
        parcalar.append(f"{icerik.overdue_actions} gecikmiş aksiyon")
    return (
        f"Sabah özeti: {', '.join(parcalar)}",
        f"{icerik.business_day} · {icerik.branch_count} şube",
    )
