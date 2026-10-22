"""Personel ve rol uç noktaları (ST-011, ST-013; FR-0107…0110, FR-0205)."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field

from talimatname.api.bagimliliklar import kullanici_servisi
from talimatname.domain.users import ROLE_LABELS, Role, RoleAssignment, User
from talimatname.services.users import UserService

router = APIRouter(tags=["personel"])

Servis = Annotated[UserService, Depends(kullanici_servisi)]


class RolAtamasi(BaseModel):
    role: Role
    role_label: str = Field(description="Rolün Türkçe adı; arayüz bunu gösterir")
    scope_type: Literal["tenant", "region", "branch"]
    scope_id: UUID | None = None


class RolGirdisi(BaseModel):
    """Rol atama gövdesi. Kapsam türü rolden belirlenir, ayrıca gönderilmez."""

    role: Role
    scope_id: UUID | None = None


class KullaniciOzet(BaseModel):
    id: UUID
    full_name: str
    phone: str | None
    email: str | None = None
    status: Literal["active", "inactive", "masked"]
    assignments: list[RolAtamasi]
    invited_at: datetime | None = None
    masked_at: datetime | None = None
    pin_set: bool = False


class KullaniciGirdisi(BaseModel):
    full_name: str = Field(min_length=1, max_length=80, examples=["Ayşe Yılmaz"])
    phone: str = Field(examples=["0532 111 00 08"], description="E.164'e çevrilir")
    email: str | None = None
    assignments: list[RolGirdisi] = Field(min_length=1)


class DavetYaniti(BaseModel):
    """Davet sonucu.

    `invite_sent` bugün **her zaman false**: SMS sağlayıcısı bağlı değil
    (ST-044). Arayüz "gönderildi" demez, "kuyruğa alındı" der.
    """

    user: KullaniciOzet
    invite_sent: bool = False
    invite_note: str = "SMS sağlayıcısı bağlanınca davet gönderilecek (ST-044)."


def _atamalar(girdi: list[RolGirdisi]) -> tuple[RoleAssignment, ...]:
    return tuple(RoleAssignment(role=g.role, scope_id=g.scope_id) for g in girdi)


def _ozet(kullanici: User) -> KullaniciOzet:
    return KullaniciOzet(
        id=kullanici.id,
        full_name=kullanici.full_name,
        phone=kullanici.phone,
        email=kullanici.email,
        status=kullanici.status,
        assignments=[
            RolAtamasi(
                role=a.role,
                role_label=ROLE_LABELS[a.role],
                scope_type=a.scope_type,
                scope_id=a.scope_id,
            )
            for a in kullanici.assignments
        ],
        invited_at=kullanici.invited_at,
        masked_at=kullanici.masked_at,
        pin_set=kullanici.pin_set,
    )


@router.get("/users", summary="Personel listesi")
def personel_listesi(
    servis: Servis,
    branch_id: UUID | None = None,
    role: Role | None = None,
    include_inactive: bool = False,
) -> list[KullaniciOzet]:
    """Şubeye ya da role göre süzülebilir; kapsam denetimi `can_access` ile."""
    return [
        _ozet(k)
        for k in servis.list_users(
            branch_id=branch_id, role=role, include_inactive=include_inactive
        )
    ]


@router.get("/users/{user_id}", summary="Personel detayı")
def personel_detayi(user_id: UUID, servis: Servis) -> KullaniciOzet:
    return _ozet(servis.get(user_id))


@router.post("/users", status_code=status.HTTP_201_CREATED, summary="Personel davet et")
def personel_davet(girdi: KullaniciGirdisi, servis: Servis) -> DavetYaniti:
    kullanici = servis.invite(
        User(
            id=uuid4(),
            full_name=girdi.full_name,
            phone=girdi.phone,
            email=girdi.email,
            assignments=_atamalar(girdi.assignments),
        )
    )
    return DavetYaniti(user=_ozet(kullanici))


@router.patch("/users/{user_id}/roles", summary="Rolleri değiştir")
def roller_guncelle(user_id: UUID, girdi: list[RolGirdisi], servis: Servis) -> KullaniciOzet:
    return _ozet(servis.update(user_id, assignments=_atamalar(girdi)))


@router.post("/users/{user_id}/deactivate", summary="Personeli pasifleştir")
def personel_pasiflestir(user_id: UUID, servis: Servis) -> KullaniciOzet:
    """Giriş kapanır, gelecek atamalar düşer; geçmiş cevap ve kanıtlar kalır (BR-22)."""
    return _ozet(servis.set_status(user_id, "inactive"))


@router.post("/users/{user_id}/activate", summary="Personeli yeniden aktif et")
def personel_aktif_et(user_id: UUID, servis: Servis) -> KullaniciOzet:
    return _ozet(servis.set_status(user_id, "active"))


@router.post("/users/{user_id}/mask", summary="KVKK: kişi verisini maskele")
def personel_maskele(user_id: UUID, servis: Servis) -> KullaniciOzet:
    """Silme talebi karşılığı (FR-1310): ad takma etikete döner, telefon
    ve e-posta silinir; cevaplar ve kanıtlar iş kaydı olarak kalır."""
    return _ozet(servis.mask(user_id))
