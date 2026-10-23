"""Sabit hatırlatmalar (ST-045; FR-0509).

İki hatırlatma, ikisi de sabit: pencere **açılışında** ve **bitişe 30 dk
kala**. Ayarlanabilir politika v1.1'de; v1'de ayar yok, çünkü zincirin
ilk sorunu "ne zaman hatırlatayım" değil, "hiç hatırlatılmıyor".

Kuyruğa koymak gönderim değildir: burası kimin ne zaman bildirim alacağına
karar verir, gönderimi `NotificationService` yapar (ST-044).

**Geçmiş hatırlatma gönderilmez.** Zamanlayıcı bir saat durmuşsa o süre
içinde açılmış pencerenin "şimdi başladı" bildirimini göndermek
kullanıcıya yalan söylemek olur. Kısa bir toparlanma payı (15 dk) var,
ötesi atlanır.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from uuid import UUID

from talimatname.domain.notifications import reminder_slots
from talimatname.domain.organization import Branch
from talimatname.domain.plans import Plan, Run
from talimatname.domain.users import User, can_access
from talimatname.services.notifications import NotificationService
from talimatname.services.organization import OrganizationRepository
from talimatname.services.plans import PlanRepository
from talimatname.services.users import UserRepository

#: Zamanlayıcı geciktiyse bu kadar geriye kadar hatırlatma yine gönderilir.
CATCH_UP = timedelta(minutes=15)

#: Ne kadar ilerisi için hatırlatma kuyruğa alınır. Ufuk 7 gün (FR-0513)
#: ama bildirim kuyruğunu 7 günlük kayıtla doldurmanın faydası yok:
#: plan değişirse kuyruk da yanlış olur.
HORIZON = timedelta(hours=36)

#: Hatırlatmayı kim alır: işi yapanlar. Yöneticiye hatırlatma gitmez;
#: ona kaçırma ve eskalasyon gider (ST-066).
WORKER_ROLES = ("staff", "branch_manager")


class ReminderService:
    def __init__(
        self,
        plans: PlanRepository,
        org: OrganizationRepository,
        users: UserRepository,
        notifications: NotificationService,
        *,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._plans = plans
        self._org = org
        self._users = users
        self._bildirim = notifications
        self._now = now

    def schedule(self, now: datetime | None = None) -> int:
        """Yaklaşan çalıştırmalar için hatırlatmaları kuyruğa koyar.

        Dönen sayı **yeni** kayıt sayısı değil, kuyruğa konan toplam
        dilimdir; kuyruk idempotent olduğundan tekrar çağrı kopya üretmez.
        """
        an = now or self._now()
        subeler = {s.id: s for s in self._org.branches()}
        planlar = {p.id: p for p in self._plans.plans()}
        sayac = 0

        for run in self._plans.runs():
            if run.status != "scheduled":
                continue
            if not (an - CATCH_UP <= run.window_end and run.window_start <= an + HORIZON):
                continue
            sube = subeler.get(run.branch_id)
            plan = planlar.get(run.plan_id)
            if sube is None or plan is None:
                continue
            sayac += self._calistirma_icin(run, plan, sube, an)
        return sayac

    # --- iç ----------------------------------------------------------

    def _calistirma_icin(self, run: Run, plan: Plan, sube: Branch, an: datetime) -> int:
        alicilar = self._alicilar(run, plan, sube)
        if not alicilar:
            return 0

        sayac = 0
        for tur, zaman, dilim in reminder_slots(run.window_start, run.window_end):
            if zaman < an - CATCH_UP:
                continue
            baslik, govde = _metin(tur, plan.name, sube.name)
            for kullanici in alicilar:
                self._bildirim.queue(
                    kind=tur,
                    user=kullanici,
                    subject_id=run.id,
                    slot=dilim,
                    title=baslik,
                    body=govde,
                    send_at=zaman,
                    timezone=sube.timezone,
                    branch_id=sube.id,
                    run_id=run.id,
                    deep_link=f"talimatname://runs/{run.id}",
                )
                sayac += 1
        return sayac

    def _alicilar(self, run: Run, plan: Plan, sube: Branch) -> list[User]:
        """Atamaya göre bildirimi kimler alır (FR-0508)."""
        atama = plan.assignment
        if atama.kind == "user":
            kisi = self._users.user(atama.user_id) if atama.user_id else None
            return [kisi] if kisi is not None and kisi.status == "active" else []

        adaylar = [
            k
            for k in self._users.users()
            if k.status == "active"
            and can_access(k, sube)
            and not _yalnizca_yonetim_kapsami(k, sube.id)
        ]
        if atama.kind == "role":
            return [k for k in adaylar if atama.role in k.roles]
        return [k for k in adaylar if any(r in WORKER_ROLES for r in k.roles)]


def _yalnizca_yonetim_kapsami(kullanici: User, branch_id: UUID) -> bool:
    """Bu şubeyi yalnızca yönetim kapsamıyla mı görüyor?

    Yönetici ve bölge müdürü her şubeyi görür ama orada **çalışmaz**:
    açılış hatırlatması onlara gitmemeli. Şubeye doğrudan atanmışsa
    (örneğin hem bölge müdürü hem bir şubenin müdürü) hatırlatma gider.
    """
    dogrudan = any(a.scope_id == branch_id for a in kullanici.assignments)
    return not dogrudan


def _metin(tur: str, plan_adi: str, sube_adi: str) -> tuple[str, str]:
    if tur == "run_opened":
        return (f"{plan_adi} başladı", f"{sube_adi} · liste şimdi açıldı")
    return (f"{plan_adi} için 30 dakika kaldı", f"{sube_adi} · pencere kapanmak üzere")
