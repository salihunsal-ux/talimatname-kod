"""Oturum uç noktaları (ST-004; FR-0201, FR-0203, FR-0204).

SMS sağlayıcısı bağlı olmadığı için kod **gönderilmiyor**. Yanıt bunu
açıkça söyler (`delivered: false`) ve yalnızca geliştirme ortamında kodu
döndürür — panel ve mobil geliştirilebilsin diye. Üretimde kod yanıtta
yer almaz; o aşamada SMS sürücüsü (ST-067) devreye girer.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from talimatname.api.bagimliliklar import kimlik_servisi
from talimatname.api.guvenlik import Kullanici
from talimatname.domain.users import ROLE_LABELS
from talimatname.services.auth import AuthService

router = APIRouter(tags=["oturum"])

Servis = Annotated[AuthService, Depends(kimlik_servisi)]


class KodIstegi(BaseModel):
    phone: str = Field(examples=["0532 111 00 03"], description="E.164'e çevrilir")


class KodYaniti(BaseModel):
    phone: str
    delivered: bool = Field(
        default=False, description="SMS gönderildi mi (sağlayıcı bağlanana kadar false)"
    )
    note: str = "SMS sağlayıcısı bağlanınca kod telefona gidecek (ST-067)."
    dev_code: str | None = Field(default=None, description="Yalnızca geliştirme ortamında dolu")


class DogrulamaIstegi(BaseModel):
    phone: str
    code: str = Field(min_length=4, max_length=8)


class RolCiktisi(BaseModel):
    role: str
    role_label: str
    scope_type: str
    scope_id: UUID | None = None


class BenYaniti(BaseModel):
    id: UUID
    full_name: str
    phone: str | None
    roles: list[RolCiktisi]


class OturumYaniti(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in_minutes: int
    user: BenYaniti


def _ben(kullanici: object) -> BenYaniti:
    from talimatname.domain.users import User

    assert isinstance(kullanici, User)
    return BenYaniti(
        id=kullanici.id,
        full_name=kullanici.full_name,
        phone=kullanici.phone,
        roles=[
            RolCiktisi(
                role=a.role,
                role_label=ROLE_LABELS[a.role],
                scope_type=a.scope_type,
                scope_id=a.scope_id,
            )
            for a in kullanici.assignments
        ],
    )


@router.post("/auth/request-code", summary="Doğrulama kodu iste")
def kod_iste(girdi: KodIstegi, servis: Servis) -> KodYaniti:
    """3 hatalı denemede 15 dk blok, 60 sn içinde yeniden gönderim yok (TC-009)."""
    telefon, kod = servis.request_code(girdi.phone)
    return KodYaniti(phone=telefon, dev_code=kod)


@router.post("/auth/verify", summary="Kodu doğrula ve oturum aç")
def kod_dogrula(girdi: DogrulamaIstegi, servis: Servis) -> OturumYaniti:
    kullanici, belirtec = servis.verify_code(girdi.phone, girdi.code)
    from talimatname.settings import get_settings

    return OturumYaniti(
        access_token=belirtec,
        expires_in_minutes=get_settings().access_token_minutes,
        user=_ben(kullanici),
    )


@router.get("/auth/me", summary="Oturumdaki kullanıcı")
def ben(kullanici: Kullanici) -> BenYaniti:
    return _ben(kullanici)
