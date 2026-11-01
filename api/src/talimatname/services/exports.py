"""Çalıştırma PDF'inin derlenmesi (ST-091; FR-1213, FR-1218).

Kâğıdın verisi beş yerden geliyor: çalıştırma ve şablon (yürütme),
cevaplar, kanıt küçük resimleri (nesne deposu), kişi adları ve olay
günlüğü. Bunları tek yerde toplamak için bu servis var — `services/pdf`
yalnızca dizgi yapıyor, depo ve kova bilmiyor.

Üç karar:

**Küçük resim, damgalı kopya değil.** Kâğıda basılan fotoğraf 320
pikselliktir; damgalı kopya tam boy ve dosya birkaç yüz kilobayt.
Otuz maddelik bir listede fark on megabaytı geçiyor ve kâğıtta
görünen aynı. Damganın metni zaten madde satırında yazılı (şube,
saat, kişi).

**Eksik kanıt raporu düşürmez.** Depoda bulunamayan ya da açılamayan
bir dosya atlanıyor, rapor üretiliyor. Denetim gününde elde eksik
kâğıt olması, hiç kâğıt olmamasından iyidir — eksik olan da satırın
"kanıt sayısı" bilgisinden görülüyor.

**Olay günlüğü özeti kâğıda giriyor.** FR-1213 "denetim izi özeti"
istiyor: bu çalıştırmaya dokunan olaylar, zamanı ve nereden geldiği.
Günlük bağlı değilse bölüm hiç basılmıyor — boş bir "Denetim izi"
başlığı, iz tutulmadığını değil olay olmadığını düşündürürdü.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID

import structlog

from talimatname.domain.audit import format_code
from talimatname.domain.evidence import Evidence
from talimatname.domain.plans import RUN_RESULT_LABELS, RUN_STATUS_LABELS
from talimatname.domain.scoring import ANSWER_STATE_LABELS
from talimatname.domain.sync import NOT_DONE_REASON_LABELS
from talimatname.domain.templates import ITEM_TYPE_LABELS, Item
from talimatname.services.audit import AuditService
from talimatname.services.evidence import EvidenceService
from talimatname.services.execution import ExecutionService
from talimatname.services.organization import OrganizationRepository
from talimatname.services.pdf import AuditLine, RunLine, RunReport, _sayi
from talimatname.services.templates import TemplateRepository
from talimatname.services.users import UserRepository

log = structlog.get_logger(__name__)

#: Bir maddenin kâğıda giren en çok fotoğrafı. Dördü bir satır;
#: beşincisi sayfayı taşırıyor ve denetçiye bir şey katmıyor.
MAX_PHOTOS = 4

#: Kâğıda giren en çok olay satırı. Uzun iz, özet olmaktan çıkar.
MAX_AUDIT_LINES = 40


class ExportService:
    def __init__(
        self,
        execution: ExecutionService,
        evidence: EvidenceService,
        org: OrganizationRepository,
        templates: TemplateRepository,
        users: UserRepository | None = None,
        audit: AuditService | None = None,
        *,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._yurutme = execution
        self._kanit = evidence
        self._org = org
        self._sablonlar = templates
        self._kullanicilar = users
        self._izi = audit
        self._now = now

    def run_report(self, run_id: UUID) -> RunReport:
        """Çalıştırmanın kâğıt karşılığını derler (FR-1213)."""
        gorunum = self._yurutme.view(run_id)
        run = gorunum.run
        sube = self._org.branch(run.branch_id)
        kanitlar = self._kanit.for_run(run_id)

        satirlar: list[RunLine] = []
        for bolum in gorunum.version.sections:
            for madde in bolum.items:
                cevap = gorunum.answers.get(madde.id)
                madde_kanitlari = [k for k in kanitlar if k.item_id == madde.id]
                satirlar.append(
                    RunLine(
                        section=bolum.title,
                        title=madde.title,
                        kind=ITEM_TYPE_LABELS[madde.type],
                        critical=madde.critical,
                        state=self._durum(cevap),
                        value=self._deger(madde, cevap),
                        reason=self._sebep(cevap),
                        note=cevap.note if cevap else None,
                        answered_at=cevap.answered_at if cevap else None,
                        by=self._kisi(cevap.user_id) if cevap else None,
                        photos=self._fotograflar(madde_kanitlari),
                    )
                )

        return RunReport(
            run_id=run.id,
            branch_name=sube.name if sube else "—",
            branch_code=sube.code if sube else "—",
            template_title=self._sablon_adi(gorunum.version.template_id),
            business_day=run.business_day,
            window_start=run.window_start,
            window_end=run.window_end,
            status_label=RUN_STATUS_LABELS.get(run.status, run.status),
            result_label=(RUN_RESULT_LABELS.get(run.result, run.result) if run.result else "—"),
            score_percent=run.score_percent,
            submitted_at=run.submitted_at,
            submitted_by=self._kisi(run.locked_by),
            lines=tuple(satirlar),
            audit=self._iz(run_id),
        )

    def _sablon_adi(self, template_id: UUID) -> str:
        sablon = self._sablonlar.template(template_id)
        return sablon.name if sablon else "Liste"

    # --- parçalar ----------------------------------------------------

    @staticmethod
    def _durum(cevap: object) -> str:
        """Kısa tutuluyor: durum sütunu dar, uzun metin iki satıra bölünür."""
        if cevap is None:
            return "Cevapsız"
        durum = getattr(cevap, "state", "")
        return ANSWER_STATE_LABELS.get(durum, durum)

    @staticmethod
    def _sebep(cevap: object) -> str | None:
        """Yapılamadı sebebi (BR-09); ayrıntı satırına giriyor."""
        sebep = getattr(cevap, "not_done_reason", None) if cevap else None
        return NOT_DONE_REASON_LABELS.get(sebep, sebep) if sebep else None

    @staticmethod
    def _deger(madde: Item, cevap: object) -> str:
        """Cevabın okunur hâli. Sayıya birim ekleniyor: denetçi birimsiz
        bir '7' ile ne yapacağını bilemez."""
        if cevap is None:
            return ""
        deger = getattr(cevap, "value", None)
        if deger is None or deger == "":
            return ""
        if isinstance(deger, bool):
            return "Evet" if deger else "Hayır"
        if isinstance(deger, int | float):
            # Ondalık ayırıcı virgül: ölçüm günlüğüyle aynı biçim.
            sayi = _sayi(float(deger))
            return f"{sayi} {madde.unit}" if madde.unit else sayi
        return str(deger)

    def _kisi(self, user_id: UUID | None) -> str | None:
        if user_id is None or self._kullanicilar is None:
            return None
        kisi = self._kullanicilar.user(user_id)
        return kisi.full_name if kisi else None

    def _fotograflar(self, kanitlar: list[Evidence]) -> tuple[bytes, ...]:
        """Küçük resim baytları; okunamayan atlanır (raporu düşürmez)."""
        baytlar: list[bytes] = []
        for kanit in kanitlar[:MAX_PHOTOS]:
            veri = self._kanit.thumbnail_bytes(kanit)
            if veri is not None:
                baytlar.append(veri)
        return tuple(baytlar)

    def _iz(self, run_id: UUID) -> tuple[AuditLine, ...]:
        if self._izi is None:
            return ()
        satirlar: list[AuditLine] = []
        for olay in self._izi.for_object(run_id, limit=MAX_AUDIT_LINES):
            satirlar.append(
                AuditLine(
                    at=olay.at,
                    label=olay.label,
                    actor=self._kisi(olay.actor_id),
                    ip=olay.ip,
                )
            )
        return tuple(satirlar)


def record_document(
    audit: AuditService | None,
    *,
    tur: str,
    icerik_kodu: str,
    donem: str | None = None,
    sube: str | None = None,
    nesne_turu: str = "rapor",
    nesne_id: UUID | None = None,
) -> str | None:
    """Raporu olay günlüğüne yazar ve kâğıttaki kodu döner (FR-1218).

    Kâğıttaki kod, **olayın zincir özeti**: doğrulama sayfası koda göre
    bu kaydı buluyor. Kaydın içinde raporun içerik kodu da duruyor,
    böylece "hangi veri dökülmüş" sorusu da cevaplanıyor.

    `donem` ve `sube` kayda yazılıyor çünkü doğrulama sayfası bunları
    gösteriyor: denetçi elindeki kâğıtla karşılaştırabilsin. Fazlası
    (puan, madde sonuçları, kimin ürettiği) **yazılmıyor** — sayfa onu
    göstermiyor, günlüğe de iş için gerekmeyen veri girmemeli (BR-21).

    Günlük yazılamazsa None dönüyor: rapor yine üretiliyor ama kâğıtta
    kodun zincire bağlı **olmadığı** yazıyor. Bağlıymış gibi yazmak,
    olmayan bir güvence vermek olurdu.

    Senkron uç nokta da arka plan işçisi de (FR-1217) burayı çağırıyor:
    iki yoldan çıkan kâğıdın kodu aynı kuralla üretilmek zorunda.
    """
    if audit is None:
        return None
    ozet: dict[str, object] = {"tur": tur, "icerik": icerik_kodu}
    if donem is not None:
        ozet["donem"] = donem
    if sube is not None:
        ozet["sube"] = sube
    olay = audit.record(
        "rapor.uretildi",
        object_type=nesne_turu,
        object_id=nesne_id,
        after=ozet,
    )
    return format_code(olay.hash) if olay else None


def pdf_filename(report: RunReport) -> str:
    """ASCII dosya adı: Content-Disposition'da Türkçe harf sorun çıkarıyor."""
    kod = report.branch_code.encode("ascii", "ignore").decode() or "sube"
    return f"talimatname-calistirma-{kod}-{report.business_day:%Y%m%d}.pdf"


__all__ = ["ExportService", "pdf_filename", "record_document"]
