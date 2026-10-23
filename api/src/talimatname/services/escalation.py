"""Eskalasyon merdiveni (ST-066; FR-0911…0915, FR-1008, BR-11).

v1'de merdiven **sabittir**, editörü yok (v1.1). Üç tetik var:

* **Kaçırılan liste** → şube müdürüne anında. Bölge müdürü ve yönetici
  bunu sabah özetinde görür (BR-27): gece yarısı herkesi uyandırmak
  sorunu çözmüyor, sabah bakılacak bir liste çözüyor.
* **Kritik madde başarısız** → şube ve bölge müdürüne anında; **10 dk
  içinde teslim/okunma yoksa SMS** (FR-1008). Sessiz saatten muaf.
* **Gecikmiş aksiyon** → yalnızca sabah özetinde (ST-143).

İki kural kolay atlanır, ikisi de burada:

* **Merdiven durur** (FR-0914): çalıştırma "yapılmayacak" işaretlenince
  ya da aksiyon kapanınca, henüz gönderilmemiş adımlar bastırılır.
  Kapanmış bir işin ardından gelen bildirim güveni aşındırır.
* **Alıcı yoksa bir üst adıma** (FR-0915): şubenin etkin müdürü yoksa
  bildirim bölge müdürüne gider ve "alıcı yok" günlüğe yazılır. Sessizce
  düşürmek, eskalasyonun hiç olmamasıyla aynı şey.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from uuid import UUID

import structlog

from talimatname.domain.actions import Action
from talimatname.domain.notifications import Notification
from talimatname.domain.organization import Branch
from talimatname.domain.users import User
from talimatname.services.actions import ActionRepository
from talimatname.services.notifications import NotificationService
from talimatname.services.organization import OrganizationRepository
from talimatname.services.plans import PlanRepository
from talimatname.services.users import UserRepository

log = structlog.get_logger(__name__)

#: Kritik bildirimin teslim edilmesi için tanınan süre; sonrasında SMS.
SMS_AFTER = timedelta(minutes=10)

#: Ne kadar geriye bakılır. Zamanlayıcı durmuş olabilir ama üç gün önceki
#: kaçırmayı bugün bildirmek kimseye yaramaz; o kayıt sabah özetinde.
LOOKBACK = timedelta(hours=24)


class EscalationService:
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

    def run(self, now: datetime | None = None) -> dict[str, int]:
        an = now or self._now()
        return {
            "missed": self._kacirilan_listeler(an),
            "critical": self._kritik_maddeler(an),
            "sms": self._teslim_edilmeyen_kritikler(an),
            "stopped": self._merdiveni_durdur(an),
        }

    # --- tetikler -----------------------------------------------------

    def _kacirilan_listeler(self, an: datetime) -> int:
        """Kaçırılan liste → şube müdürüne anında (BR-11)."""
        subeler = {s.id: s for s in self._org.branches()}
        planlar = {p.id: p.name for p in self._plans.plans()}
        sayac = 0
        for run in self._plans.runs():
            if run.status != "missed" or run.tolerance_end < an - LOOKBACK:
                continue
            sube = subeler.get(run.branch_id)
            if sube is None:
                continue
            ad = planlar.get(run.plan_id, "Liste")
            sayac += self._gonder(
                alicilar=self._sube_adimi(sube, run.id),
                kind="run_missed",
                subject_id=run.id,
                slot="kacirildi",
                title=f"{ad} yapılmadı",
                body=f"{sube.name} · {run.business_day} penceresi kapandı",
                send_at=an,
                sube=sube,
                run_id=run.id,
            )
        return sayac

    def _kritik_maddeler(self, an: datetime) -> int:
        """Kritik madde başarısız → şube **ve** bölge müdürüne anında (FR-1008)."""
        subeler = {s.id: s for s in self._org.branches()}
        sayac = 0
        for aksiyon in self._actions.actions():
            if aksiyon.source != "critical_item" or aksiyon.status != "open":
                continue
            if aksiyon.opened_at < an - LOOKBACK:
                continue
            sube = subeler.get(aksiyon.branch_id)
            if sube is None:
                continue
            # Kritik maddede iki basamak birden: şube **ve** bölge (FR-1008).
            mudurler = self._sube_mudurleri(sube)
            if not mudurler:
                log.warning(
                    "eskalasyon.alici_yok",
                    sube=sube.code,
                    konu=str(aksiyon.id),
                    eksik_adim="branch_manager",
                    ust_adim="region_manager",
                )
            alicilar = mudurler + self._bolge_mudurleri(sube, aksiyon.id)
            sayac += self._gonder(
                alicilar=alicilar,
                kind="critical_failed",
                subject_id=aksiyon.id,
                slot="kritik",
                title=aksiyon.title,
                body=f"{sube.name} · {aksiyon.description or ''}".strip(" ·"),
                send_at=an,
                sube=sube,
                action_id=aksiyon.id,
            )
        return sayac

    def _teslim_edilmeyen_kritikler(self, an: datetime) -> int:
        """10 dk içinde teslim yoksa SMS (FR-1008).

        "Teslim edilmedi" burada **gönderilemedi**yi de kapsıyor: sürücü
        bağlı değilken push zaten başarısız oluyor, kritik bildirimin
        ikinci yolu denenmeli.
        """
        acik_aksiyonlar = {a.id for a in self._actions.actions() if a.status == "open"}
        sayac = 0
        for kayit in self._bildirim.list_notifications(limit=1000):
            if not self._sms_gerekir(kayit, an, acik_aksiyonlar):
                continue
            kisi = self._users.user(kayit.user_id)
            if kisi is None or kisi.phone is None:
                continue
            sube = self._org.branch(kayit.branch_id) if kayit.branch_id else None
            self._bildirim.queue(
                kind="critical_failed",
                user=kisi,
                subject_id=kayit.action_id or kayit.id,
                slot="kritik-sms",
                channel="sms",
                title=kayit.title,
                body=kayit.body,
                send_at=an,
                timezone=sube.timezone if sube else "Europe/Istanbul",
                branch_id=kayit.branch_id,
                action_id=kayit.action_id,
            )
            sayac += 1
        return sayac

    def _merdiveni_durdur(self, an: datetime) -> int:
        """İş bitince bekleyen adımları bastırır (FR-0914)."""
        iptal_edilenler = {r.id for r in self._plans.runs() if r.status == "cancelled"}
        kapali_aksiyonlar = {a.id for a in self._actions.actions() if a.status == "closed"}
        sayac = 0
        for kayit in self._bildirim.list_notifications(status="queued", limit=1000):
            bitti = (kayit.run_id in iptal_edilenler) or (kayit.action_id in kapali_aksiyonlar)
            if bitti:
                self._bildirim.suppress(kayit.id, "is-kapandi")
                sayac += 1
        return sayac

    # --- yardımcılar ---------------------------------------------------

    def _sms_gerekir(self, kayit: Notification, an: datetime, acik: set[UUID]) -> bool:
        """Yalnızca **push** kaydı SMS tetikler; SMS kendini tetiklemez."""
        return (
            kayit.kind == "critical_failed"
            and kayit.channel == "push"
            and kayit.status in ("sent", "failed")
            and kayit.sent_at is not None
            and kayit.sent_at <= an - SMS_AFTER
            # Aksiyon kapandıysa merdiven durur (FR-0914).
            and (kayit.action_id is None or kayit.action_id in acik)
        )

    def _gonder(
        self,
        *,
        alicilar: list[User],
        kind: str,
        subject_id: UUID,
        slot: str,
        title: str,
        body: str,
        send_at: datetime,
        sube: Branch,
        run_id: UUID | None = None,
        action_id: UUID | None = None,
    ) -> int:
        for kisi in alicilar:
            self._bildirim.queue(
                kind=kind,  # type: ignore[arg-type]
                user=kisi,
                subject_id=subject_id,
                slot=slot,
                title=title,
                body=body,
                send_at=send_at,
                timezone=sube.timezone,
                branch_id=sube.id,
                run_id=run_id,
                action_id=action_id,
            )
        return len(alicilar)

    def _sube_adimi(self, sube: Branch, konu: UUID) -> list[User]:
        """Merdivenin ilk basamağı: şube müdürü. Yoksa bir üste (FR-0915).

        Atlamayı **günlüğe yazmak** şart: alıcısı olmayan bir şube,
        eskalasyonun sessizce kaybolduğu yerdir ve ancak kayıt varsa
        fark edilir.
        """
        mudurler = self._sube_mudurleri(sube)
        if mudurler:
            return mudurler
        log.warning(
            "eskalasyon.alici_yok",
            sube=sube.code,
            konu=str(konu),
            eksik_adim="branch_manager",
            ust_adim="region_manager",
        )
        return self._bolge_mudurleri(sube, konu)

    def _sube_mudurleri(self, sube: Branch) -> list[User]:
        return [
            k
            for k in self._users.users()
            if k.status == "active"
            and any(a.role == "branch_manager" and a.scope_id == sube.id for a in k.assignments)
        ]

    def _bolge_mudurleri(self, sube: Branch, konu: UUID) -> list[User]:
        """Şubenin bölge müdürleri. Boşsa yöneticiye çıkılır (FR-0915)."""
        bolge = [
            k
            for k in self._users.users()
            if k.status == "active"
            and sube.region_id is not None
            and any(
                a.role == "region_manager" and a.scope_id == sube.region_id for a in k.assignments
            )
        ]
        if bolge:
            return bolge
        yoneticiler = [
            k for k in self._users.users() if k.status == "active" and "admin" in k.roles
        ]
        log.warning("eskalasyon.alici_yok", sube=sube.code, konu=str(konu), ust_adim="admin")
        return yoneticiler


def overdue_actions(actions: list[Action], now: datetime) -> list[Action]:
    """Vadesi geçmiş açık aksiyonlar — sabah özetinin girdisi (BR-11)."""
    return [a for a in actions if a.status == "open" and a.overdue(now)]
