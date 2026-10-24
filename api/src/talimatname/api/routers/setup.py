"""Kurulum sihirbazı uç noktaları (ST-008; FR-1401, FR-0105, FR-0106).

```
GET  /setup                      → hangi adımdayım, ne eksik
PUT  /setup/brand                → adım 1: marka, saat dilimi, saatler
GET  /setup/branches/template    → doldurulacak Excel
POST /setup/branches/preview     → kuru çalıştırma: ne olacak, ne hatalı
POST /setup/branches/import      → uygula
POST /setup/complete             → sihirbazı kapat
```

**Önizleme ayrı bir uç nokta**: yöneticinin 40 şubelik bir dosyayı
yazmadan önce görmesi gerekiyor. Aynı dosya iki kez gönderiliyor;
bunun bedeli, yanlış dosyayı geri almaya çalışmaktan ucuz.

Hepsi **yönetici** işidir: kurulum hesabın kendisini şekillendiriyor.
"""

from __future__ import annotations

from datetime import datetime, time
from typing import Annotated

from fastapi import APIRouter, Depends, File, Response, UploadFile
from pydantic import BaseModel, Field

from talimatname.api.bagimliliklar import kurulum_servisi
from talimatname.api.guvenlik import Yonetici
from talimatname.domain.setup import (
    STEP_ORDER,
    AccountSettings,
    ImportReport,
    SetupProgress,
    SetupStep,
)
from talimatname.services.imports import error_report
from talimatname.services.setup import SetupService

router = APIRouter(tags=["kurulum"])

Servis = Annotated[SetupService, Depends(kurulum_servisi)]

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class SaatCiktisi(BaseModel):
    weekday: int = Field(description="0 Pazartesi … 6 Pazar")
    open_time: str | None = None
    close_time: str | None = None


class MarkaCiktisi(BaseModel):
    brand_name: str
    timezone: str
    logo_url: str | None = None
    hours: list[SaatCiktisi]
    completed_at: datetime | None = None


class AdimCiktisi(BaseModel):
    step: SetupStep
    label: str
    done: bool
    detail: str


class DurumCiktisi(BaseModel):
    """Sihirbazın durumu. `current` kaldığı yer (TC-004)."""

    steps: list[AdimCiktisi]
    current: SetupStep
    order: list[SetupStep] = Field(default_factory=lambda: list(STEP_ORDER))
    publishable: bool
    completed_at: datetime | None = None
    brand: MarkaCiktisi | None = None


class MarkaGirdisi(BaseModel):
    brand_name: str = Field(min_length=1, max_length=120)
    timezone: str = "Europe/Istanbul"
    open_time: time | None = Field(default=None, description="Tüm günler için varsayılan açılış")
    close_time: time | None = None
    closed_days: list[int] = Field(
        default_factory=list, description="Kapalı günler (0 Pazartesi … 6 Pazar)"
    )
    logo_url: str | None = None


class SatirHatasi(BaseModel):
    row: int
    field: str
    message: str


class YuklemeRaporu(BaseModel):
    """Satır bazlı sonuç (FR-0106). `rejected` ise hiçbir şey yazılmadı."""

    total: int
    accepted: int
    error_rows: int
    created: int
    updated: int
    rejected: bool
    errors: list[SatirHatasi]
    branches: list[str] = Field(default_factory=list, description="Kabul edilen şube kodları")


def _marka(ayar: AccountSettings | None) -> MarkaCiktisi | None:
    if ayar is None:
        return None
    return MarkaCiktisi(
        brand_name=ayar.brand_name,
        timezone=ayar.timezone,
        logo_url=ayar.logo_url,
        completed_at=ayar.completed_at,
        hours=[
            SaatCiktisi(
                weekday=gun,
                open_time=saat.open_time.isoformat() if saat else None,
                close_time=saat.close_time.isoformat() if saat else None,
            )
            for gun, saat in sorted(ayar.default_hours.items())
        ],
    )


def _durum(durum: SetupProgress, ayar: AccountSettings | None) -> DurumCiktisi:
    return DurumCiktisi(
        steps=[
            AdimCiktisi(step=a.step, label=a.label, done=a.done, detail=a.detail)
            for a in durum.steps
        ],
        current=durum.current,
        publishable=durum.publishable,
        completed_at=durum.completed_at,
        brand=_marka(ayar),
    )


