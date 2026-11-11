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

Her adım **olay günlüğüne** de yazılıyor (FR-0913). Bir ince nokta var:
tur dakikada bir koşuyor ve aynı kaçırılmış liste her turda yeniden
değerlendiriliyor. Bildirim kuyruğu idempotent olduğu için ikinci kez
bildirim çıkmıyor; günlük ise idempotent değil. Bu yüzden olay,
**yalnızca gerçekten yeni bir bildirim kuyruğa girdiğinde** yazılıyor —
yoksa hiçbir şey olmadığı hâlde zincir her dakika büyürdü.

FR-0913 ayrıca adımın aksiyonun yorum dizisine yazılmasını istiyor;
yorum dizisi v1 kapsamında yok (ADR-0008, v1.1).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

import structlog

from talimatname.domain.actions import Action, missed_run_source
from talimatname.domain.notifications import Notification
from talimatname.domain.organization import Branch
from talimatname.domain.plans import Run
from talimatname.domain.users import User
from talimatname.services.actions import ActionRepository
from talimatname.services.audit import AuditService
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


@dataclass(frozen=True, slots=True)
class _Basamak:
    """Merdivenin bir basamağı: kime gidiyor ve hangi adım atlandı.

    Atlanan adım burada taşınıyor çünkü onu **olayla birlikte** yazmak
    istiyoruz: "bildirim bölge müdürüne gitti, çünkü şubenin müdürü
    yok" tek kayıtta okunur.
    """

    alicilar: list[User]
    adim: str
    atlanan: str | None = None


