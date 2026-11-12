"""Senk servisi: önbellek manifesti ve kuyruk gönderimi (ST-054).

ADR-0013'ün **üçüncü devir sözleşmesi**. Mobil geliştirici başlamadan
önce bu yüzeyin yazılı olması gerekiyordu; yoksa API panelin çevrimiçi
istek-cevap şekline oturur ve Faz B onu sökmek zorunda kalır.

İki uç nokta, iki yön:

* `manifest` — cihaz ne indirecek? Önümüzdeki 48 saatin çalıştırmaları,
  bunların şablon sürüm kimlikleri, yapılamadı sebep seti ve kuyruk
  sınırları (FR-0701). Şablon sürümü **değişmez**: cihaz id ile bir kez
  indirir, bir daha sormaz. Bu yüzden manifest sürümün içeriğini değil
  kimliğini taşır — her 15 dakikada şablon ağacını yeniden indirmek
  mobil veriyi boşa harcamak olurdu.
* `apply_batch` — cihaz ne yükleyecek? Kuyruktaki cevaplar ve kanıt
  niyetleri. **Yazma yolu ayrı değil**: cevap `ExecutionService`e,
  kanıt `EvidenceService`e iner. Senk için ikinci bir yazma yolu
  yazmak, iki yolun kurallarının zamanla ayrışması demekti.

Üç davranış sözleşme sayılır:

1. **Idempotans** (FR-0707). Cevabın ve kanıtın kimliği cihazda üretilir.
   Aynı kuyruk iki kez gönderilse de tek kayıt oluşur; yarım kalan
   yükleme kaldığı yerden devam eder.
2. **Kısmi başarı** (FR-0703). Yanıt 200 döner ve her kayıt kendi
   sonucunu taşır. Reddedilen bir kayıt kuyruğun kalanını bloke etmez.
   `retryable` alanı cihaza "bunu bir daha dene" ile "bunu bırak ve
   kullanıcıya söyle" ayrımını verir — yoksa bozuk tek kayıt sonsuz
   döngüye girer.
3. **Saat düzeltmesi** (FR-0704, BR-13). Fark senk anında ölçülür,
   çekim zamanına uygulanır, ham değer ve fark saklanır.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any, Literal
from uuid import UUID

import structlog

from talimatname.domain.errors import DomainError, ErrorKind
from talimatname.domain.evidence import MAX_BYTES, MAX_PER_ITEM
from talimatname.domain.sync import (
    MANIFEST_HORIZON_HOURS,
    MANIFEST_HORIZON_MAX_HOURS,
    MANIFEST_REFRESH_MINUTES,
    MAX_BATCH_ANSWERS,
    MAX_BATCH_EVIDENCE,
    NOT_DONE_REASON_LABELS,
    QUEUE_EVIDENCE_LIMIT,
    QUEUE_HOURS,
    clock_flagged,
    clock_offset,
    corrected_time,
    skew_minutes,
)
from talimatname.domain.validation import ValidationError
from talimatname.services.evidence import DuplicateEvidence, EvidenceService
from talimatname.services.execution import ExecutionService
from talimatname.services.organization import OrganizationRepository
from talimatname.services.plans import PlanRepository
from talimatname.services.templates import TemplateRepository

log = structlog.get_logger(__name__)

AnswerOutcome = Literal["accepted", "rejected"]
EvidenceOutcome = Literal["accepted", "resumed", "duplicate", "rejected"]


class RunOutOfScope(DomainError):
    code = "calistirma-kapsam-disi"
    title = "Bu çalıştırma kapsamınızda değil"
    kind: ErrorKind = "forbidden"


# --- okuma: manifest -------------------------------------------------


@dataclass(frozen=True, slots=True)
class ClockReading:
    """Senk anındaki saat ölçümü (FR-0704, BR-13)."""

    server_time: datetime
    device_time: datetime | None
    skew_minutes: int | None
    flagged: bool


@dataclass(frozen=True, slots=True)
class ManifestRun:
    """Cihazın çevrimdışı açacağı bir çalıştırma: kapak bilgisi."""

    run_id: UUID
    plan_id: UUID
    plan_name: str
    branch_id: UUID
    branch_code: str
    branch_name: str
    template_version_id: UUID
    business_day: date
    status: str
    window_start: datetime
    window_end: datetime
    tolerance_end: datetime
    #: Cihazın cevap yazmaya başlayabileceği an (pencere eksi hazırlık
    #: payı). Manifest penceresi açılmamış çalıştırmayı da listeler —
    #: cihaz şablonu önceden indirsin diye — ama doldurmaya o saatten
    #: önce izin yok (`pencere-acilmadi`).
    writable_from: datetime


@dataclass(frozen=True, slots=True)
class ManifestVersion:
    """Şablon sürümünün kimliği; içeriği ayrı uç noktadan bir kez iner."""

    id: UUID
    template_id: UUID
    version_no: int
    published_at: datetime | None
    item_count: int


@dataclass(frozen=True, slots=True)
class QueuePolicy:
    """Cihazın uyacağı sınırlar (FR-0604, FR-0605, FR-0706).

    Sunucu bu sayıları **söyler**, cihaz uygular. Cihaza sabit kodlanmış
    bir sınır, parametre değişince eski kurulumların yanlış davranması
    demekti; manifest her 15 dakikada tazeleniyor.
    """

    max_evidence_per_item: int = MAX_PER_ITEM
    max_evidence_bytes: int = MAX_BYTES
    queue_evidence_limit: int = QUEUE_EVIDENCE_LIMIT
    queue_hours: int = QUEUE_HOURS
    #: Tek **partide** en çok kaç kayıt. Kuyruk sınırından ayrı:
    #: `queue_evidence_limit` cihazın biriktirebileceği toplam, bunlar
    #: bir isteğe sığan. Eksiklerdi ve aşılınca sunucu **bütün isteği**
    #: 422 ile reddediyordu — modülün kendi ilkesiyle çelişen, kuyruğu
    #: sonsuza kadar tıkayan hâl (Spike A bulgusu).
    batch_answer_limit: int = MAX_BATCH_ANSWERS
    batch_evidence_limit: int = MAX_BATCH_EVIDENCE


@dataclass(frozen=True, slots=True)
class Manifest:
    """FR-0701'in karşılığı: cihazın çevrimdışı kalmadan önce indirdiği."""

    clock: ClockReading
    horizon_hours: int
    refresh_after_minutes: int
    runs: tuple[ManifestRun, ...]
    template_versions: tuple[ManifestVersion, ...]
    not_done_reasons: tuple[tuple[str, str], ...]
    policy: QueuePolicy = field(default_factory=QueuePolicy)