def _rapor(rapor: ImportReport) -> YuklemeRaporu:
    return YuklemeRaporu(
        total=rapor.total,
        accepted=len(rapor.rows),
        error_rows=rapor.error_rows,
        created=rapor.created,
        updated=rapor.updated,
        rejected=rapor.rejected,
        errors=[SatirHatasi(row=h.row, field=h.field, message=h.message) for h in rapor.errors],
        branches=[satir.code for satir in rapor.rows],
    )


@router.get("/setup", summary="Kurulum durumu (kaldığı yer)")
def kurulum_durumu(servis: Servis, kullanici: Yonetici) -> DurumCiktisi:
    """Adımların durumu **veriden** okunur: sayaç tutulmuyor.

    Panelden elle şube ekleyen bir yöneticide sayaç ile gerçek
    ayrışırdı; böyle olunca sihirbaz her zaman doğruyu gösteriyor.
    """
    return _durum(servis.progress(), servis.settings())


@router.put("/setup/brand", summary="Adım 1 · marka ve varsayılan saatler")
def marka_kaydet(girdi: MarkaGirdisi, servis: Servis, kullanici: Yonetici) -> DurumCiktisi:
    servis.save_brand(
        brand_name=girdi.brand_name,
        timezone=girdi.timezone,
        open_time=girdi.open_time,
        close_time=girdi.close_time,
        closed_days=tuple(girdi.closed_days),
        logo_url=girdi.logo_url,
    )
    return _durum(servis.progress(), servis.settings())


@router.get(
    "/setup/branches/template",
    summary="Adım 2 · şube Excel şablonu",
    response_class=Response,
    responses={200: {"content": {XLSX: {}}, "description": "Excel şablonu"}},
)
def sube_sablonu(servis: Servis, kullanici: Yonetici) -> Response:
    """Doldurulacak dosya. Şablon sürümü dosyanın içinde yazılı (FR-0105)."""
    return Response(
        content=servis.template_file(),
        media_type=XLSX,
        headers={"Content-Disposition": 'attachment; filename="subeler.xlsx"'},
    )


@router.post("/setup/branches/preview", summary="Adım 2 · dosyayı yazmadan dene")
async def sube_onizleme(
    servis: Servis,
    kullanici: Yonetici,
    file: Annotated[UploadFile, File()],
) -> YuklemeRaporu:
    """Kuru çalıştırma: ne yazılacağını ve neyin hatalı olduğunu gösterir."""
    return _rapor(servis.import_branches(await file.read(), apply=False))


@router.post("/setup/branches/import", summary="Adım 2 · şubeleri yükle")
async def sube_yukle(
    servis: Servis,
    kullanici: Yonetici,
    file: Annotated[UploadFile, File()],
) -> YuklemeRaporu:
    """Aynı kodla gelen satır **günceller**: dosyayı ikinci kez yüklemek zarar vermez."""
    return _rapor(servis.import_branches(await file.read(), apply=True))


@router.post(
    "/setup/branches/error-report",
    summary="Adım 2 · hatalı satır raporu (Excel)",
    response_class=Response,
    responses={200: {"content": {XLSX: {}}, "description": "Hatalı satırlar"}},
)
async def hata_raporu(
    servis: Servis,
    kullanici: Yonetici,
    file: Annotated[UploadFile, File()],
) -> Response:
    """Hatalı satırları indirilebilir Excel olarak döner (FR-0106, UC-01/E2).

    Dosya yeniden gönderiliyor: raporu sunucuda saklamak, kullanıcının
    aynı dosyayı bir daha yollamasından daha çok soru doğururdu
    (ne kadar saklanacak, kim görebilecek).
    """
    rapor = servis.import_branches(await file.read(), apply=False, raise_on_reject=False)
    return Response(
        content=error_report(rapor),
        media_type=XLSX,
        headers={"Content-Disposition": 'attachment; filename="hatali-satirlar.xlsx"'},
    )


@router.post("/setup/complete", summary="Sihirbazı kapat")
def kurulum_tamamla(servis: Servis, kullanici: Yonetici) -> DurumCiktisi:
    servis.complete()
    return _durum(servis.progress(), servis.settings())


@router.post("/setup/reopen", summary="Sihirbazı yeniden aç")
def kurulum_yeniden_ac(servis: Servis, kullanici: Yonetici) -> DurumCiktisi:
    servis.reopen()
    return _durum(servis.progress(), servis.settings())
