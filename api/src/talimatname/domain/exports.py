"""Arka planda üretilen çıktılar (ST-102; FR-1217).

Büyük bir dönem raporu istek içinde üretilemez: elli şubenin bir ayı
binlerce çalıştırma demek ve o kadar veriyi okuyup dizmek isteğin
zaman aşımına uğramasına, uğramazsa da bir web işçisinin dakikalarca
bloklanmasına yol açar. Eşiği geçen çıktı bu yüzden **iş kaydına**
dönüşüyor; üretimi zamanlayıcı süreci yapıyor (01-teknik-mimari SCH).

Dört karar burada yazılı:

**Eşik veri büyüklüğünde, çıktı büyüklüğünde değil.** Aylık özet tek
sayfadır ama binlerce çalıştırmayı okuyarak üretilir; pahalı olan
okuma. Bu yüzden ölçü, raporun kapsadığı çalıştırma sayısı (FR-1217).

**İş kaydı kalıcı.** Süreç içi bir kuyruk (ya da isteğin arkasına
iliştirilen bir görev) yeniden başlatmada kaybolurdu ve kullanıcı
beklediği raporun hiç üretilmediğini anlamazdı. Kayıt tabloda durur:
hangi durumda olduğu, kaç kez denendiği ve neden düştüğü görünür.

**Kapsam kullanıcıya bağlı, kayda değil.** İşte yalnızca isteyenin
kimliği duruyor; hangi şubeleri göreceği üretim anında rolünden
okunuyor. Kapsamı kaydın içine dondurmak, rolü daralmış birinin
eski kapsamıyla rapor almasına yol açardı.

**Dosya süresiz durmaz.** Hazır çıktı nesne deposunda bir hafta
kalır, sonra süpürülür: üretilmiş rapor iş verisi taşır ve sonsuza
kadar saklamak, kimsenin istemediği bir arşiv biriktirmektir.
Kayıt kalır, dosya gider — "vardı ama süresi doldu" demek,
"hiç olmadı" demekten dürüsttür.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import Literal
from uuid import UUID

from talimatname.domain.validation import ValidationError

#: Bu sayıdan çok çalıştırma kapsayan çıktı arka plana düşer (FR-1217).
#: Sayı ölçümle değil kararla seçildi: 500 çalıştırma yaklaşık iki
#: şubelik bir yıl ya da elli şubelik bir ay — ikisi de istek içinde
#: üretilmemesi gereken büyüklükler.
BACKGROUND_THRESHOLD = 500

ExportKind = Literal["aylik-ozet", "olcum-gunlugu"]

#: Tür adı sözleşmedir: panel ikonu ve dosya adı buna bakar.
EXPORT_KIND_LABELS: dict[str, str] = {
    "aylik-ozet": "Aylık özet raporu",
    "olcum-gunlugu": "Ölçüm günlüğü",
}

#: Her türün beklediği parametreler. Tek yerde: uç nokta da işçi de
#: aynı anahtarları kullanmak zorunda, yoksa kuyruğa giren iş
#: üretim anında çözülemez.
REQUIRED_PARAMS: dict[str, tuple[str, ...]] = {
    "aylik-ozet": ("year", "month"),
    "olcum-gunlugu": ("first_day", "last_day"),
}

JobState = Literal["queued", "running", "ready", "failed"]

JOB_STATE_LABELS: dict[str, str] = {
    "queued": "Sırada",
    "running": "Hazırlanıyor",
    "ready": "Hazır",
    "failed": "Üretilemedi",
}

#: Kaç deneme sonra pes edilir. Geçici bir hata (ağ, depo) bir sonraki
#: turda düzelebilir; üçüncüde hâlâ düşüyorsa sorun geçici değildir ve
#: sonsuz deneme, kullanıcıyı "hazırlanıyor" yazısıyla oyalamak olur.
MAX_ATTEMPTS = 3

#: Hazır dosya ne kadar durur. Kayıt kalır, dosya süpürülür.
FILE_TTL = timedelta(days=7)


@dataclass(frozen=True, slots=True)
class ExportJob:
    """Kuyruğa girmiş ya da bitmiş bir çıktı işi."""

    id: UUID
    kind: ExportKind
    params: dict[str, str]
    requested_by: UUID
    requested_at: datetime
    run_count: int
    state: JobState = "queued"
    attempts: int = 0
    started_at: datetime | None = None
    finished_at: datetime | None = None
    object_key: str | None = None
    size_bytes: int | None = None
    document_code: str | None = None
    error_code: str | None = None

    def validated(self) -> ExportJob:
        if self.kind not in REQUIRED_PARAMS:
            raise ValidationError("kind", f"Bilinmeyen çıktı türü: {self.kind}")
        eksik = [a for a in REQUIRED_PARAMS[self.kind] if not self.params.get(a)]
        if eksik:
            raise ValidationError("params", f"Eksik parametre: {', '.join(eksik)}")
        if self.requested_at.tzinfo is None:
            raise ValidationError("requested_at", "Zaman saat dilimli olmalı")
        return self

    @property
    def label(self) -> str:
        return EXPORT_KIND_LABELS.get(self.kind, "Çıktı")

    @property
    def state_label(self) -> str:
        return JOB_STATE_LABELS[self.state]

    @property
    def downloadable(self) -> bool:
        return self.state == "ready" and self.object_key is not None

    def expired(self, now: datetime) -> bool:
        """Dosyasının süresi doldu mu? Kayıt için değil, dosya için."""
        if self.finished_at is None or self.object_key is None:
            return False
        return now - self.finished_at > FILE_TTL

    # --- geçişler (saf) ----------------------------------------------

    def claimed(self, now: datetime) -> ExportJob:
        """İşçi işi üstleniyor. Deneme sayacı **burada** artıyor:
        çöken bir işçinin bıraktığı iş de denenmiş sayılsın."""
        return replace(self, state="running", started_at=now, attempts=self.attempts + 1)

    def completed(self, now: datetime, *, key: str, size: int, code: str | None) -> ExportJob:
        return replace(
            self,
            state="ready",
            finished_at=now,
            object_key=key,
            size_bytes=size,
            document_code=code,
            error_code=None,
        )

    def broken(self, now: datetime, *, code: str) -> ExportJob:
        """Düştü. Denemesi kaldıysa sıraya döner, kalmadıysa biter."""
        if self.attempts < MAX_ATTEMPTS:
            return replace(self, state="queued", error_code=code)
        return replace(self, state="failed", finished_at=now, error_code=code)

    def swept(self) -> ExportJob:
        """Dosya silindi; kayıt duruyor ve indirilemez olduğunu söylüyor."""
        return replace(self, object_key=None)


def file_name(job: ExportJob) -> str:
    """İndirilen dosyanın adı.

    ASCII: `Content-Disposition` başlığında Türkçe harf sorun
    çıkarıyor. Dönem adın içinde çünkü indirilen üç dosya aynı
    klasörde yan yana durunca hangisinin hangisi olduğu ancak
    adından anlaşılır.
    """
    if job.kind == "aylik-ozet":
        donem = f"{job.params.get('year', '')}-{job.params.get('month', '').zfill(2)}"
    else:
        ilk = job.params.get("first_day", "").replace("-", "")
        son = job.params.get("last_day", "").replace("-", "")
        donem = f"{ilk}-{son}"
    return f"talimatname-{job.kind}-{donem}.pdf"


def same_request(job: ExportJob, *, kind: str, params: dict[str, str]) -> bool:
    """Aynı isteğin tekrarı mı? İki kez tıklamak iki iş açmamalı."""
    return job.kind == kind and job.params == params


def pending(job: ExportJob) -> bool:
    return job.state in ("queued", "running")


__all__ = [
    "BACKGROUND_THRESHOLD",
    "EXPORT_KIND_LABELS",
    "FILE_TTL",
    "JOB_STATE_LABELS",
    "MAX_ATTEMPTS",
    "REQUIRED_PARAMS",
    "ExportJob",
    "ExportKind",
    "JobState",
    "file_name",
    "pending",
    "same_request",
]