# --- yazma: kuyruk ---------------------------------------------------


@dataclass(frozen=True, slots=True)
class QueuedAnswer:
    """Cihaz kuyruğundaki bir cevap. `answer_id` cihazda üretildi."""

    answer_id: UUID
    run_id: UUID
    item_id: UUID
    state: str
    value: Any = None
    note: str | None = None
    not_done_reason: str | None = None
    device_id: UUID | None = None
    answered_at: datetime | None = None
    evidence_count: int = 0


@dataclass(frozen=True, slots=True)
class QueuedEvidence:
    """Cihaz kuyruğundaki bir kanıt niyeti. Baytlar ayrı istekle gider."""

    evidence_id: UUID
    run_id: UUID
    answer_id: UUID
    item_id: UUID
    sha256: str
    content_type: str
    size_bytes: int
    from_gallery: bool = False
    captured_at: datetime | None = None
    device_id: UUID | None = None
    latitude: float | None = None
    longitude: float | None = None


@dataclass(frozen=True, slots=True)
class SyncError:
    """Tek kaydın reddi. `code` sözleşme, `title` Türkçe ve değişebilir."""

    code: str
    title: str
    detail: str | None = None
    retryable: bool = False


@dataclass(frozen=True, slots=True)
class AnswerResult:
    answer_id: UUID
    outcome: AnswerOutcome
    error: SyncError | None = None


@dataclass(frozen=True, slots=True)
class EvidenceResult:
    evidence_id: UUID
    outcome: EvidenceOutcome
    upload_token: str | None = None
    error: SyncError | None = None


@dataclass(frozen=True, slots=True)
class BatchResult:
    clock: ClockReading
    answers: tuple[AnswerResult, ...]
    evidence: tuple[EvidenceResult, ...]

    @property
    def accepted(self) -> int:
        kabul = sum(1 for c in self.answers if c.outcome == "accepted")
        return kabul + sum(1 for k in self.evidence if k.outcome in ("accepted", "resumed"))

    @property
    def rejected(self) -> int:
        red = sum(1 for c in self.answers if c.outcome == "rejected")
        return red + sum(1 for k in self.evidence if k.outcome in ("rejected", "duplicate"))


