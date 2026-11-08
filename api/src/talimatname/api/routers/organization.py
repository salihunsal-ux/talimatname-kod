"""Şube ve bölge uç noktaları (ST-002, ST-007; FR-0102…0104)."""

from __future__ import annotations

from datetime import time
from typing import Annotated, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field

from talimatname.api.bagimliliklar import organizasyon_servisi
from talimatname.api.guvenlik import Gozlemci, Yonetici, sube_erisimi_zorunlu
from talimatname.domain.organization import WEEKDAYS, Branch
from talimatname.domain.users import can_access
from talimatname.domain.window import BusinessHours
from talimatname.services.organization import OrganizationService

router = APIRouter(tags=["organizasyon"])

Servis = Annotated[OrganizationService, Depends(organizasyon_servisi)]

GUN_ADLARI = ("Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar")


class CalismaSaati(BaseModel):
    """Bir günün açılış/kapanışı. `null` gün = kapalı."""

    weekday: int = Field(ge=0, le=6, description="0 = Pazartesi")
    weekday_name: str
    open_time: time | None = None
    close_time: time | None = None

    @property
    def closed(self) -> bool:
        return self.open_time is None


class SubeOzet(BaseModel):
    id: UUID
    code: str
    name: str
    status: Literal["active", "inactive"]
    region_id: UUID | None = None
    timezone: str
    open_days: int = Field(description="Haftada açık gün sayısı")


class SubeDetay(SubeOzet):
    address: str | None = None
    business_hours: list[CalismaSaati]
    stations: list[IstasyonOzet]


class IstasyonOzet(BaseModel):
    id: UUID
    name: str
    kind: str


class BolgeDugumu(BaseModel):
    id: UUID | None
    name: str
    branches: list[SubeOzet]


class SubeGirdisi(BaseModel):
    """Şube oluşturma/güncelleme gövdesi.

    Çalışma saatleri verilmezse 08:00–23:00 her gün uygulanır: kurulum
    sihirbazının varsayılanı (FR-1401); şube sonradan düzeltir.
    """

    code: str = Field(min_length=2, max_length=16, examples=["KDK"])
    name: str = Field(min_length=1, max_length=80, examples=["Kadıköy"])
    timezone: str = "Europe/Istanbul"
    region_id: UUID | None = None
    address: str | None = None
    business_hours: list[CalismaSaati] | None = None


def _saatler(girdi: list[CalismaSaati] | None) -> dict[int, BusinessHours | None]:
    if girdi is None:
        return {gun: BusinessHours(time(8, 0), time(23, 0)) for gun in WEEKDAYS}
    sonuc: dict[int, BusinessHours | None] = dict.fromkeys(WEEKDAYS)
    for satir in girdi:
        if satir.open_time is not None and satir.close_time is not None:
            sonuc[satir.weekday] = BusinessHours(satir.open_time, satir.close_time)
    return sonuc


def _saat_listesi(sube: Branch) -> list[CalismaSaati]:
    return [
        CalismaSaati(
            weekday=gun,
            weekday_name=GUN_ADLARI[gun],
            open_time=saat.open_time if saat else None,
            close_time=saat.close_time if saat else None,
        )
        for gun, saat in sorted(sube.business_hours.items())
    ]


def _ozet(sube: Branch) -> SubeOzet:
    return SubeOzet(
        id=sube.id,
        code=sube.code,
        name=sube.name,
        status=sube.status,
        region_id=sube.region_id,
        timezone=sube.timezone,
        open_days=sube.open_days,
    )


@router.get("/branches", summary="Bölge → şube ağacı")
def sube_agaci(
    servis: Servis, kullanici: Gozlemci, include_inactive: bool = False
) -> list[BolgeDugumu]:
    """Yalnızca kullanıcının kapsamındaki şubeler (FR-0205).

    Boş kalan bölge düğümü gösterilmez: bölge adı da bir bilgidir.
    """
    agac = []
    for dugum in servis.tree(include_inactive=include_inactive):
        gorunur = [s for s in dugum.branches if can_access(kullanici, s)]
        if gorunur:
            agac.append(
                BolgeDugumu(id=dugum.id, name=dugum.name, branches=[_ozet(s) for s in gorunur])
            )
    return agac


@router.get("/branches/{branch_id}", summary="Şube detayı")
def sube_detayi(branch_id: UUID, servis: Servis, kullanici: Gozlemci) -> SubeDetay:
    sube = sube_erisimi_zorunlu(kullanici, branch_id, servis)
    return SubeDetay(
        **_ozet(sube).model_dump(),
        address=sube.address,
        business_hours=_saat_listesi(sube),
        stations=[
            IstasyonOzet(id=i.id, name=i.name, kind=i.kind) for i in servis.stations(branch_id)
        ],
    )


@router.post("/branches", status_code=status.HTTP_201_CREATED, summary="Şube ekle")
def sube_ekle(girdi: SubeGirdisi, servis: Servis, _: Yonetici) -> SubeOzet:
    sube = servis.create_branch(
        Branch(
            id=uuid4(),
            code=girdi.code,
            name=girdi.name,
            timezone=girdi.timezone,
            business_hours=_saatler(girdi.business_hours),
            region_id=girdi.region_id,
            address=girdi.address,
        )
    )
    return _ozet(sube)


@router.patch("/branches/{branch_id}", summary="Şube güncelle")
def sube_guncelle(branch_id: UUID, girdi: SubeGirdisi, servis: Servis, _: Yonetici) -> SubeOzet:
    sube = servis.update_branch(
        branch_id,
        code=girdi.code,
        name=girdi.name,
        timezone=girdi.timezone,
        business_hours=_saatler(girdi.business_hours),
        region_id=girdi.region_id,
        address=girdi.address,
    )
    return _ozet(sube)


@router.post("/branches/{branch_id}/deactivate", summary="Şubeyi pasifleştir")
def sube_pasiflestir(branch_id: UUID, servis: Servis, _: Yonetici) -> SubeOzet:
    """Silme değil: geçmiş kayıtlar ve kanıtlar durur (BR-22)."""
    return _ozet(servis.set_status(branch_id, "inactive"))


@router.post("/branches/{branch_id}/activate", summary="Şubeyi yeniden aktif et")
def sube_aktif_et(branch_id: UUID, servis: Servis, _: Yonetici) -> SubeOzet:
    return _ozet(servis.set_status(branch_id, "active"))
