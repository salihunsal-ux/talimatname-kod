"""Aksiyon uç noktaları (ST-064, ST-065, ST-069, ST-152; FR-0901…0910)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field

from talimatname.api.bagimliliklar import aksiyon_servisi, organizasyon_servisi
from talimatname.api.guvenlik import (
    Kullanici,
    sube_erisimi_zorunlu,
)
from talimatname.domain.actions import PRIORITY_LABELS, SOURCE_LABELS, Action, Priority
from talimatname.services.actions import ActionService
from talimatname.services.organization import (
    OrganizationService,
    erisilebilir_sube_idleri,
)

router = APIRouter(tags=["aksiyon"])

Servis = Annotated[ActionService, Depends(aksiyon_servisi)]
OrgServis = Annotated[OrganizationService, Depends(organizasyon_servisi)]


class AksiyonOzet(BaseModel):
    id: UUID
    branch_id: UUID
    branch_name: str
    title: str
    description: str | None = None
    source: Literal["missed_run", "critical_item", "not_done", "issue", "manual"]
    source_label: str
    priority: Priority
    priority_label: str
    status: Literal["open", "closed"]
    opened_at: datetime
    due_at: datetime
    overdue: bool = Field(description="Açık ve vadesi geçmiş mi")
    remaining_hours: float | None = Field(
        default=None, description="Vadeye kalan saat; kapalı aksiyonda boş"
    )
    closed_at: datetime | None = None
    close_note: str | None = None


class ElleAksiyonGirdisi(BaseModel):
    branch_id: UUID
    title: str = Field(min_length=1, max_length=160, examples=["Buzdolabı tamiri"])
    priority: Priority = "normal"
    description: str | None = None
    assignee_user_id: UUID | None = None


class KapanisGirdisi(BaseModel):
    """Kapanış notu zorunlu (FR-0904): ne yapıldığı yazılmadan kapanmaz."""

    note: str = Field(min_length=3, max_length=500, examples=["Teknisyen geldi, termostat değişti"])
    closed_by: UUID | None = None


class AksiyonSayaclari(BaseModel):
    open: int
    overdue: int
    critical: int


def _ozet(aksiyon: Action, sube_adlari: dict[UUID, str], simdi: datetime) -> AksiyonOzet:
    return AksiyonOzet(
        id=aksiyon.id,
        branch_id=aksiyon.branch_id,
        branch_name=sube_adlari.get(aksiyon.branch_id, "—"),
        title=aksiyon.title,
        description=aksiyon.description,
        source=aksiyon.source,
        source_label=SOURCE_LABELS[aksiyon.source],
        priority=aksiyon.priority,
        priority_label=PRIORITY_LABELS[aksiyon.priority],
        status=aksiyon.status,
        opened_at=aksiyon.opened_at,
        due_at=aksiyon.due_at,
        overdue=aksiyon.overdue(simdi),
        remaining_hours=(
            round(aksiyon.remaining_hours(simdi), 1) if aksiyon.status == "open" else None
        ),
        closed_at=aksiyon.closed_at,
        close_note=aksiyon.close_note,
    )


def _sube_adlari(org: OrganizationService) -> dict[UUID, str]:
    return {
        sube.id: sube.name for dugum in org.tree(include_inactive=True) for sube in dugum.branches
    }


@router.get("/actions", summary="Aksiyon listesi")
def aksiyon_listesi(
    servis: Servis,
    org: OrgServis,
    kullanici: Kullanici,
    branch_id: UUID | None = None,
    action_status: Literal["open", "closed", "all"] = "open",
    only_overdue: bool = False,
) -> list[AksiyonOzet]:
    """Varsayılan: açık aksiyonlar, **vadesi yakın olan önce**. Kapsamla süzülür."""
    adlar = _sube_adlari(org)
    kapsam = erisilebilir_sube_idleri(kullanici, org)
    simdi = datetime.now(UTC)
    return [
        _ozet(a, adlar, simdi)
        for a in servis.list_actions(
            branch_id=branch_id,
            status=None if action_status == "all" else action_status,
            only_overdue=only_overdue,
        )
        if a.branch_id in kapsam
    ]


@router.get("/actions/counts", summary="Aksiyon sayaçları")
def aksiyon_sayaclari(servis: Servis, org: OrgServis, kullanici: Kullanici) -> AksiyonSayaclari:
    """Sayaçlar da kapsamla sınırlı: bölge müdürü kendi bölgesinin yükünü görür."""
    sayac = servis.counts(erisilebilir_sube_idleri(kullanici, org))
    return AksiyonSayaclari(
        open=sayac["open"], overdue=sayac["overdue"], critical=sayac["critical"]
    )


@router.post("/actions", status_code=status.HTTP_201_CREATED, summary="Elle aksiyon aç")
def aksiyon_ac(
    girdi: ElleAksiyonGirdisi, servis: Servis, org: OrgServis, kullanici: Kullanici
) -> AksiyonOzet:
    """FR-0908. Vade önceliğe göre sabittir (BR-10): kritik 4 sa, yüksek 24, normal 72.

    Kapsam dışı şubeye aksiyon açılamaz.
    """
    sube_erisimi_zorunlu(kullanici, girdi.branch_id, org)
    aksiyon = servis.create_manual(
        branch_id=girdi.branch_id,
        title=girdi.title,
        priority=girdi.priority,
        description=girdi.description,
        assignee_user_id=girdi.assignee_user_id,
    )
    return _ozet(aksiyon, _sube_adlari(org), datetime.now(UTC))


@router.post("/actions/{action_id}/close", summary="Aksiyonu kapat")
def aksiyon_kapat(
    action_id: UUID,
    girdi: KapanisGirdisi,
    servis: Servis,
    org: OrgServis,
    kullanici: Kullanici,
) -> AksiyonOzet:
    """Kapatan, oturumdaki kullanıcıdır; kapsam dışı aksiyon kapatılamaz."""
    sube_erisimi_zorunlu(kullanici, servis.get(action_id).branch_id, org)
    aksiyon = servis.close(action_id, girdi.note, kullanici.id)
    return _ozet(aksiyon, _sube_adlari(org), datetime.now(UTC))
