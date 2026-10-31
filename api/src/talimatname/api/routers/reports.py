"""Rapor uç noktaları (ST-088, ST-145, ST-092; FR-1207, FR-1208, FR-1220, FR-1214).

```
GET /reports/monthly?year&month      → ayın tek sayfası, şube kırılımı
GET /reports/monthly.pdf?year&month  → aynı sayfa, kâğıda (FR-1220)
GET /reports/measurements?from&to    → ölçüm günlüğü (sıcaklık, sayı)
GET /reports/measurements.pdf        → dönem PDF'i (FR-1214)
GET /reports/gallery?from&to         → kanıt ızgarası
```

Hepsi **kapsamla süzülür**: bölge müdürü bölgesini, şube müdürü
şubesini görür. Kapsam belirteçten değil kullanıcıdan okunuyor.

PDF'ler ekranla **aynı** servis çağrısını kullanıyor: kâğıt kendi
sorgusunu yazsaydı iki çıktı zamanla ayrışırdı — denetimde elde
ekrandan farklı bir kâğıt olurdu.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, Field

from talimatname.api.bagimliliklar import (
    izi_servisi,
    kurulum_servisi,
    organizasyon_servisi,
    rapor_servisi,
)
from talimatname.api.guvenlik import Kullanici, erisilebilir_sube_idleri
from talimatname.domain.evidence import FLAG_LABELS
from talimatname.domain.reports import Counters, MonthlySummary
from talimatname.services.audit import AuditService
from talimatname.services.organization import OrganizationService
from talimatname.services.pdf import (
    Brand,
    measurements_code,
    measurements_pdf,
    monthly_code,
    monthly_pdf,
)
from talimatname.services.reports import MeasurementSeries, ReportService
from talimatname.services.setup import SetupService

router = APIRouter(tags=["rapor"])

Servis = Annotated[ReportService, Depends(rapor_servisi)]
OrgServis = Annotated[OrganizationService, Depends(organizasyon_servisi)]
KurulumServis = Annotated[SetupService, Depends(kurulum_servisi)]
Iz = Annotated[AuditService, Depends(izi_servisi)]

AY_ADLARI = (
    "Ocak",
    "Şubat",
    "Mart",
    "Nisan",
    "Mayıs",
    "Haziran",
    "Temmuz",
    "Ağustos",
    "Eylül",
    "Ekim",
    "Kasım",
    "Aralık",
)


class SayaclarCiktisi(BaseModel):
    total: int
    on_time: int
    late: int
    missed: int
    cancelled: int
    open: int
    failed: int
    not_done_items: int
    closed: int
    on_time_percent: int | None = Field(
        default=None,
        description="Kapanmış çalıştırma yoksa null: sıfır 'hiçbiri zamanında değil' demek olurdu",
    )


class SubeOzeti(BaseModel):
    branch_id: UUID
    branch_code: str
    branch_name: str
    counters: SayaclarCiktisi


class AylikOzet(BaseModel):
    year: int
    month: int
    month_name: str
    first_day: date
    last_day: date
    counters: SayaclarCiktisi
    branches: list[SubeOzeti] = Field(
        description="Zamanındalığı en düşük şube önce; ölçülemeyenler sonda"
    )


class OlcumNoktasi(BaseModel):
    run_id: UUID
    branch_id: UUID
    measured_at: datetime | None = None
    value: float
    out_of_range: bool


class OlcumSerisi(BaseModel):
    item_id: UUID
    item_title: str
    unit: str | None = None
    min_value: float | None = None
    max_value: float | None = None
    out_of_range_count: int
    points: list[OlcumNoktasi]


class GaleriKanidi(BaseModel):
    id: UUID
    run_id: UUID
    branch_id: UUID
    item_id: UUID
    created_at: datetime
    captured_at: datetime | None = None
    flags: list[str] = Field(default_factory=list, description="Bayrakların Türkçe etiketleri")


def _sayaclar(sayac: Counters) -> SayaclarCiktisi:
    return SayaclarCiktisi(
        total=sayac.total,
        on_time=sayac.on_time,
        late=sayac.late,
        missed=sayac.missed,
        cancelled=sayac.cancelled,
        open=sayac.open,
        failed=sayac.failed,
        not_done_items=sayac.not_done_items,
        closed=sayac.closed,
        on_time_percent=sayac.on_time_percent,
    )


def _ozet(ozet: MonthlySummary) -> AylikOzet:
    return AylikOzet(
        year=ozet.year,
        month=ozet.month,
        month_name=AY_ADLARI[ozet.month - 1],
        first_day=ozet.first_day,
        last_day=ozet.last_day,
        counters=_sayaclar(ozet.counters),
        branches=[
            SubeOzeti(
                branch_id=sube.branch_id,
                branch_code=sube.branch_code,
                branch_name=sube.branch_name,
                counters=_sayaclar(sube.counters),
            )
            for sube in ozet.worst_branches
        ],
    )


def _seri(seri: MeasurementSeries) -> OlcumSerisi:
    return OlcumSerisi(
        item_id=seri.item_id,
        item_title=seri.item_title,
        unit=seri.unit,
        min_value=seri.min_value,
        max_value=seri.max_value,
        out_of_range_count=seri.out_of_range_count,
        points=[
            OlcumNoktasi(
                run_id=nokta.run_id,
                branch_id=nokta.branch_id,
                measured_at=nokta.measured_at,
                value=nokta.value,
                out_of_range=nokta.out_of_range,
            )
            for nokta in seri.points
        ],
    )


@router.get("/reports/monthly", summary="Aylık tek sayfa özet (FR-1220)")
def aylik_ozet(
    servis: Servis,
    org: OrgServis,
    kullanici: Kullanici,
    year: Annotated[int, Query(ge=2020, le=2100)],
    month: Annotated[int, Query(ge=1, le=12)],
) -> AylikOzet:
    """Ayın zamanında / geç / kaçırıldı dağılımı ve şube kırılımı.

    Açık pencereler yüzdeye girmez: ayın ortasında henüz olmamış işi
    kayıp saymak, raporu yanlış okutur.
    """
    return _ozet(servis.monthly(year, month, branch_ids=erisilebilir_sube_idleri(kullanici, org)))


@router.get("/reports/measurements", summary="Ölçüm günlüğü (FR-1207)")
def olcum_gunlugu(
    servis: Servis,
    org: OrgServis,
    kullanici: Kullanici,
    first_day: date,
    last_day: date,
    only_out_of_range: bool = False,
) -> list[OlcumSerisi]:
    """Sıcaklık ve sayı maddelerinin zaman serisi; aralık dışı işaretli.

    Aralık dışı ölçümü olan seriler **önce** geliyor: denetim
    konuşması oradan başlıyor.
    """
    seriler = servis.measurements(
        first_day=first_day,
        last_day=last_day,
        branch_ids=erisilebilir_sube_idleri(kullanici, org),
        only_out_of_range=only_out_of_range,
    )
    return [_seri(seri) for seri in seriler]


@router.get("/reports/gallery", summary="Kanıt galerisi (FR-1208)")
def kanit_galerisi(
    servis: Servis,
    org: OrgServis,
    kullanici: Kullanici,
    first_day: date,
    last_day: date,
    only_flagged: bool = False,
) -> list[GaleriKanidi]:
    """Şube ve tarih süzgeciyle doğrulanmış kanıtlar, yenisi önce.

    Görsellerin kendisi imzalı bağlantıyla geliyor
    (`GET /evidence/{id}/url`); burada yalnızca kayıt listesi var.
    """
    kanitlar = servis.gallery(
        first_day=first_day,
        last_day=last_day,
        branch_ids=erisilebilir_sube_idleri(kullanici, org),
        only_flagged=only_flagged,
    )
    return [
        GaleriKanidi(
            id=kanit.id,
            run_id=kanit.run_id,
            branch_id=kanit.branch_id,
            item_id=kanit.item_id,
            created_at=kanit.created_at,
            captured_at=kanit.captured_at,
            flags=[FLAG_LABELS[b] for b in kanit.flags],
        )
        for kanit in kanitlar
    ]


# --- PDF çıktıları (FR-1220, FR-1214) ---------------------------------


def _marka(kurulum: KurulumServis) -> Brand:
    """Kâğıdın üstündeki hesap adı ve saat dilimi.

    Sihirbaz bitmemişse marka adı henüz yok: rapor üretilir ama
    kâğıtta ürünün adı görünür. Üretmemek daha kötü olurdu — kurulumun
    ortasında da rapor alınabilmeli.
    """
    ayar = kurulum.settings()
    if ayar is None:
        return Brand(name="Talimatname")
    return Brand(name=ayar.brand_name, timezone=ayar.timezone)


def _sube_kodlari(org: OrgServis) -> dict[UUID, str]:
    """Ölçüm satırında şube **kodu** görünüyor: kâğıtta yer dar.

    Kapalı şubeler de alınıyor: geçmiş dönemin ölçümü kapanmış bir
    şubeye ait olabilir ve kod yerine `—` basmak kaydı okunamaz kılar.
    """
    return {
        sube.id: sube.code for bolge in org.tree(include_inactive=True) for sube in bolge.branches
    }


def _belge_kodu(iz: Iz, *, tur: str, donem: str, icerik_kodu: str) -> str | None:
    """Raporu olay günlüğüne yazar ve kâğıttaki kodu döner (FR-1218).

    Kâğıttaki kod, **olayın zincir özeti**: doğrulama sayfası koda
    göre kaydı bulacak (v1.x). Kaydın içinde raporun içerik kodu da
    duruyor, böylece "hangi veri dökülmüş" sorusu da cevaplanıyor.

    Günlük yazılamazsa None dönüyor: rapor yine üretiliyor ama
    kâğıtta kodun zincire bağlı **olmadığı** yazıyor. Bağlıymış gibi
    yazmak, olmayan bir güvence vermek olurdu.
    """
    olay = iz.record(
        "rapor.uretildi",
        object_type="rapor",
        after={"tur": tur, "donem": donem, "icerik": icerik_kodu},
    )
    if olay is None:
        return None
    ozet = olay.hash[:12].upper()
    return f"{ozet[:4]}-{ozet[4:8]}-{ozet[8:]}"


def _pdf(icerik: bytes, *, dosya_adi: str) -> Response:
    return Response(
        content=icerik,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{dosya_adi}"'},
    )


@router.get(
    "/reports/monthly.pdf",
    summary="Aylık özetin PDF'i (FR-1220)",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}}, "description": "PDF"}},
)
def aylik_ozet_pdf(
    servis: Servis,
    org: OrgServis,
    kurulum: KurulumServis,
    iz: Iz,
    kullanici: Kullanici,
    year: Annotated[int, Query(ge=2020, le=2100)],
    month: Annotated[int, Query(ge=1, le=12)],
) -> Response:
    ozet = servis.monthly(year, month, branch_ids=erisilebilir_sube_idleri(kullanici, org))
    marka = _marka(kurulum)
    kod = _belge_kodu(
        iz,
        tur="aylik-ozet",
        donem=f"{year}-{month:02d}",
        icerik_kodu=monthly_code(ozet, brand=marka),
    )
    icerik = monthly_pdf(
        ozet,
        brand=marka,
        generated_at=datetime.now(UTC),
        generated_by=kullanici.full_name,
        code=kod,
    )
    return _pdf(icerik, dosya_adi=f"talimatname-{year}-{month:02d}-aylik-ozet.pdf")


@router.get(
    "/reports/measurements.pdf",
    summary="Ölçüm günlüğünün PDF'i (FR-1214)",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}}, "description": "PDF"}},
)
def olcum_gunlugu_pdf(
    servis: Servis,
    org: OrgServis,
    kurulum: KurulumServis,
    iz: Iz,
    kullanici: Kullanici,
    first_day: date,
    last_day: date,
    only_out_of_range: bool = False,
) -> Response:
    """Soğuk zincir denetiminin istediği kâğıt: ne, nerede, ne zaman, kaç."""
    seriler = servis.measurements(
        first_day=first_day,
        last_day=last_day,
        branch_ids=erisilebilir_sube_idleri(kullanici, org),
        only_out_of_range=only_out_of_range,
    )
    marka = _marka(kurulum)
    kod = _belge_kodu(
        iz,
        tur="olcum-gunlugu",
        donem=f"{first_day:%Y-%m-%d}/{last_day:%Y-%m-%d}",
        icerik_kodu=measurements_code(seriler, brand=marka, first_day=first_day, last_day=last_day),
    )
    icerik = measurements_pdf(
        seriler,
        brand=marka,
        first_day=first_day,
        last_day=last_day,
        branch_codes=_sube_kodlari(org),
        generated_at=datetime.now(UTC),
        generated_by=kullanici.full_name,
        code=kod,
    )
    return _pdf(
        icerik,
        dosya_adi=f"talimatname-olcum-gunlugu-{first_day:%Y%m%d}-{last_day:%Y%m%d}.pdf",
    )
