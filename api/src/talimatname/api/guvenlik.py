"""Yetki denetimi: kim, neyi, nerede (FR-0205; TC-006, TC-010).

İki kural ve ikisi de burada toplanıyor:

* **Kim** — uç nokta en az hangi rolü ister. `admin > region_manager >
  branch_manager > staff` sırası yok: rol bir **yetki kümesidir**,
  sıralama değil. Bu yüzden gereken roller açıkça yazılır.
* **Nerede** — kapsam. Şubeye dokunan her uç nokta `can_access` ile
  süzülür; uç noktalar kendi `if`'ini yazmaz (ADR-0014 md.4).

Kapsam **belirteçten değil kullanıcıdan** okunur: rol değişince elindeki
belirteç eski yetkiyi taşımaz.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Request

from talimatname.api.bagimliliklar import kimlik_servisi
from talimatname.domain.errors import DomainError, ErrorKind
from talimatname.domain.organization import Branch
from talimatname.domain.users import Role, User, can_access
from talimatname.services.audit import set_actor
from talimatname.services.auth import AuthService
from talimatname.services.organization import OrganizationService
from talimatname.services.tokens import TokenInvalid


class NotAuthenticated(DomainError):
    code = "oturum-yok"
    title = "Oturum açmanız gerekiyor"
    kind: ErrorKind = "forbidden"


class Forbidden(DomainError):
    code = "yetki-yok"
    title = "Bu işlem için yetkiniz yok"
    kind: ErrorKind = "forbidden"


def _belirtec(request: Request) -> str:
    baslik = request.headers.get("Authorization", "")
    if not baslik.lower().startswith("bearer "):
        raise NotAuthenticated("Authorization başlığı yok")
    return baslik[7:].strip()


def gecerli_kullanici(
    request: Request,
    kimlik: Annotated[AuthService, Depends(kimlik_servisi)],
) -> User:
    """Belirteçten kullanıcıyı çözer. Her korumalı uç noktanın girişi.

    Çözülen kullanıcı **olay günlüğü bağlamına** da yazılıyor
    (FR-1301 "aktör"): günlüğe yazan yer servisin derinliği ve orası
    kimin istediğini bilmiyor. Burası biliyor ve tek giriş noktası.
    """
    try:
        kullanici = kimlik.user_from_token(_belirtec(request))
    except TokenInvalid:
        raise
    except DomainError:
        raise
    set_actor(kullanici.id)
    return kullanici


Kullanici = Annotated[User, Depends(gecerli_kullanici)]


def rol_gerekir(*roller: Role) -> Callable[[User], User]:
    """Belirtilen rollerden en az birini ister."""

    def denetle(kullanici: Kullanici) -> User:
        if not set(roller) & set(kullanici.roles):
            raise Forbidden(f"Gereken rol: {', '.join(roller)}")
        return kullanici

    return denetle


#: Sık kullanılan iki küme.
Yonetici = Annotated[User, Depends(rol_gerekir("admin"))]
YoneticiVeyaBolge = Annotated[User, Depends(rol_gerekir("admin", "region_manager"))]


def gorebildigi_subeler(kullanici: User, subeler: Iterable[Branch]) -> list[Branch]:
    return [s for s in subeler if can_access(kullanici, s)]


def sube_erisimi_zorunlu(
    kullanici: User,
    branch_id: UUID,
    org: OrganizationService,
) -> Branch:
    """Kullanıcının bu şubeye erişimi yoksa **404 değil 403** döner.

    Varlığı gizlemek (404) ile yetkisizliği söylemek (403) arasında
    seçim: v1'de şube kodları zaten zincir içinde bilinen bilgi, bu
    yüzden açık mesaj daha yararlı.
    """
    sube = org.get(branch_id)
    if not can_access(kullanici, sube):
        raise Forbidden(f"Şube kapsamınızda değil: {sube.code}")
    return sube


def erisilebilir_sube_idleri(kullanici: User, org: OrganizationService) -> set[UUID]:
    """Kullanıcının kapsamındaki şube kimlikleri — liste süzgeçlerinin temeli."""
    return {
        sube.id
        for dugum in org.tree(include_inactive=True)
        for sube in dugum.branches
        if can_access(kullanici, sube)
    }
