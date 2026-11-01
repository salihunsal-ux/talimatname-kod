"""Arka planda çıktı üretimi (ST-102; FR-1217).

Üç parça burada: isteği **kuyruğa alan** yol (uç nokta çağırıyor),
kuyruğu **boşaltan** işçi (zamanlayıcı turu çağırıyor) ve hazır
dosyayı **veren** yol.

Dört karar:

**Üretim zamanlayıcı sürecinde.** İsteğin arkasına iliştirilen bir
görev (BackgroundTasks) web işçisini dakikalarca meşgul eder ve
yeniden başlatmada iz bırakmadan kaybolur. Zamanlayıcı zaten ayrı bir
süreç (01-teknik-mimari SCH) ve işi idempotent; çıktı da oraya düştü.

**Kapsam üretim anında hesaplanıyor.** İşte yalnızca isteyenin kimliği
var; hangi şubeleri göreceği üretim anında rolünden okunuyor ve bunu
yapan fonksiyon uç noktanınkiyle **aynı** (`erisilebilir_sube_idleri`).
İki ayrı kapsam hesabı, arka plandaki kâğıdın kullanıcının göremediği
şubeleri taşıması demek olurdu.

**Belge kodu senkron yoldakiyle aynı.** Çıktı olay günlüğüne yazılıyor
ve kâğıttaki kod o kaydın zincir özeti (FR-1218): arka planda üretilen
rapor da doğrulama sayfasından sorulabiliyor. Olayın aktörü isteği
yapan kişi — işçi değil.

**Hata saklanmıyor.** Düşen iş üç kez deneniyor, sonra `failed`
kalıyor ve neden düştüğü kayıtta duruyor. Sonsuz deneme, kullanıcıyı
"hazırlanıyor" yazısıyla oyalamak olurdu.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, date, datetime
from typing import Protocol
from uuid import UUID, uuid4

import structlog

from talimatname.domain.errors import DomainError, ErrorKind
from talimatname.domain.exports import (
    FILE_TTL,
    ExportJob,
    ExportKind,
    pending,
    same_request,
)
from talimatname.services.audit import AuditService, RequestContext, using_context
from talimatname.services.exports import record_document
from talimatname.services.notifications import NotificationService
from talimatname.services.organization import (
    OrganizationService,
    erisilebilir_sube_idleri,
    sube_kodlari,
)
from talimatname.services.pdf import (
    Brand,
    measurements_code,
    measurements_pdf,
    monthly_code,
    monthly_pdf,
)
from talimatname.services.reports import ReportService
from talimatname.services.storage import ObjectStore
from talimatname.services.users import UserRepository

log = structlog.get_logger(__name__)

#: Bir turda kaç iş üretilir. Zamanlayıcı dakikada bir koşuyor;
#: ikisi, tek turu dakikalarca uzatmadan kuyruğu akıtmaya yetiyor.
BATCH = 2

#: Bir turda kaç süresi dolmuş dosya silinir.
SWEEP_BATCH = 50


class JobNotFound(DomainError):
    code = "cikti-bulunamadi"
    title = "Çıktı bulunamadı"
    kind: ErrorKind = "not_found"


class JobNotReady(DomainError):
    code = "cikti-hazir-degil"
    title = "Çıktı henüz hazır değil"
    kind: ErrorKind = "conflict"


class JobFileGone(DomainError):
    code = "cikti-suresi-doldu"
    title = "Çıktının dosyası silinmiş"
    kind: ErrorKind = "not_found"


class ExportJobRepository(Protocol):
    def job(self, job_id: UUID) -> ExportJob | None: ...

    def jobs_for_user(self, user_id: UUID, *, limit: int = 20) -> list[ExportJob]:
        """Kişinin işleri, **yeniden eskiye**."""
        ...

    def save_job(self, job: ExportJob) -> None: ...

    def queued_jobs(self, limit: int) -> list[ExportJob]:
        """Sıradakiler, **eskiden yeniye**: ilk isteyen ilk alır."""
        ...

    def files_before(self, before: datetime, limit: int) -> list[ExportJob]:
        """Dosyası bu andan **önce** biten işler (süpürme için).

        Süre sınırını servis uyguluyor: depo politika bilmez.
        """
        ...


class ExportJobService:
    def __init__(
        self,
        repo: ExportJobRepository,
        reports: ReportService,
        org: OrganizationService,
        users: UserRepository,
        store: ObjectStore,
        *,
        brand: Callable[[], Brand],
        audit: AuditService | None = None,
        notifications: NotificationService | None = None,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._repo = repo
        self._raporlar = reports
        self._org = org
        self._kullanicilar = users
        self._depo = store
        self._marka = brand
        self._izi = audit
        self._bildirim = notifications
        self._now = now

    # --- kuyruğa alma -------------------------------------------------

    def queue(
        self, user_id: UUID, *, kind: ExportKind, params: dict[str, str], run_count: int
    ) -> ExportJob:
        """İşi kuyruğa alır. **Aynı istek ikinci kez iş açmaz.**

        Kullanıcı düğmeye iki kez bastığında ya da sayfayı
        yenilediğinde aynı raporu iki kez üretmek, en pahalı işi
        boşuna yapmak olurdu.
        """
        for mevcut in self._repo.jobs_for_user(user_id):
            if pending(mevcut) and same_request(mevcut, kind=kind, params=params):
                return mevcut

        is_kaydi = ExportJob(
            id=uuid4(),
            kind=kind,
            params=dict(params),
            requested_by=user_id,
            requested_at=self._now(),
            run_count=run_count,
        ).validated()
        self._repo.save_job(is_kaydi)
        log.info("cikti.kuyruga_alindi", tur=kind, calistirma=run_count)
        return is_kaydi

    def jobs_for(self, user_id: UUID, *, limit: int = 20) -> list[ExportJob]:
        return self._repo.jobs_for_user(user_id, limit=limit)

    def job_for(self, user_id: UUID, job_id: UUID) -> ExportJob:
        """Kişinin kendi işi. Başkasının işi **yok** sayılıyor.

        "Yetkiniz yok" demek, o işin var olduğunu söylemek olurdu.
        """
        is_kaydi = self._repo.job(job_id)
        if is_kaydi is None or is_kaydi.requested_by != user_id:
            raise JobNotFound()
        return is_kaydi

    def file(self, user_id: UUID, job_id: UUID) -> tuple[ExportJob, bytes]:
        """Hazır dosyayı verir. **Yalnızca isteyen indirebilir.**

        Çıktı, isteyenin kapsamıyla üretildi; başkasına vermek o
        kapsamı delmek olurdu. Paylaşılabilir bağlantı ayrı bir iş
        (FR-1216, v1.1).
        """
        is_kaydi = self.job_for(user_id, job_id)
        if is_kaydi.state != "ready":
            raise JobNotReady(detail=f"Çıktı durumu: {is_kaydi.state_label}")
        if is_kaydi.object_key is None:
            raise JobFileGone()
        try:
            return is_kaydi, self._depo.get(is_kaydi.object_key)
        except Exception as hata:
            log.warning("cikti.dosya_okunamadi", is_id=str(job_id), sebep=str(hata))
            raise JobFileGone() from hata

    # --- işçi (zamanlayıcı turu) --------------------------------------

    def run_pending(self, limit: int = BATCH) -> tuple[int, int]:
        """Sıradaki işleri üretir. Dönen: (biten, düşen)."""
        biten = dusen = 0
        for is_kaydi in self._repo.queued_jobs(limit):
            calisan = is_kaydi.claimed(self._now())
            self._repo.save_job(calisan)
            try:
                baytlar, kod = self._uret(calisan)
            except Exception as hata:
                dusen += 1
                kirik = calisan.broken(self._now(), code=_hata_kodu(hata))
                self._repo.save_job(kirik)
                log.exception("cikti.uretilemedi", is_id=str(is_kaydi.id), durum=kirik.state)
                continue

            anahtar = f"exports/{calisan.id}.pdf"
            self._depo.put(anahtar, baytlar)
            hazir = calisan.completed(self._now(), key=anahtar, size=len(baytlar), code=kod)
            self._repo.save_job(hazir)
            self._haber_ver(hazir)
            biten += 1
            log.info("cikti.hazir", is_id=str(hazir.id), bayt=len(baytlar))
        return biten, dusen

    def sweep_files(self, limit: int = SWEEP_BATCH) -> int:
        """Süresi dolmuş dosyaları siler; **kayıt kalır** (FR-1217).

        Kaydı da silmek, kullanıcıya "böyle bir rapor hiç olmadı"
        demek olurdu; oysa oldu ve süresi doldu.
        """
        silinen = 0
        for is_kaydi in self._repo.files_before(self._now() - FILE_TTL, limit):
            if is_kaydi.object_key is None:
                continue
            try:
                self._depo.delete(is_kaydi.object_key)
            except Exception:
                log.warning("cikti.dosya_silinemedi", is_id=str(is_kaydi.id))
            self._repo.save_job(is_kaydi.swept())
            silinen += 1
        return silinen

    # --- üretim -------------------------------------------------------

    def _uret(self, is_kaydi: ExportJob) -> tuple[bytes, str | None]:
        kullanici = self._kullanicilar.user(is_kaydi.requested_by)
        if kullanici is None:
            raise LookupError("kullanici-yok")

        kapsam = erisilebilir_sube_idleri(kullanici, self._org)
        marka = self._marka()
        an = self._now()
        # Olayın aktörü **isteyen kişi**: kâğıdı o istedi, işçi yalnızca
        # üretti. Günlüğe işçiyi yazmak, izi okunamaz kılardı.
        with using_context(RequestContext(actor_id=kullanici.id)):
            if is_kaydi.kind == "aylik-ozet":
                return self._aylik(is_kaydi, kapsam, marka, an, kullanici.full_name)
            return self._olcum(is_kaydi, kapsam, marka, an, kullanici.full_name)

    def _aylik(
        self,
        is_kaydi: ExportJob,
        kapsam: set[UUID],
        marka: Brand,
        an: datetime,
        kisi: str,
    ) -> tuple[bytes, str | None]:
        yil, ay = int(is_kaydi.params["year"]), int(is_kaydi.params["month"])
        ozet = self._raporlar.monthly(yil, ay, branch_ids=kapsam)
        kod = record_document(
            self._izi,
            tur="aylik-ozet",
            icerik_kodu=monthly_code(ozet, brand=marka),
            donem=f"{yil}-{ay:02d}",
        )
        return monthly_pdf(ozet, brand=marka, generated_at=an, generated_by=kisi, code=kod), kod

    def _olcum(
        self,
        is_kaydi: ExportJob,
        kapsam: set[UUID],
        marka: Brand,
        an: datetime,
        kisi: str,
    ) -> tuple[bytes, str | None]:
        ilk = date.fromisoformat(is_kaydi.params["first_day"])
        son = date.fromisoformat(is_kaydi.params["last_day"])
        yalniz = is_kaydi.params.get("only_out_of_range") == "1"
        seriler = self._raporlar.measurements(
            first_day=ilk, last_day=son, branch_ids=kapsam, only_out_of_range=yalniz
        )
        kod = record_document(
            self._izi,
            tur="olcum-gunlugu",
            icerik_kodu=measurements_code(seriler, brand=marka, first_day=ilk, last_day=son),
            donem=f"{ilk:%Y-%m-%d}/{son:%Y-%m-%d}",
        )
        return measurements_pdf(
            seriler,
            brand=marka,
            first_day=ilk,
            last_day=son,
            branch_codes=sube_kodlari(self._org),
            generated_at=an,
            generated_by=kisi,
            code=kod,
        ), kod

    # --- bildirim -----------------------------------------------------

    def _haber_ver(self, is_kaydi: ExportJob) -> None:
        """Hazır olduğunu kuyruğa yazar (FR-1217).

        Sürücü bağlı değilse kayıt `failed` olur ve panelde "sürücü
        yok" diye görünür — ürün "gönderildi" demiyor (ST-044). Çıktı
        listesi zaten hazır durumu gösteriyor, bildirim ikinci yol.
        """
        if self._bildirim is None:
            return
        kullanici = self._kullanicilar.user(is_kaydi.requested_by)
        if kullanici is None:
            return
        self._bildirim.queue(
            kind="export_ready",
            user=kullanici,
            subject_id=is_kaydi.id,
            title=f"{is_kaydi.label} hazır",
            body="Hazırladığınız çıktı indirilebilir.",
            send_at=self._now(),
            timezone=self._marka().timezone,
            deep_link=f"/raporlar/ciktilar/{is_kaydi.id}",
        )


def _hata_kodu(hata: Exception) -> str:
    """Hatanın kullanıcıya gösterilen kısa karşılığı.

    Ayrıntı günlüğe gidiyor; kayda sınıf adı yazılıyor çünkü
    kullanıcıya yığın izi göstermek ne anlaşılır ne güvenli.
    """
    if isinstance(hata, LookupError):
        return str(hata) or "bulunamadi"
    return type(hata).__name__


__all__ = [
    "ExportJobRepository",
    "ExportJobService",
    "JobFileGone",
    "JobNotFound",
    "JobNotReady",
]
