"""Oturum uç noktaları (ST-004; FR-0201, FR-0203, FR-0204).

SMS sağlayıcısı bağlı olmadığı için kod **gönderilmiyor**. Yanıt bunu
açıkça söyler (`delivered: false`) ve yalnızca geliştirme ortamında kodu
döndürür — panel ve mobil geliştirilebilsin diye. Üretimde kod yanıtta
yer almaz; o aşamada SMS sürücüsü (ST-067) devreye girer.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from talimatname.api.bagimliliklar import izi_servisi, kimlik_servisi, oturum_servisi
from talimatname.api.guvenlik import Kullanici
from talimatname.api.hiz_siniri import HizSiniri
from talimatname.api.istek import istemci_ip
from talimatname.domain.errors import DomainError
from talimatname.domain.sessions import SessionKind
from talimatname.domain.users import ROLE_LABELS
from talimatname.services.audit import AuditService, current_context
from talimatname.services.auth import AuthService, UnknownPhone
from talimatname.services.sessions import SessionService

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
Oturumlar = Annotated[SessionService, Depends(oturum_servisi)]


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
    refresh_token: str = Field(
        description="Yenileme belirteci; **yalnızca burada** verilir, saklanması istemcinin işi"
    )
    refresh_expires_at: datetime
    user: BenYaniti


class YenilemeIstegi(BaseModel):
    refresh_token: str


class OturumOzeti(BaseModel):
    """Cihaz listesi satırı (FR-0203). Belirteç ya da özeti **dönmez**."""

    id: UUID
    kind: str
    device: str | None
    issued_at: datetime
    expires_at: datetime
    last_used_at: datetime | None
    current: bool = Field(default=False, description="Bu isteği yapan oturum mu")


class DurumYaniti(BaseModel):
    ok: bool = True


def _cihaz(request: Request) -> str | None:
    """Cihaz etiketi: User-Agent. Kullanıcıya "hangi cihaz" diyebilmek için."""
    return request.headers.get("user-agent")


def _tur(request: Request) -> SessionKind:
    """Web mi mobil mi — ömrü bu belirliyor (web 12 sa, mobil 30 gün).

    Bugün mobil istemci yok; başlık gelince ona göre davranıyoruz,
    gelmezse web sayılıyor. İstemcinin kendi ömrünü uzatmasına izin
    vermiyoruz: `X-Istemci: mobile` demek 30 güne çıkarır, o yüzden
    mobil yazıldığında bu **belirteçten** okunacak (ADR-0013).
    """
    return "mobile" if request.headers.get("x-istemci") == "mobile" else "web"


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


def _oturum_yaniti(
    kullanici: object, servis: AuthService, oturum: object, sir: str
) -> OturumYaniti:
    from talimatname.domain.sessions import Session
    from talimatname.domain.users import User
    from talimatname.settings import get_settings

    assert isinstance(kullanici, User)
    assert isinstance(oturum, Session)
    return OturumYaniti(
        access_token=servis.issue_token(kullanici),
        expires_in_minutes=get_settings().access_token_minutes,
        refresh_token=sir,
        refresh_expires_at=oturum.expires_at,
        user=_ben(kullanici),
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
def kod_dogrula(
    girdi: DogrulamaIstegi, request: Request, servis: Servis, oturumlar: Oturumlar, iz: Iz
) -> OturumYaniti:
    """Başarılı da başarısız da olay günlüğüne yazılır (FR-1301).

    Reddedilen deneme, başarılı oturum kadar önemli: denetimde "kim
    girmeye çalıştı" sorusunun cevabı orada. Telefon numarası
    yazılmıyor — kişisel veri, üstelik kayıt kullanıcı kimliğiyle
    zaten bağlanabiliyor (BR-21).
    """
    try:
        kullanici, _ = servis.verify_code(girdi.phone, girdi.code)
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
    oturum, sir = oturumlar.open(kullanici, kind=_tur(request), device=_cihaz(request))
    return _oturum_yaniti(kullanici, servis, oturum, sir)


@router.post("/auth/refresh", summary="Oturumu yenile")
def oturum_yenile(
    girdi: YenilemeIstegi,
    request: Request,
    servis: Servis,
    oturumlar: Oturumlar,
    iz: Iz,
) -> OturumYaniti:
    """Yenileme belirtecini **döndürür**: eskisi aynı anda iptal olur.

    Erişim belirteci kısa ömürlü ve durumsuz; onu uzatmak yerine
    yenisini üretiyoruz. Böylece oturum iptal edilebilir kalıyor
    (FR-0203) — pasifleştirilen ya da oturumu uzaktan kapatılan
    kullanıcı en fazla bir erişim belirteci ömrü kadar içeride kalır.

    Döndürülmüş bir belirteç ikinci kez sunulursa o kullanıcının bütün
    oturumları kapatılır: belirteç iki elde demektir ve hangisinin
    gerçek kullanıcı olduğu bilinemez.
    """
    try:
        oturum, sir = oturumlar.rotate(girdi.refresh_token, device=_cihaz(request))
    except DomainError as hata:
        iz.record("oturum.yenileme_reddedildi", object_type="kullanici", after={"sebep": hata.code})
        raise

    kullanici = servis.user_for(oturum.user_id)
    iz.record(
        "oturum.yenilendi",
        object_type="kullanici",
        object_id=kullanici.id,
        context=replace(current_context(), actor_id=kullanici.id),
        after={"oturum": str(oturum.id)},
    )
    return _oturum_yaniti(kullanici, servis, oturum, sir)


@router.post("/auth/logout", summary="Oturumu kapat")
def oturum_kapat(girdi: YenilemeIstegi, oturumlar: Oturumlar, iz: Iz) -> DurumYaniti:
    """Yenileme belirtecini iptal eder.

    Tanınmayan belirteç **hata döndürmez**: istemci zaten belirteci
    atıyor ve "çıkamadın" demek kullanıcıya yapacak bir şey bırakmıyor.
    Elindeki erişim belirteci ömrü dolana kadar geçerli kalır; bunu
    kısaltmanın yolu erişim ömrünü kısa tutmak.
    """
    kapali = oturumlar.revoke(girdi.refresh_token)
    if kapali is not None:
        iz.record(
            "oturum.kapatildi",
            object_type="kullanici",
            object_id=kapali.user_id,
            after={"oturum": str(kapali.id), "sebep": "logout"},
        )
    return DurumYaniti(ok=True)


@router.get("/auth/sessions", summary="Açık oturumlar (cihaz listesi)")
def oturum_listesi(kullanici: Kullanici, oturumlar: Oturumlar) -> list[OturumOzeti]:
    """Kullanıcının kendi açık oturumları (FR-0203).

    Başkasının oturumları görünmez: liste kullanıcının kendi
    kimliğinden türetiliyor, parametre almıyor.
    """
    return [
        OturumOzeti(
            id=o.id,
            kind=o.kind,
            device=o.device,
            issued_at=o.issued_at,
            expires_at=o.expires_at,
            last_used_at=o.last_used_at,
        )
        for o in oturumlar.active(kullanici.id)
    ]


@router.post("/auth/sessions/{session_id}/revoke", summary="Oturumu uzaktan kapat")
def oturum_sonlandir(
    session_id: UUID, kullanici: Kullanici, oturumlar: Oturumlar, iz: Iz
) -> DurumYaniti:
    """Kaybolan telefondaki oturumu kapatır (FR-0203)."""
    kapali = oturumlar.revoke_session(kullanici.id, session_id)
    iz.record(
        "oturum.kapatildi",
        object_type="kullanici",
        object_id=kullanici.id,
        after={"oturum": str(kapali.id), "sebep": "remote"},
    )
    return DurumYaniti(ok=True)


@router.get("/auth/me", summary="Oturumdaki kullanıcı")
def ben(kullanici: Kullanici) -> BenYaniti:
    return _ben(kullanici)
