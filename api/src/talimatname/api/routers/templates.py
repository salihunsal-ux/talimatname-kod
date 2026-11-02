"""Şablon uç noktaları (ST-014, ST-016, ST-017; FR-0301…0312)."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field

from talimatname.api.bagimliliklar import sablon_servisi
from talimatname.api.guvenlik import Kullanici, Mudur, Yonetici
from talimatname.domain.templates import (
    ITEM_TYPE_LABELS,
    ChoiceOption,
    Item,
    ItemType,
    Section,
    TemplateVersion,
    VersionSettings,
)
from talimatname.services.templates import TemplateService

router = APIRouter(tags=["şablon"])

Servis = Annotated[TemplateService, Depends(sablon_servisi)]


class SecenekGirdisi(BaseModel):
    label: str = Field(min_length=1, max_length=60)
    passing: bool = True


class MaddeGirdisi(BaseModel):
    id: UUID | None = Field(default=None, description="Yoksa yeni madde üretilir")
    type: ItemType
    title: str = Field(min_length=1, max_length=160)
    hint: str | None = None
    required: bool = True
    photo_required: bool = False
    critical: bool = False
    options: list[SecenekGirdisi] = []
    min_value: float | None = None
    max_value: float | None = None
    unit: str | None = None


class BolumGirdisi(BaseModel):
    id: UUID | None = None
    title: str = Field(min_length=1, max_length=80)
    items: list[MaddeGirdisi] = []


class TaslakGirdisi(BaseModel):
    sections: list[BolumGirdisi]
    camera_only: bool = True


class SablonGirdisi(BaseModel):
    name: str = Field(min_length=1, max_length=80, examples=["Kapanış (kafe)"])
    category: str | None = None


class MaddeCiktisi(MaddeGirdisi):
    id: UUID
    type_label: str
    scored: bool


class BolumCiktisi(BaseModel):
    id: UUID
    order: int
    title: str
    items: list[MaddeCiktisi]


class SurumOzet(BaseModel):
    id: UUID
    version_no: int
    status: Literal["draft", "published", "archived"]
    published_at: datetime | None = None
    scored_item_count: int
    critical_item_count: int
    photo_item_count: int


class YayinSorunu(BaseModel):
    where: str
    message: str


class SurumDetay(SurumOzet):
    template_id: UUID
    template_name: str
    camera_only: bool
    sections: list[BolumCiktisi]
    publish_issues: list[YayinSorunu]


class SablonOzet(BaseModel):
    id: UUID
    name: str
    category: str | None = None
    versions: list[SurumOzet]


def _madde_ciktisi(madde: Item) -> MaddeCiktisi:
    return MaddeCiktisi(
        id=madde.id,
        type=madde.type,
        type_label=ITEM_TYPE_LABELS[madde.type],
        title=madde.title,
        hint=madde.hint,
        required=madde.required,
        photo_required=madde.photo_required,
        critical=madde.critical,
        options=[SecenekGirdisi(label=o.label, passing=o.passing) for o in madde.options],
        min_value=madde.min_value,
        max_value=madde.max_value,
        unit=madde.unit,
        scored=madde.scored,
    )


def _surum_ozet(surum: TemplateVersion) -> SurumOzet:
    return SurumOzet(
        id=surum.id,
        version_no=surum.version_no,
        status=surum.status,
        published_at=surum.published_at,
        scored_item_count=surum.scored_item_count,
        critical_item_count=surum.critical_item_count,
        photo_item_count=surum.photo_item_count,
    )


def _surum_detay(surum: TemplateVersion, template_name: str) -> SurumDetay:
    return SurumDetay(
        **_surum_ozet(surum).model_dump(),
        template_id=surum.template_id,
        template_name=template_name,
        camera_only=surum.settings.camera_only,
        sections=[
            BolumCiktisi(
                id=bolum.id,
                order=bolum.order,
                title=bolum.title,
                items=[_madde_ciktisi(m) for m in bolum.items],
            )
            for bolum in surum.sections
        ],
        publish_issues=[
            YayinSorunu(where=s.where, message=s.message) for s in surum.publish_issues()
        ],
    )


def _bolumler(girdi: list[BolumGirdisi]) -> tuple[Section, ...]:
    return tuple(
        Section(
            id=bolum.id or uuid4(),
            order=sira,
            title=bolum.title,
            items=tuple(
                Item(
                    id=madde.id or uuid4(),
                    order=madde_sira,
                    type=madde.type,
                    title=madde.title,
                    hint=madde.hint,
                    required=madde.required,
                    photo_required=madde.photo_required,
                    critical=madde.critical,
                    options=tuple(
                        ChoiceOption(label=o.label, passing=o.passing) for o in madde.options
                    ),
                    min_value=madde.min_value,
                    max_value=madde.max_value,
                    unit=madde.unit,
                )
                for madde_sira, madde in enumerate(bolum.items, start=1)
            ),
        )
        for sira, bolum in enumerate(girdi, start=1)
    )


@router.get("/templates", summary="Şablon listesi (sürümleriyle)")
def sablon_listesi(servis: Servis, _: Mudur) -> list[SablonOzet]:
    return [
        SablonOzet(
            id=sablon.id,
            name=sablon.name,
            category=sablon.category,
            versions=[_surum_ozet(s) for s in surumler],
        )
        for sablon, surumler in servis.list_templates()
    ]


# Sürüm detayı personele de açık: çalıştırmayı dolduran kişi madde
# listesini okumak zorunda (senk akışı). Matristeki "Şablon –" satırı
# kütüphaneyi yönetmekle ilgili; kütüphane listesi (/templates) kapalı.
@router.get("/template-versions/{version_id}", summary="Sürüm detayı")
def surum_detayi(version_id: UUID, servis: Servis, _: Kullanici) -> SurumDetay:
    surum = servis.version(version_id)
    return _surum_detay(surum, servis.get(surum.template_id).name)


@router.post("/templates", status_code=status.HTTP_201_CREATED, summary="Şablon oluştur")
def sablon_olustur(girdi: SablonGirdisi, servis: Servis, _: Yonetici) -> SurumDetay:
    """Yeni şablon boş bir **taslak** sürümle açılır (FR-0301)."""
    sablon, taslak = servis.create(girdi.name, girdi.category)
    return _surum_detay(taslak, sablon.name)


@router.put("/template-versions/{version_id}", summary="Taslağı kaydet")
def taslak_kaydet(
    version_id: UUID, girdi: TaslakGirdisi, servis: Servis, _: Yonetici
) -> SurumDetay:
    surum = servis.save_draft(
        version_id,
        _bolumler(girdi.sections),
        VersionSettings(camera_only=girdi.camera_only),
    )
    return _surum_detay(surum, servis.get(surum.template_id).name)


@router.post("/templates/{template_id}/new-draft", summary="Yayından yeni taslak türet")
def yeni_taslak(template_id: UUID, servis: Servis, _: Yonetici) -> SurumDetay:
    """Yayınlanmış sürüm değişmez; düzenleme yeni taslakta sürer (FR-0301)."""
    taslak = servis.new_draft(template_id)
    return _surum_detay(taslak, servis.get(template_id).name)


@router.post("/template-versions/{version_id}/publish", summary="Sürümü yayınla")
def surum_yayinla(version_id: UUID, servis: Servis, _: Yonetici) -> SurumDetay:
    """Doğrulama geçmezse 422 ve **tüm** sorunların listesi döner (FR-0312)."""
    surum = servis.publish(version_id)
    return _surum_detay(surum, servis.get(surum.template_id).name)