#: Tekrar denemenin işe yarayabileceği tek alan hatası: kilit süresi
#: dolunca aynı kayıt geçer (FR-0521). Gerisi belirlenimlidir — "pencere
#: kapandı" ya da "madde şablonda yok" bir daha denemekle düzelmez.
RETRYABLE_CODES = frozenset({"calistirma-kilitli"})


def _hata(hata: DomainError | ValidationError) -> SyncError:
    if isinstance(hata, ValidationError):
        return SyncError(
            code="gecersiz-istek",
            title="Kayıt doğrulanamadı",
            detail=f"{hata.field_name}: {hata.message}",
        )
    return SyncError(
        code=hata.code,
        title=hata.title,
        detail=hata.detail,
        retryable=hata.code in RETRYABLE_CODES,
    )


class SyncService:
    def __init__(
        self,
        plans: PlanRepository,
        org: OrganizationRepository,
        templates: TemplateRepository,
        execution: ExecutionService,
        evidence: EvidenceService,
        *,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._plans = plans
        self._org = org
        self._templates = templates
        self._execution = execution
        self._evidence = evidence
        self._now = now

    # --- manifest ----------------------------------------------------

    def manifest(
        self,
        *,
        branch_ids: set[UUID],
        device_time: datetime | None = None,
        horizon_hours: int = MANIFEST_HORIZON_HOURS,
    ) -> Manifest:
        """Cihazın indireceği önbellek listesi (FR-0701)."""
        an = self._now()
        ufuk = max(1, min(horizon_hours, MANIFEST_HORIZON_MAX_HOURS))
        son = an + timedelta(hours=ufuk)

        planlar = {p.id: p for p in self._plans.plans()}
        subeler = {s.id: s for s in self._org.branches()}

        kosular = [
            r
            for r in self._plans.runs()
            if r.branch_id in branch_ids
            and r.status in ("scheduled", "in_progress")
            and r.tolerance_end > an
            and r.window_start <= son
        ]
        kosular.sort(key=lambda r: (r.window_start, str(r.branch_id)))

        satirlar: list[ManifestRun] = []
        for run in kosular:
            sube = subeler.get(run.branch_id)
            if sube is None:
                continue
            plan = planlar.get(run.plan_id)
            satirlar.append(
                ManifestRun(
                    run_id=run.id,
                    plan_id=run.plan_id,
                    plan_name=plan.name if plan else "Liste",
                    branch_id=run.branch_id,
                    branch_code=sube.code,
                    branch_name=sube.name,
                    template_version_id=run.template_version_id,
                    business_day=run.business_day,
                    status=run.status,
                    window_start=run.window_start,
                    writable_from=run.writable_from(self._execution.prep_minutes),
                    window_end=run.window_end,
                    tolerance_end=run.tolerance_end,
                )
            )

        surumler: list[ManifestVersion] = []
        for surum_id in dict.fromkeys(s.template_version_id for s in satirlar):
            surum = self._templates.version(surum_id)
            if surum is None:
                # Sürümü bulunmayan çalıştırma cihazda açılamaz; sessiz
                # geçmek yerine günlüğe yazıyoruz, bu bir tutarsızlıktır.
                log.warning("senk.surum_yok", surum=str(surum_id))
                continue
            surumler.append(
                ManifestVersion(
                    id=surum.id,
                    template_id=surum.template_id,
                    version_no=surum.version_no,
                    published_at=surum.published_at,
                    item_count=len(surum.items),
                )
            )

        return Manifest(
            clock=self._saat(an, device_time),
            horizon_hours=ufuk,
            refresh_after_minutes=MANIFEST_REFRESH_MINUTES,
            runs=tuple(satirlar),
            template_versions=tuple(surumler),
            not_done_reasons=tuple(NOT_DONE_REASON_LABELS.items()),
        )

    # --- kuyruk ------------------------------------------------------

    def apply_batch(
        self,
        *,
        branch_ids: set[UUID],
        user_id: UUID,
        device_time: datetime | None = None,
        answers: list[QueuedAnswer] | None = None,
        evidence: list[QueuedEvidence] | None = None,
    ) -> BatchResult:
        """Kuyruğu işler: önce cevaplar, sonra kanıtlar (FR-0703).

        Sıra önemli: kanıt bir cevaba bağlıdır. Kanıt önce gelirse
        cevabı olmayan bir dosya ortaya çıkar.
        """
        an = self._now()
        saat = self._saat(an, device_time)
        fark = clock_offset(an, device_time)

        cevap_sonuclari = [
            self._cevap_yaz(kayit, branch_ids, user_id, saat.skew_minutes)
            for kayit in (answers or [])
        ]
        kanit_sonuclari = [
            self._kanit_baslat(kayit, branch_ids, user_id, saat.skew_minutes, fark)
            for kayit in (evidence or [])
        ]

        sonuc = BatchResult(
            clock=saat,
            answers=tuple(cevap_sonuclari),
            evidence=tuple(kanit_sonuclari),
        )
        log.info(
            "senk.kuyruk",
            kullanici=str(user_id),
            cihaz_saati=device_time.isoformat() if device_time else None,
            sapma_dk=saat.skew_minutes,
            kabul=sonuc.accepted,
            red=sonuc.rejected,
        )
        return sonuc

    # --- tek kayıt ---------------------------------------------------

    def _cevap_yaz(
        self,
        kayit: QueuedAnswer,
        branch_ids: set[UUID],
        user_id: UUID,
        sapma: int | None,
    ) -> AnswerResult:
        try:
            self._kapsam(kayit.run_id, branch_ids)
            self._execution.write_answer(
                run_id=kayit.run_id,
                answer_id=kayit.answer_id,
                item_id=kayit.item_id,
                state=kayit.state,
                value=kayit.value,
                note=kayit.note,
                user_id=user_id,
                device_id=kayit.device_id,
                device_reported_at=kayit.answered_at,
                evidence_count=kayit.evidence_count,
                not_done_reason=kayit.not_done_reason,
                clock_skew_minutes=sapma,
            )
        except (DomainError, ValidationError) as hata:
            return AnswerResult(kayit.answer_id, "rejected", _hata(hata))
        return AnswerResult(kayit.answer_id, "accepted")

    def _kanit_baslat(
        self,
        kayit: QueuedEvidence,
        branch_ids: set[UUID],
        user_id: UUID,
        sapma: int | None,
        fark: timedelta | None,
    ) -> EvidenceResult:
        try:
            self._kapsam(kayit.run_id, branch_ids)
            if self._evidence.find(kayit.evidence_id) is not None:
                # Aynı kimlik ikinci kez: yarım kalan yükleme sürüyor
                # (FR-0707). Yeni kayıt açmıyoruz, yeni belirteç veriyoruz.
                _, belirtec = self._evidence.resume(kayit.evidence_id)
                return EvidenceResult(kayit.evidence_id, "resumed", belirtec)

            _, belirtec = self._evidence.start(
                run_id=kayit.run_id,
                answer_id=kayit.answer_id,
                item_id=kayit.item_id,
                sha256=kayit.sha256,
                content_type=kayit.content_type,
                size_bytes=kayit.size_bytes,
                user_id=user_id,
                device_id=kayit.device_id,
                from_gallery=kayit.from_gallery,
                captured_at=corrected_time(kayit.captured_at, fark),
                device_reported_at=kayit.captured_at,
                latitude=kayit.latitude,
                longitude=kayit.longitude,
                evidence_id=kayit.evidence_id,
                clock_skew_minutes=sapma,
            )
        except DuplicateEvidence as hata:
            # Aynı fotoğraf başka bir kimlikle gelmiş: cihaz bu kaydı
            # bırakmalı ve kullanıcıya yeniden çekmesini söylemeli.
            return EvidenceResult(kayit.evidence_id, "duplicate", None, _hata(hata))
        except (DomainError, ValidationError) as hata:
            return EvidenceResult(kayit.evidence_id, "rejected", None, _hata(hata))
        return EvidenceResult(kayit.evidence_id, "accepted", belirtec)

    # --- yardımcılar -------------------------------------------------

    def _saat(self, an: datetime, device_time: datetime | None) -> ClockReading:
        sapma = skew_minutes(clock_offset(an, device_time))
        return ClockReading(
            server_time=an,
            device_time=device_time,
            skew_minutes=sapma,
            flagged=clock_flagged(sapma),
        )

    def _kapsam(self, run_id: UUID, branch_ids: set[UUID]) -> None:
        """Kapsam dışı şubenin çalıştırmasına senk yoluyla da yazılamaz."""
        run = self._plans.run(run_id)
        if run is None:
            raise RunOutOfScope(f"Çalıştırma id: {run_id}")
        if run.branch_id not in branch_ids:
            raise RunOutOfScope(f"Şube kapsamınızda değil: {run.branch_id}")
