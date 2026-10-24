"""Kanıt uç noktaları (ST-039, ST-049; FR-0606, FR-0614, FR-0615, FR-1305).

Akış mobil için tasarlandı ve panelde de aynı yolu kullanıyoruz:

```
POST /runs/{run}/answers/{answer}/evidence   → izin + yükleme adresi
PUT  {upload_url}                            → baytlar (sunucu belleğinden geçmez)
POST /evidence/{id}/complete                 → sunucu özeti doğrular
GET  /evidence/{id}/url                      → 15 dk imzalı görüntüleme bağlantısı
```

İkinci ve üçüncü adım ayrı: istemcinin "yükledim" demesi yetmez,
sunucu depodaki baytların özetini **kendisi** hesaplar. Bu olmadan
kanıt bir beyandan ibaret kalır.

Görüntüleme uç noktası belirteçle çalışır, oturumla değil: `<img src>`
başlık gönderemez. Belirteç kısa ömürlü ve yalnızca o kanıt için.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response, status
from pydantic import BaseModel, Field

from talimatname.api.bagimliliklar import (
    kanit_servisi,
    organizasyon_servisi,
    yurutme_servisi,
)
from talimatname.api.guvenlik import Kullanici, sube_erisimi_zorunlu
from talimatname.domain.evidence import (
    FLAG_LABELS,
    MAX_BYTES,
    MAX_PER_ITEM,
    Evidence,
    EvidenceVariant,
)
from talimatname.services.evidence import EvidenceService
from talimatname.services.execution import ExecutionService
from talimatname.services.organization import OrganizationService

router = APIRouter(tags=["kanıt"])

Servis = Annotated[EvidenceService, Depends(kanit_servisi)]
OrgServis = Annotated[OrganizationService, Depends(organizasyon_servisi)]
YurutmeServis = Annotated[ExecutionService, Depends(yurutme_servisi)]


class KanitGirdisi(BaseModel):
    """Yükleme öncesi beyan. Dosyanın kendisi bu istekte **yok**."""

    item_id: UUID
    sha256: str = Field(min_length=64, max_length=64, description="Dosyanın SHA-256 özeti")
    content_type: Literal["image/jpeg", "image/png"]
    size_bytes: int = Field(gt=0, le=MAX_BYTES)
    from_gallery: bool = Field(
        default=False, description="Galeriden seçildiyse true; bayrak olarak saklanır"
    )
    captured_at: datetime | None = None
    device_reported_at: datetime | None = None
    device_id: UUID | None = None
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)


class BayrakCiktisi(BaseModel):
    code: str
    label: str


class KanitOzet(BaseModel):
    id: UUID
    run_id: UUID
    answer_id: UUID
    item_id: UUID
    status: Literal["pending", "stored", "stamped"]
    content_type: str
    size_bytes: int
    sha256: str
    created_at: datetime
    captured_at: datetime | None = None
    distance_meters: int | None = None
    stamped_at: datetime | None = Field(
        default=None, description="Görünür damgalı kopyanın üretildiği an (FR-0606)"
    )
    has_stamp: bool = Field(default=False, description="Damgalı kopya hazır mı")
    has_thumbnail: bool = Field(default=False, description="Küçük resim hazır mı")
    flags: list[BayrakCiktisi] = Field(
        default_factory=list, description="Bayrak suçlama değil, incelemeye çağrıdır"
    )


class YuklemeIzni(BaseModel):
    """Yükleme adresi ve belirteci.

    `upload_url` yerel adaptörde kendi uç noktamızdır ve **göreli**
    yazılır: istemci kendi kaynağına göre çözsün, ters vekil arkasında
    sunucunun iç adresi sızmasın. S3 uyumlu depoya geçilince burası ön
    imzalı kova adresi olur (mutlak) ve istemci kodu değişmez.
    """

    evidence: KanitOzet
    upload_url: str
    upload_method: Literal["PUT"] = "PUT"
    expires_in_minutes: int
    max_per_item: int = MAX_PER_ITEM


class GoruntulemeBaglantisi(BaseModel):
    url: str
    expires_in_minutes: int
    variant: EvidenceVariant = Field(default="raw", description="Bağlantının hangi kopyayı verdiği")


def _ozet(kanit: Evidence) -> KanitOzet:
    return KanitOzet(
        id=kanit.id,
        run_id=kanit.run_id,
        answer_id=kanit.answer_id,
        item_id=kanit.item_id,
        status=kanit.status,
        content_type=kanit.content_type,
        size_bytes=kanit.size_bytes,
        sha256=kanit.sha256,
        created_at=kanit.created_at,
        captured_at=kanit.captured_at,
        distance_meters=kanit.distance_meters,
        stamped_at=kanit.stamped_at,
        has_stamp=kanit.stamped_key is not None,
        has_thumbnail=kanit.thumbnail_key is not None,
        flags=[BayrakCiktisi(code=b, label=FLAG_LABELS[b]) for b in kanit.flags],
    )


@router.post(
    "/runs/{run_id}/answers/{answer_id}/evidence",
    status_code=status.HTTP_201_CREATED,
    summary="Kanıt yükleme izni al",
)
def kanit_baslat(
    run_id: UUID,
    answer_id: UUID,
    girdi: KanitGirdisi,
    servis: Servis,
    yurutme: YurutmeServis,
    org: OrgServis,
    kullanici: Kullanici,
    request: Request,
) -> YuklemeIzni:
    """Aynı SHA-256 hesapta daha önce kullanıldıysa 409 döner (FR-0614)."""
    sube_erisimi_zorunlu(kullanici, yurutme.view(run_id).run.branch_id, org)
    kanit, belirtec = servis.start(
        run_id=run_id,
        answer_id=answer_id,
        item_id=girdi.item_id,
        sha256=girdi.sha256,
        content_type=girdi.content_type,
        size_bytes=girdi.size_bytes,
        user_id=kullanici.id,
        device_id=girdi.device_id,
        from_gallery=girdi.from_gallery,
        captured_at=girdi.captured_at,
        device_reported_at=girdi.device_reported_at,
        latitude=girdi.latitude,
        longitude=girdi.longitude,
    )
    return YuklemeIzni(
        evidence=_ozet(kanit),
        upload_url=request.url_for("kanit_yukle", token=belirtec).path,
        expires_in_minutes=15,
    )


@router.put("/uploads/{token}", name="kanit_yukle", summary="Kanıt baytlarını yükle")
async def kanit_yukle(token: str, servis: Servis, request: Request) -> KanitOzet:
    """Yerel depolama adaptörünün yükleme ucu.

    Oturum **istemez**: yetki belirtecin kendisindedir ve o belirteç tek
    bir kanıt için 15 dakika geçerlidir. S3'e geçilince bu uç nokta
    kullanılmaz, istemci doğrudan kovaya yükler.
    """
    return _ozet(servis.receive(token, await request.body()))


@router.post("/evidence/{evidence_id}/complete", summary="Yüklemeyi doğrula ve tamamla")
def kanit_tamamla(evidence_id: UUID, servis: Servis) -> KanitOzet:
    """Sunucu depodaki baytların özetini hesaplar; tutmuyorsa reddeder."""
    return _ozet(servis.complete(evidence_id))


@router.get("/runs/{run_id}/evidence", summary="Çalıştırmanın kanıtları")
def calistirma_kanitlari(
    run_id: UUID,
    servis: Servis,
    yurutme: YurutmeServis,
    org: OrgServis,
    kullanici: Kullanici,
) -> list[KanitOzet]:
    sube_erisimi_zorunlu(kullanici, yurutme.view(run_id).run.branch_id, org)
    return [_ozet(k) for k in servis.for_run(run_id)]


@router.get("/evidence/{evidence_id}/url", summary="İmzalı görüntüleme bağlantısı")
def kanit_baglantisi(
    evidence_id: UUID,
    servis: Servis,
    org: OrgServis,
    kullanici: Kullanici,
    request: Request,
    variant: EvidenceVariant = "raw",
) -> GoruntulemeBaglantisi:
    """15 dakikalık bağlantı (FR-1305). Kapsam denetimi **burada** yapılır.

    `variant`: `thumbnail` ızgara için, `stamped` dışarı giden kopya,
    `raw` özeti tutulan dosya. İstenen kopya henüz üretilmediyse ham
    dosya döner (damgalama turlu bir iştir, ST-040).
    """
    kanit = servis.get(evidence_id)
    sube_erisimi_zorunlu(kullanici, kanit.branch_id, org)
    belirtec = servis.view_token(evidence_id, variant)
    return GoruntulemeBaglantisi(
        url=request.url_for("kanit_dosyasi", token=belirtec).path,
        expires_in_minutes=15,
        variant=variant,
    )


@router.get("/evidence/file/{token}", name="kanit_dosyasi", summary="Kanıt dosyası")
def kanit_dosyasi(token: str, servis: Servis) -> Response:
    """Belirteçle servis edilir: `<img src>` Authorization başlığı gönderemez."""
    kanit, baytlar = servis.read(token)
    return Response(
        content=baytlar,
        media_type=kanit.content_type,
        headers={"Cache-Control": "private, max-age=900"},
    )
