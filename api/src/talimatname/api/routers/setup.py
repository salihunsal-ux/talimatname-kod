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

from dataclasses import replace
from datetime import datetime, time
from typing import Annotated, Literal
from uuid import UUID

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
from talimatname.domain.window import WindowRule
from talimatname.services.imports import error_report
from talimatname.services.library import LibraryTemplate
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


class KutuphaneSablonu(BaseModel):
    """Kütüphanedeki hazır şablon (ürün içeriği, hesap verisi değil)."""

    key: str
    name: str
    category: str
    summary: str
    item_count: int
    critical_count: int
    photo_count: int
    window: str = Field(description="Önerilen pencere, insan diliyle")


class SablonSecimi(BaseModel):
    key: str


class SablonSonucu(BaseModel):
    template_id: UUID
    version_id: UUID


class PlanOnerisi(BaseModel):
    """Şube saatlerinden türetilmiş öneri; kaydedilmeden gösterilir."""

    name: str
    template_version_id: UUID
    branch_ids: list[UUID]
    recurrence: str
    anchor_reference: Literal["open", "close"]
    anchor_offset_minutes: int
    duration_minutes: int
    tolerance_minutes: int
    window: str = Field(description="Pencerenin insan diliyle özeti")


class PlanOnayi(BaseModel):
    """Hepsi isteğe bağlı: boş gövde öneriyi olduğu gibi kaydeder."""

    version_id: UUID | None = None
    name: str | None = None
    branch_ids: list[UUID] | None = None
    duration_minutes: int | None = None
    tolerance_minutes: int | None = None


class YayinSonucu(BaseModel):
    """Yayın özeti. **Hazır** çalıştırma sayısı, "yeni yazılan" değil:
    plan kaydedilirken üretim zaten koşuyor ve ikinci kez yayınlamak
    sıfır gösterirdi."""

    runs_ready: int
    first_window: datetime | None = None
    status: DurumCiktisi


def _pencere_ozeti(kural: WindowRule) -> str:
    """Planın penceresini insan diliyle: "kapanıştan 60 dk önce…"."""
    assert kural.anchor is not None
    yon = "açılış" if kural.anchor.reference == "open" else "kapanış"
    dakika = abs(kural.anchor.offset_minutes)
    once = "önce" if kural.anchor.offset_minutes < 0 else "sonra"
    return (
        f"Günlük · şube {yon} saatinden {dakika} dk {once} başlar · "
        f"{kural.duration_minutes} dk pencere · {kural.tolerance_minutes} dk tolerans"
    )


def _pencere_metni(sablon: LibraryTemplate) -> str:
    yon = "açılış" if sablon.plan.anchor.reference == "open" else "kapanış"
    dakika = abs(sablon.plan.anchor.offset_minutes)
    once = "önce" if sablon.plan.anchor.offset_minutes < 0 else "sonra"
    return (
        f"Günlük · şube {yon} saatinden {dakika} dk {once} başlar · "
        f"{sablon.plan.duration_minutes} dk pencere · "
        f"{sablon.plan.tolerance_minutes} dk tolerans"
    )


@router.get("/setup/library", summary="Adım 3 · hazır şablonlar")
def kutuphane(servis: Servis, kullanici: Yonetici) -> list[KutuphaneSablonu]:
    """Ürün kütüphanesi (02-urun/07). Seçilen şablon hesaba kopyalanır."""
    return [
        KutuphaneSablonu(
            key=sablon.key,
            name=sablon.name,
            category=sablon.category,
            summary=sablon.summary,
            item_count=sablon.item_count,
            critical_count=sablon.critical_count,
            photo_count=sablon.photo_count,
            window=_pencere_metni(sablon),
        )
        for sablon in servis.library()
    ]


@router.post("/setup/template", summary="Adım 3 · şablonu hesaba kopyala")
def sablon_kopyala(girdi: SablonSecimi, servis: Servis, kullanici: Yonetici) -> SablonSonucu:
    sablon_id, surum_id = servis.use_template(girdi.key)
    return SablonSonucu(template_id=sablon_id, version_id=surum_id)


@router.get("/setup/plan-proposal", summary="Adım 4 · plan önerisi")
def plan_onerisi(
    servis: Servis,
    kullanici: Yonetici,
    version_id: UUID | None = None,
) -> PlanOnerisi:
    """Şube çalışma saatinden türetilir; kaydedilmez, gösterilir.

    `version_id` verilmezse **planı olmayan ilk yayınlanmış sürüm**
    seçilir: sihirbaz "hangi şablonu seçmiştim" diye durum tutmuyor.
    """
    plan = servis.plan_proposal(version_id)
    assert plan.rule.anchor is not None
    return PlanOnerisi(
        name=plan.name,
        template_version_id=plan.template_version_id,
        branch_ids=list(plan.branch_ids),
        recurrence=plan.rule.recurrence,
        anchor_reference=plan.rule.anchor.reference,
        anchor_offset_minutes=plan.rule.anchor.offset_minutes,
        duration_minutes=plan.rule.duration_minutes,
        tolerance_minutes=plan.rule.tolerance_minutes,
        window=_pencere_ozeti(plan.rule),
    )


@router.post("/setup/plan", summary="Adım 4 · planı oluştur")
def plan_olustur(girdi: PlanOnayi, servis: Servis, kullanici: Yonetici) -> DurumCiktisi:
    """Öneriyi (yöneticinin düzenlediği hâliyle) kaydeder."""
    oneri = servis.plan_proposal(girdi.version_id)
    plan = replace(
        oneri,
        name=girdi.name or oneri.name,
        branch_ids=tuple(girdi.branch_ids) if girdi.branch_ids else oneri.branch_ids,
        rule=replace(
            oneri.rule,
            duration_minutes=girdi.duration_minutes or oneri.rule.duration_minutes,
            tolerance_minutes=(
                girdi.tolerance_minutes
                if girdi.tolerance_minutes is not None
                else oneri.rule.tolerance_minutes
            ),
        ),
    ).validated()
    servis.create_plan(plan)
    return _durum(servis.progress(), servis.settings())


@router.post("/setup/publish", summary="Yayınla: çalıştırmaları üret ve sihirbazı kapat")
def yayinla(servis: Servis, kullanici: Yonetici) -> YayinSonucu:
    """Üretim idempotent: düğmeye iki kez basmak ikinci pencere açmaz."""
    _, sonuc = servis.publish()
    return YayinSonucu(
        runs_ready=sonuc.runs_ready,
        first_window=sonuc.first_window,
        status=_durum(servis.progress(), servis.settings()),
    )


@router.post("/setup/complete", summary="Sihirbazı kapat")
def kurulum_tamamla(servis: Servis, kullanici: Yonetici) -> DurumCiktisi:
    servis.complete()
    return _durum(servis.progress(), servis.settings())


@router.post("/setup/reopen", summary="Sihirbazı yeniden aç")
def kurulum_yeniden_ac(servis: Servis, kullanici: Yonetici) -> DurumCiktisi:
    servis.reopen()
    return _durum(servis.progress(), servis.settings())
