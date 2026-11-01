"""Zamanlayıcı işleri (ST-027; FR-0513, FR-0514).

Zamanlayıcı **iki** iş yapar ve ikisi de idempotenttir:

1. **Ufuk üretimi** — etkin planların önümüzdeki 7 günlük çalıştırmaları
   (FR-0513). Aynı pencere ikinci kez üretilmez.
2. **Eskalasyon ve sabah özeti** — kaçırılan liste şube müdürüne,
   kritik madde şube ve bölge müdürüne gider (FR-0912); 07:00
   özeti bölge müdürü ve yöneticiye kuyruğa girer (BR-27).
3. **Hatırlatma ve gönderim** — yaklaşan çalıştırmalar için iki sabit
   hatırlatma kuyruğa girer (FR-0509), zamanı gelenler kanala verilir
   (FR-1001). İkisi de idempotent: aynı dilim ikinci kez üretilmez.
4. **Damgalama** — doğrulanmış kanıtlara görünür damga ve küçük
   resim (FR-0606, ST-040). Yükleme yolunda değil burada: görsel
   işleme yüklemenin yanıt süresine eklenmemeli.
5. **Kapanış** — toleransı dolmuş, hâlâ başlanmamış ya da yarım kalmış
   çalıştırmaları `missed` olarak **kalıcı** işaretler (FR-0514), ve
   kaçırılan her liste için aksiyon açar (FR-0902; idempotent).
6. **Büyük çıktılar** — eşiği geçen dönem raporları burada üretilir ve
   süresi dolan dosyalar silinir (FR-1217). İstek içinde üretmek bir web
   işçisini dakikalarca bloklardı.

İkinci iş neden gerekli? Pano "kaçırıldı"yı zaten zamandan türetiyor
(`Run.state_at`), yani ekran için yazmaya gerek yok. Ama kaçırma bir
**olaydır**: aksiyon açacak (ST-064) ve bildirim tetikleyecek (ST-066).
Olayın bir kez olması için durumun bir kez yazılması gerekir.

Mimaride zamanlayıcı ayrı bir süreçtir (01-teknik-mimari `SCH`); bu
modül onun iş mantığıdır, döngüsü `talimatname.scheduler`'da.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime

from talimatname.services.actions import ActionService
from talimatname.services.audit import RequestContext, using_context
from talimatname.services.digest import DigestService
from talimatname.services.escalation import EscalationService
from talimatname.services.evidence import EvidenceService
from talimatname.services.export_jobs import ExportJobService
from talimatname.services.notifications import NotificationService
from talimatname.services.organization import OrganizationRepository
from talimatname.services.plans import HORIZON_DAYS, PlanRepository, PlanService
from talimatname.services.reminders import ReminderService
from talimatname.services.templates import TemplateRepository


@dataclass(frozen=True, slots=True)
class TickResult:
    """Bir turun özeti — günlüğe ve `/scheduler/tick` yanıtına gider."""

    at: datetime
    created: int
    deleted: int
    missed: int
    actions_opened: int = 0
    reminders_queued: int = 0
    escalated: int = 0
    digests_queued: int = 0
    sent: int = 0
    failed: int = 0
    stamped: int = 0
    swept: int = 0
    recovered: int = 0
    exports_done: int = 0
    exports_failed: int = 0
    export_files_swept: int = 0

    @property
    def quiet(self) -> bool:
        return (
            self.created == 0
            and self.deleted == 0
            and self.missed == 0
            and self.actions_opened == 0
            and self.reminders_queued == 0
            and self.escalated == 0
            and self.digests_queued == 0
            and self.sent == 0
            and self.failed == 0
            and self.stamped == 0
            and self.swept == 0
            and self.recovered == 0
            and self.exports_done == 0
            and self.exports_failed == 0
            and self.export_files_swept == 0
        )


class SchedulerService:
    def __init__(
        self,
        plans: PlanRepository,
        org: OrganizationRepository,
        templates: TemplateRepository,
        actions: ActionService | None = None,
        reminders: ReminderService | None = None,
        notifications: NotificationService | None = None,
        escalation: EscalationService | None = None,
        digest: DigestService | None = None,
        evidence: EvidenceService | None = None,
        exports: ExportJobService | None = None,
        *,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._repo = plans
        self._plans = PlanService(plans, org, templates, now=now)
        self._actions = actions
        self._hatirlatma = reminders
        self._bildirim = notifications
        self._eskalasyon = escalation
        self._ozet = digest
        self._kanit = evidence
        self._cikti = exports
        self._now = now

    def tick(self, *, days: int = HORIZON_DAYS) -> TickResult:
        """Bir tur. Olay günlüğüne **bağlamsız** yazar (FR-1301).

        Tur işi arka plandadır: üretimde ayrı süreçte koşar, IP'si ve
        cihazı yoktur. Geliştirmede ilk istekle, panelde elle de
        tetiklenebiliyor; o isteğin IP'sini süpürülen kanıdın yanına
        yazmak "bu kullanıcı sildi" gibi okunurdu. Tur kimin
        tetiklediğinden bağımsız aynı kaydı bıraksın.
        """
        with using_context(RequestContext()):
            return self._tur(days=days)

    def _tur(self, *, days: int = HORIZON_DAYS) -> TickResult:
        an = self._now()
        eklenen, silinen = self._plans.generate_all(days=days)
        kacirilan = self.close_expired(an)
        # Kaçırma bir olaydır: aksiyonu burada açılır (FR-0902), çünkü
        # "kaçırıldı" durumunu yazan da bu turdur.
        acilan = self._actions.sync_from_runs() if self._actions else 0
        # Önce kuyruğa koy, sonra zamanı geleni gönder: aynı turda
        # kuyruğa giren bir hatırlatma aynı turda çıkabilsin.
        kuyruga = self._hatirlatma.schedule(an) if self._hatirlatma else 0
        merdiven = self._eskalasyon.run(an) if self._eskalasyon else {}
        ozet = self._ozet.schedule(an) if self._ozet else 0
        gonderim = self._bildirim.dispatch(an) if self._bildirim else {}
        # Süpürme damgadan **önce**: kurtarılan kayıt `stored` olur ve
        # aynı turda damgalanır, bir tur beklemez.
        supurme = self._kanit.sweep_pending() if self._kanit else {}
        damga = self._kanit.stamp_pending() if self._kanit else {}
        # Çıktı üretimi turun **sonunda**: dakikalar sürebilir ve
        # pencere açılışı gibi zamana bağlı işleri geciktirmemeli.
        uretilen, dusen = self._cikti.run_pending() if self._cikti else (0, 0)
        silinen_dosya = self._cikti.sweep_files() if self._cikti else 0
        return TickResult(
            at=an,
            created=eklenen,
            deleted=silinen,
            missed=kacirilan,
            actions_opened=acilan,
            reminders_queued=kuyruga,
            escalated=merdiven.get("missed", 0)
            + merdiven.get("critical", 0)
            + merdiven.get("sms", 0),
            digests_queued=ozet,
            sent=gonderim.get("sent", 0),
            failed=gonderim.get("failed", 0),
            stamped=damga.get("stamped", 0),
            swept=supurme.get("silinen", 0),
            recovered=supurme.get("kurtarilan", 0),
            exports_done=uretilen,
            exports_failed=dusen,
            export_files_swept=silinen_dosya,
        )

    def close_expired(self, now: datetime) -> int:
        """Toleransı dolmuş çalıştırmaları `missed` olarak yazar.

        Yalnızca `scheduled` ve `in_progress` olanlar kapanır: gönderilmiş
        ya da "yapılmayacak" işaretlenmiş çalıştırmaya dokunulmaz.
        """
        sayac = 0
        for run in self._repo.runs():
            if run.status not in ("scheduled", "in_progress"):
                continue
            if now < run.tolerance_end:
                continue
            self._repo.save_run(replace(run, status="missed"))
            sayac += 1
        return sayac
