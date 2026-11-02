"""Arka plan çıktıları: liste ve indirme (ST-102; FR-1217).

```
GET /reports/exports                 → kendi çıktı isteklerim
GET /reports/exports/{id}            → tek işin durumu
GET /reports/exports/{id}/dosya      → hazır PDF
```

Dönem PDF uç noktaları eşiği geçince **202** ile bir iş kaydı dönüyor
(bkz. `routers/reports`); panel bu listeden takip ediyor, hazır olunca
da bildirim düşüyor.

**Yalnızca isteyen indirir.** Çıktı, isteyenin kapsamıyla üretildi;
başkasına vermek o kapsamı delmek olurdu. Paylaşılabilir bağlantı ayrı
bir iş (FR-1216, v1.1).
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, Field

from talimatname.api.bagimliliklar import cikti_servisi
from talimatname.api.guvenlik import Mudur
from talimatname.domain.exports import ExportJob, file_name
from talimatname.services.export_jobs import ExportJobService

router = APIRouter(tags=["rapor"])

Servis = Annotated[ExportJobService, Depends(cikti_servisi)]


class CiktiIsi(BaseModel):
    """Bir çıktı isteğinin durumu."""

    id: UUID
    kind: str = Field(description="aylik-ozet | olcum-gunlugu")
    kind_label: str
    params: dict[str, str] = Field(description="Dönem bilgisi: yıl/ay ya da ilk/son gün")
    state: str = Field(description="queued | running | ready | failed")
    state_label: str
    run_count: int = Field(description="Kapsadığı çalıştırma sayısı: arka plana düşme sebebi")
    requested_at: datetime
    finished_at: datetime | None = None
    size_bytes: int | None = None
    document_code: str | None = Field(
        default=None, description="Kâğıttaki belge kodu (FR-1218); doğrulama sayfasında sorulur"
    )
    error_code: str | None = Field(
        default=None, description="Düştüyse sebebin kısa karşılığı — gizlenmiyor"
    )
    downloadable: bool


def cikti_ciktisi(is_kaydi: ExportJob) -> CiktiIsi:
    return CiktiIsi(
        id=is_kaydi.id,
        kind=is_kaydi.kind,
        kind_label=is_kaydi.label,
        params=is_kaydi.params,
        state=is_kaydi.state,
        state_label=is_kaydi.state_label,
        run_count=is_kaydi.run_count,
        requested_at=is_kaydi.requested_at,
        finished_at=is_kaydi.finished_at,
        size_bytes=is_kaydi.size_bytes,
        document_code=is_kaydi.document_code,
        error_code=is_kaydi.error_code,
        downloadable=is_kaydi.downloadable,
    )


@router.get("/reports/exports", summary="Arka plan çıktılarım (FR-1217)")
def ciktilarim(servis: Servis, kullanici: Mudur) -> list[CiktiIsi]:
    """Yalnızca **kendi** istekleri: çıktı isteyenin kapsamıyla üretiliyor."""
    return [cikti_ciktisi(i) for i in servis.jobs_for(kullanici.id)]


@router.get("/reports/exports/{job_id}", summary="Çıktı isteğinin durumu")
def cikti(job_id: UUID, servis: Servis, kullanici: Mudur) -> CiktiIsi:
    return cikti_ciktisi(servis.job_for(kullanici.id, job_id))


@router.get(
    "/reports/exports/{job_id}/dosya",
    summary="Hazır çıktıyı indir",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}}, "description": "PDF"}},
)
def cikti_dosyasi(job_id: UUID, servis: Servis, kullanici: Mudur) -> Response:
    is_kaydi, icerik = servis.file(kullanici.id, job_id)
    return Response(
        content=icerik,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{file_name(is_kaydi)}"'},
    )
