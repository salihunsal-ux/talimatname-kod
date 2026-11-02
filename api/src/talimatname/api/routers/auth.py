"""Oturum uç noktaları (ST-004; FR-0201, FR-0203, FR-0204).

SMS sağlayıcısı bağlı olmadığı için kod **gönderilmiyor**. Yanıt bunu
açıkça söyler (`delivered: false`) ve yalnızca geliştirme ortamında kodu
döndürür — panel ve mobil geliştirilebilsin diye. Üretimde kod yanıtta
yer almaz; o aşamada SMS sürücüsü (ST-067) devreye girer.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from talimatname.api.bagimliliklar import izi_servisi, kimlik_servisi
from talimatname.api.guvenlik import Kullanici
from talimatname.api.hiz_siniri import HizSiniri
from talimatname.api.istek import istemci_ip
from talimatname.domain.errors import DomainError
from talimatname.domain.users import ROLE_LABELS
from talimatname.services.audit import AuditService, current_context
from talimatname.services.auth import AuthService, UnknownPhone

router = APIRouter(tags=["oturum"])

#: Dakikada izin verilen kod isteği (IP başına). Bir insan kod isteyip
#: 60 sn bekliyor; aynı IP'nin arkasında vardiya değişiminde birkaç
#: kişi olabilir, bu yüzden sınır cömert. Kapattığı şey hız: uç nokta
#: kayıtlı numaraya 200, kayıtsıza 404 dönüyor, yani **numara sorgusu**
#: olarak kullanılabiliyor. Sınırsızken bir zincirin personel listesi
#: saniyeler içinde çıkarılabiliyordu.
#:
#: Sınırın ne olmadığı `hiz_siniri` modülünde yazılı: süreç içi ve
#: IP'ye bağlı. Asıl savunma, bu isteğin artık **iz bırakması**.
KOD_ISTEK_SINIRI = 20
SINIR_PENCERESI = timedelta(minutes=1)

hiz_siniri = HizSiniri(limit=KOD_ISTEK_SINIRI, period=SINIR_PENCERESI)

Servis = Annotated[AuthService, Depends(kimlik_servisi)]
Iz = Annotated[AuditService, Depends(izi_servisi)]


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
def kod_iste(girdi: KodIstegi, request: Request, servis: Servis, iz: Iz) -> KodYaniti:
    """3 hatalı denemede 15 dk blok, 60 sn içinde yeniden gönderim yok (TC-009).

    Oturumsuz uç nokta olduğu için iki şey var: IP başına hız sınırı ve
    olay günlüğü kaydı. İkincisi daha önemli — sınır atlatılabilir,
    kayıt atlatılamaz: bilinmeyen numaralara yapılan yüzlerce istek
    günlükte art arda görünür.

    **Telefon numarası kayda yazılmıyor** (BR-21). Numara biliniyorsa
    kayıt kullanıcıya bağlanıyor; bilinmiyorsa kayıt "bilinmeyen" diyor
    ve numarayı saklamıyor. Böylece "hangi hesaplar yoklandı" sorusu
    cevaplanabiliyor, yoklanan numaralar ise ürünün içinde birikmiyor.
    """
    hiz_siniri.zorunlu_kil(istemci_ip(request))
    try:
        telefon, kod = servis.request_code(girdi.phone)
    except UnknownPhone:
        iz.record("oturum.kod_istendi", object_type="kullanici", after={"sonuc": "bilinmeyen"})
        raise
    except DomainError as hata:
        iz.record("oturum.kod_istendi", object_type="kullanici", after={"sonuc": hata.code})
        raise

    iz.record(
        "oturum.kod_istendi",
        object_type="kullanici",
        object_id=servis.user_id_for(telefon),
        after={"sonuc": "gonderildi"},
    )
    return KodYaniti(phone=telefon, dev_code=kod)


@router.post("/auth/verify", summary="Kodu doğrula ve oturum aç")
def kod_dogrula(girdi: DogrulamaIstegi, servis: Servis, iz: Iz) -> OturumYaniti:
    """Başarılı da başarısız da olay günlüğüne yazılır (FR-1301).

    Reddedilen deneme, başarılı oturum kadar önemli: denetimde "kim
    girmeye çalıştı" sorusunun cevabı orada. Telefon numarası
    yazılmıyor — kişisel veri, üstelik kayıt kullanıcı kimliğiyle
    zaten bağlanabiliyor (BR-21).
    """
    try:
        kullanici, belirtec = servis.verify_code(girdi.phone, girdi.code)
    except DomainError as hata:
        iz.record(
            "oturum.reddedildi",
            object_type="kullanici",
            after={"sebep": hata.code},
        )
        raise

    iz.record(
        "oturum.acildi",
        object_type="kullanici",
        object_id=kullanici.id,
        context=replace(current_context(), actor_id=kullanici.id),
        after={"roller": ",".join(a.role for a in kullanici.assignments) or "-"},
    )
    from talimatname.settings import get_settings

    return OturumYaniti(
        access_token=belirtec,
        expires_in_minutes=get_settings().access_token_minutes,
        user=_ben(kullanici),
    )


@router.get("/auth/me", summary="Oturumdaki kullanıcı")
def ben(kullanici: Kullanici) -> BenYaniti:
    return _ben(kullanici)