class EscalationService:
    def __init__(
        self,
        plans: PlanRepository,
        org: OrganizationRepository,
        users: UserRepository,
        actions: ActionRepository,
        notifications: NotificationService,
        audit: AuditService | None = None,
        *,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._plans = plans
        self._org = org
        self._users = users
        self._actions = actions
        self._bildirim = notifications
        self._izi = audit
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
        """Kaçırılan liste → şube müdürüne anında (BR-11).

        Konu **çalıştırma değil, (şube, plan, iş günü)**: aynı gün
        birden çok pencere kaçırılırsa tek bildirim gider. Saatlik
        tuvalet turunda bu yedi push demekti ve yedisi de aynı şeyi
        söylüyordu; aksiyon listesinde çözdüğümüz gürültü bildirimde
        duruyordu — orası daha acıtıcı, çünkü listeye bakmayı seçersin,
        bildirimi seçemezsin.

        Sayı bildirimde **yazmıyor**: ilk kaçırmada gidiyor ve o anda
        sayı 1. Gün içinde kaçının kaçırıldığı aksiyon satırında
        güncelleniyor ("bugün 7 kez yapılmadı"), bildirim onu kovalamaz.

        Pencere açılış hatırlatması ayrı ve **kısılmadı**: saatlik turun
        mekanizması odur, hatırlatılmayan kontrol yapılmaz.
        """
        subeler = {s.id: s for s in self._org.branches()}
        planlar = {p.id: p.name for p in self._plans.plans()}
        gruplar: dict[tuple[UUID, UUID, object], Run] = {}
        for run in self._plans.runs():
            if run.status != "missed" or run.tolerance_end < an - LOOKBACK:
                continue
            anahtar = (run.branch_id, run.plan_id, run.business_day)
            ilk = gruplar.get(anahtar)
            if ilk is None or run.window_start < ilk.window_start:
                gruplar[anahtar] = run

        sayac = 0
        for (sube_id, plan_id, gun), run in gruplar.items():
            sube = subeler.get(sube_id)
            if sube is None:
                continue
            ad = planlar.get(plan_id, "Liste")
            sayac += self._gonder(
                basamak=self._sube_adimi(sube),
                kind="run_missed",
                subject_id=missed_run_source(sube_id, plan_id, gun),
                slot="kacirildi",
                title=f"{ad} yapılmadı",
                body=f"{sube.name} · {gun} penceresi kapandı",
                send_at=an,
                sube=sube,
                run_id=run.id,
                tetik="kacirilan-liste",
                nesne_turu="calistirma",
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
            basamak = _Basamak(
                alicilar=mudurler + self._bolge_mudurleri(sube),
                adim="branch_manager+region_manager",
                atlanan=None if mudurler else "branch_manager",
            )
            sayac += self._gonder(
                basamak=basamak,
                kind="critical_failed",
                subject_id=aksiyon.id,
                slot="kritik",
                title=aksiyon.title,
                body=f"{sube.name} · {aksiyon.description or ''}".strip(" ·"),
                send_at=an,
                sube=sube,
                action_id=aksiyon.id,
                tetik="kritik-madde",
                nesne_turu="aksiyon",
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
        basamak: _Basamak,
        kind: str,
        subject_id: UUID,
        slot: str,
        title: str,
        body: str,
        send_at: datetime,
        sube: Branch,
        tetik: str,
        nesne_turu: str,
        run_id: UUID | None = None,
        action_id: UUID | None = None,
    ) -> int:
        # Hangi alıcı için **yeni** bildirim çıkacağını önce soruyoruz:
        # olay yalnızca gerçekten bir adım yürüdüğünde yazılmalı.
        yeni = [
            k
            for k in basamak.alicilar
            if not self._bildirim.exists(
                kind=kind,  # type: ignore[arg-type]
                user_id=k.id,
                subject_id=subject_id,
                slot=slot,
            )
        ]
        for kisi in basamak.alicilar:
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
        if yeni or (basamak.atlanan and not basamak.alicilar):
            self._iz_yaz(basamak, tetik=tetik, nesne_turu=nesne_turu, konu=subject_id, sube=sube)
        return len(basamak.alicilar)

    def _iz_yaz(
        self, basamak: _Basamak, *, tetik: str, nesne_turu: str, konu: UUID, sube: Branch
    ) -> None:
        """Adımı olay günlüğüne yazar (FR-0913, FR-0915).

        Kişi **adı yazılmıyor**, sayısı yazılıyor: günlük kişisel veri
        taşımaz (BR-21) ve "kaç kişiye gitti" denetim için yeterli.
        """
        if self._izi is None:
            return
        self._izi.record(
            "aksiyon.eskalasyon",
            object_type=nesne_turu,
            object_id=konu,
            after={
                "tetik": tetik,
                "adim": basamak.adim,
                "alici": str(len(basamak.alicilar)),
                "sube": sube.code,
            },
        )
        if basamak.atlanan:
            # Alıcısı olmayan bir şube, eskalasyonun sessizce kaybolduğu
            # yerdir; ayrı tür olması aranabilir kılıyor (FR-0915).
            self._izi.record(
                "aksiyon.alici_yok",
                object_type=nesne_turu,
                object_id=konu,
                after={
                    "eksik_adim": basamak.atlanan,
                    "yurutulen_adim": basamak.adim,
                    "sube": sube.code,
                },
            )

    def _sube_adimi(self, sube: Branch) -> _Basamak:
        """Merdivenin ilk basamağı: şube müdürü. Yoksa bir üste (FR-0915).

        Atlamayı **günlüğe yazmak** şart: alıcısı olmayan bir şube,
        eskalasyonun sessizce kaybolduğu yerdir ve ancak kayıt varsa
        fark edilir. Kaydı yazan yer `_gonder`: adımın gerçekten
        yürüyüp yürümediği orada belli oluyor.
        """
        mudurler = self._sube_mudurleri(sube)
        if mudurler:
            return _Basamak(alicilar=mudurler, adim="branch_manager")
        log.warning(
            "eskalasyon.alici_yok",
            sube=sube.code,
            eksik_adim="branch_manager",
            ust_adim="region_manager",
        )
        return _Basamak(
            alicilar=self._bolge_mudurleri(sube),
            adim="region_manager",
            atlanan="branch_manager",
        )

    def _sube_mudurleri(self, sube: Branch) -> list[User]:
        return [
            k
            for k in self._users.users()
            if k.status == "active"
            and any(a.role == "branch_manager" and a.scope_id == sube.id for a in k.assignments)
        ]

    def _bolge_mudurleri(self, sube: Branch) -> list[User]:
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
        log.warning("eskalasyon.alici_yok", sube=sube.code, ust_adim="admin")
        return yoneticiler


def overdue_actions(actions: list[Action], now: datetime) -> list[Action]:
    """Vadesi geçmiş açık aksiyonlar — sabah özetinin girdisi (BR-11)."""
    return [a for a in actions if a.status == "open" and a.overdue(now)]
