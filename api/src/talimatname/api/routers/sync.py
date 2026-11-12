"""Senk uç noktaları (ST-054; FR-0701, FR-0703, FR-0704, FR-0707).

Mobilin çevrimdışı kuyruğunun sunucu yüzeyi — ADR-0013'ün üçüncü devir
sözleşmesi. İki çağrı:

```
GET  /sync/manifest   → ne indireceğim? (48 saat, sürüm kimlikleri, sınırlar)
POST /sync/batch      → kuyruğumu al (cevaplar + kanıt niyetleri)
```

`/sync/batch` **200 döner ve her kayıt kendi sonucunu taşır**. Tek bozuk
kayıt yüzünden 4xx dönmek, cihazın kuyruğunu sonsuza kadar tıkamak
olurdu; hata kodu kayıt başına geliyor ve `retryable` cihaza ne
yapacağını söylüyor.

Kanıt baytları bu çağrıda **gitmez**: cihaz dönen yükleme adresine
dosyaları tek tek yükler, sonra `POST /evidence/{id}/complete` ile
sunucu özeti doğrular. Fotoğrafları kuyruk isteğine gömmek, 500 kayıtlı
bir kuyrukta tek bir dev istek demekti.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import date, datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request
from pydantic import BaseModel, Field

from talimatname.api.bagimliliklar import organizasyon_servisi, senk_servisi
from talimatname.api.errors import URN_PREFIX
from talimatname.api.guvenlik import Kullanici
from talimatname.domain.evidence import MAX_BYTES
from talimatname.domain.sync import (
    MANIFEST_HORIZON_HOURS,
    MANIFEST_HORIZON_MAX_HOURS,
    MAX_BATCH_ANSWERS,
    MAX_BATCH_EVIDENCE,
)
from talimatname.services.organization import (
    OrganizationService,
    erisilebilir_sube_idleri,
)
from talimatname.services.sync import (
    BatchResult,
    ClockReading,
    Manifest,
    QueuedAnswer,
    QueuedEvidence,
    SyncService,
)

router = APIRouter(tags=["senk"])

Servis = Annotated[SyncService, Depends(senk_servisi)]
OrgServis = Annotated[OrganizationService, Depends(organizasyon_servisi)]


class SaatCiktisi(BaseModel):
    """Senk anındaki saat ölçümü (FR-0704, BR-13).

    `skew_minutes` pozitifse cihaz **ileri**. Çekim zamanları bu farkla
    düzeltilerek saklanır; ham cihaz değeri de kaydın içinde kalır.
    Olay zamanı (cevabın yazıldığı an) **sunucununkidir**: düzeltme
    yalnızca çekim zamanına uygulanır, yoksa saati geri alan bir cihaz
    kapanmış pencereye yazabilirdi.
    """

    server_time: datetime
    device_time: datetime | None = None
    skew_minutes: int | None = None
    flagged: bool = Field(description="Fark eşiği aştı mı (10 dk; BR-13)")


class ManifestCalistirmasi(BaseModel):
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
    #: Cevap yazmanın açıldığı an; cihaz bundan önce doldurmaya
    #: kalkmamalı (sunucu `pencere-acilmadi` ile reddeder).
    writable_from: datetime


class ManifestSurumu(BaseModel):
    """Şablon sürümünün kimliği. İçeriği `GET /template-versions/{id}`.

    Sürüm yayınlandıktan sonra **değişmez**: cihaz bir kez indirir ve
    süresiz önbelleğe alır. Manifest her 15 dakikada tazelenirken
    şablon ağacını yeniden göndermek mobil veriyi boşa harcardı.
    """

    id: UUID
    template_id: UUID
    version_no: int
    published_at: datetime | None = None
    item_count: int


class SebepCiktisi(BaseModel):
    code: str
    label: str


class KuyrukPolitikasi(BaseModel):
    """Cihazın uygulayacağı sınırlar (FR-0604, FR-0605, FR-0706)."""

    max_evidence_per_item: int
    max_evidence_bytes: int
    queue_evidence_limit: int
    queue_hours: int
    #: Tek partiye sığan kayıt sayısı; kuyruk sınırından ayrı. Cihaz
    #: kuyruğunu buna göre dilimler (Spike A bulgusu).
    batch_answer_limit: int
    batch_evidence_limit: int


class ManifestCiktisi(BaseModel):
    clock: SaatCiktisi
    horizon_hours: int
    refresh_after_minutes: int
    runs: list[ManifestCalistirmasi]
    template_versions: list[ManifestSurumu]
    not_done_reasons: list[SebepCiktisi]
    policy: KuyrukPolitikasi


class KuyruktakiCevap(BaseModel):
    """Cihazda verilmiş bir cevap. `answer_id` **cihazda** üretildi."""

    answer_id: UUID
    run_id: UUID
    item_id: UUID
    state: Literal["passed", "failed", "not_done", "not_applicable"]
    value: Any = None
    note: str | None = None
    not_done_reason: (
        Literal["no_material", "equipment_broken", "no_time", "not_authorized", "other"] | None
    ) = Field(default=None, description="Yapılamadı sebebi; zorunlu (BR-09)")
    device_id: UUID | None = None
    answered_at: datetime | None = Field(
        default=None, description="Cihaz saatiyle cevap zamanı; ham olarak saklanır"
    )
    evidence_count: int = Field(default=0, ge=0, le=3)


class KuyruktakiKanit(BaseModel):
    """Cihazda çekilmiş bir fotoğrafın niyeti; baytlar ayrı istekte."""

    evidence_id: UUID
    run_id: UUID
    answer_id: UUID
    item_id: UUID
    sha256: str = Field(min_length=64, max_length=64)
    content_type: Literal["image/jpeg", "image/png"]
    size_bytes: int = Field(gt=0, le=MAX_BYTES)
    from_gallery: bool = False
    captured_at: datetime | None = Field(
        default=None, description="Cihaz saatiyle çekim zamanı; sunucu düzeltir"
    )
    device_id: UUID | None = None
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)


class KuyrukGirdisi(BaseModel):
    device_time: datetime | None = Field(
        default=None, description="Cihazın isteği gönderdiği andaki saati (FR-0704)"
    )
    answers: list[KuyruktakiCevap] = Field(default_factory=list, max_length=MAX_BATCH_ANSWERS)
    evidence: list[KuyruktakiKanit] = Field(default_factory=list, max_length=MAX_BATCH_EVIDENCE)


class KayitHatasi(BaseModel):
    """Tek kaydın reddi. İstemci `type`a göre davranır, metne göre değil."""

    type: str
    title: str
    detail: str | None = None
    retryable: bool = Field(description="Sonra denemek işe yarar mı (ör. kilit süresi dolunca)")


class CevapSonucu(BaseModel):
    answer_id: UUID
    outcome: Literal["accepted", "rejected"]
    error: KayitHatasi | None = None


class KanitSonucu(BaseModel):
    """`resumed`: kayıt vardı, yükleme sürüyor. `duplicate`: fotoğraf tekrarı."""

    evidence_id: UUID
    outcome: Literal["accepted", "resumed", "duplicate", "rejected"]
    upload_url: str | None = None
    upload_method: Literal["PUT"] = "PUT"
    expires_in_minutes: int | None = None
    error: KayitHatasi | None = None


class KuyrukCiktisi(BaseModel):
    clock: SaatCiktisi
    accepted: int
    rejected: int
    answers: list[CevapSonucu]
    evidence: list[KanitSonucu]


def _saat(okuma: ClockReading) -> SaatCiktisi:
    return SaatCiktisi(
        server_time=okuma.server_time,
        device_time=okuma.device_time,
        skew_minutes=okuma.skew_minutes,
        flagged=okuma.flagged,
    )


def _manifest(m: Manifest) -> ManifestCiktisi:
    return ManifestCiktisi(
        clock=_saat(m.clock),
        horizon_hours=m.horizon_hours,
        refresh_after_minutes=m.refresh_after_minutes,
        runs=[ManifestCalistirmasi(**asdict(r)) for r in m.runs],
        template_versions=[ManifestSurumu(**asdict(s)) for s in m.template_versions],
        not_done_reasons=[SebepCiktisi(code=k, label=e) for k, e in m.not_done_reasons],
        policy=KuyrukPolitikasi(**asdict(m.policy)),
    )


@router.get("/sync/manifest", summary="Çevrimdışı önbellek manifesti")
def senk_manifesti(
    servis: Servis,
    org: OrgServis,
    kullanici: Kullanici,
    horizon_hours: Annotated[int, Query(ge=1, le=MANIFEST_HORIZON_MAX_HOURS)] = (
        MANIFEST_HORIZON_HOURS
    ),
    device_time: Annotated[datetime | None, Header(alias="X-Device-Time")] = None,
) -> ManifestCiktisi:
    """Cihazın indireceği liste: kapsamındaki şubelerin çalıştırmaları.

    Kapsam **kullanıcıdan** okunur: personel yalnızca kendi şubesini
    indirir. Şablon sürümlerinin yalnızca kimliği döner; içeriği
    değişmediği için cihaz bir kez indirip saklar.

    Cihaz saati **başlıkta** (`X-Device-Time`), sorgu dizesinde değil:
    ISO zamanın `+00:00` eki sorgu dizesinde boşluğa çözülüyor ve istek
    422 dönüyordu. Denemede ilk elde yakalandı; mobil de aynı tuzağa
    düşecekti. POST'ta aynı değer gövdede taşınıyor.
    """
    return _manifest(
        servis.manifest(
            branch_ids=erisilebilir_sube_idleri(kullanici, org),
            device_time=device_time,
            horizon_hours=horizon_hours,
        )
    )


@router.post("/sync/batch", summary="Cihaz kuyruğunu gönder (kısmi başarı)")
def senk_kuyrugu(
    girdi: KuyrukGirdisi,
    servis: Servis,
    org: OrgServis,
    kullanici: Kullanici,
    request: Request,
) -> KuyrukCiktisi:
    """Kuyruğu işler ve **her kayıt için** ayrı sonuç döner.

    Kayıt kimlikleri cihazda üretildiği için aynı kuyruğu iki kez
    göndermek ikinci kayıt açmaz (FR-0707): cevap güncellenir, kanıt
    `resumed` döner ve yükleme kaldığı yerden devam eder.

    Cevapları yazan oturumdaki kullanıcıdır; gövdede kullanıcı alanı yok.
    """
    sonuc = servis.apply_batch(
        branch_ids=erisilebilir_sube_idleri(kullanici, org),
        user_id=kullanici.id,
        device_time=girdi.device_time,
        answers=[
            QueuedAnswer(
                answer_id=k.answer_id,
                run_id=k.run_id,
                item_id=k.item_id,
                state=k.state,
                value=k.value,
                note=k.note,
                not_done_reason=k.not_done_reason,
                device_id=k.device_id,
                answered_at=k.answered_at,
                evidence_count=k.evidence_count,
            )
            for k in girdi.answers
        ],
        evidence=[
            QueuedEvidence(
                evidence_id=k.evidence_id,
                run_id=k.run_id,
                answer_id=k.answer_id,
                item_id=k.item_id,
                sha256=k.sha256,
                content_type=k.content_type,
                size_bytes=k.size_bytes,
                from_gallery=k.from_gallery,
                captured_at=k.captured_at,
                device_id=k.device_id,
                latitude=k.latitude,
                longitude=k.longitude,
            )
            for k in girdi.evidence
        ],
    )
    return _kuyruk(sonuc, request)


def _kuyruk(sonuc: BatchResult, request: Request) -> KuyrukCiktisi:
    def hata(h: Any) -> KayitHatasi | None:
        if h is None:
            return None
        return KayitHatasi(
            type=URN_PREFIX + h.code,
            title=h.title,
            detail=h.detail,
            retryable=h.retryable,
        )

    return KuyrukCiktisi(
        clock=_saat(sonuc.clock),
        accepted=sonuc.accepted,
        rejected=sonuc.rejected,
        answers=[
            CevapSonucu(answer_id=c.answer_id, outcome=c.outcome, error=hata(c.error))
            for c in sonuc.answers
        ],
        evidence=[
            KanitSonucu(
                evidence_id=k.evidence_id,
                outcome=k.outcome,
                upload_url=(
                    request.url_for("kanit_yukle", token=k.upload_token).path
                    if k.upload_token
                    else None
                ),
                expires_in_minutes=15 if k.upload_token else None,
                error=hata(k.error),
            )
            for k in sonuc.evidence
        ],
    )
