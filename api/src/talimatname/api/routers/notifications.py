"""Bildirim uç noktaları: teslimat izi (ST-044; FR-1005).

Bu liste bir destek aracıdır: "gitti mi?" sorusunun cevabı. Sürücü
bağlanmadığı sürece kayıtların çoğu `failed / surucu-yok` olacak ve
**öyle görünmesi gerekiyor** — eksik bir entegrasyonu başarılı
göstermek, sahada kaybolan hatırlatmayı aramaya dönüşür.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from talimatname.api.bagimliliklar import bildirim_servisi, kullanici_servisi
from talimatname.api.guvenlik import Yonetici
from talimatname.domain.notifications import Notification
from talimatname.services.notifications import NotificationService
from talimatname.services.users import UserService

router = APIRouter(tags=["bildirim"])

Servis = Annotated[NotificationService, Depends(bildirim_servisi)]
KullaniciServis = Annotated[UserService, Depends(kullanici_servisi)]

DURUM_ETIKETLERI: dict[str, str] = {
    "queued": "Kuyrukta",
    "sent": "Kanala verildi",
    "delivered": "Teslim edildi",
    "failed": "Gönderilemedi",
    "suppressed": "Gönderilmedi",
}

TUR_ETIKETLERI: dict[str, str] = {
    "run_opened": "Liste açıldı",
    "reminder": "Hatırlatma",
    "window_closing": "30 dakika kaldı",
    "run_missed": "Liste kaçırıldı",
    "action_opened": "Aksiyon açıldı",
    "critical_failed": "Kritik madde başarısız",
    "daily_digest": "Günlük özet",
}


class BildirimOzet(BaseModel):
    id: UUID
    kind: str
    kind_label: str
    channel: Literal["push", "sms", "email"]
    user_id: UUID
    user_name: str
    title: str
    body: str
    send_at: datetime
    status: Literal["queued", "sent", "delivered", "failed", "suppressed"]
    status_label: str
    attempts: int
    error_code: str | None = Field(
        default=None, description="Örn. surucu-yok: kanal henüz bağlanmadı"
    )
    error_detail: str | None = None
    run_id: UUID | None = None
    branch_id: UUID | None = None


class BildirimSayaclari(BaseModel):
    """Kuyruğun özeti. `failed` sıfırdan büyükse bir şey eksik demektir."""

    queued: int
    sent: int
    failed: int
    total: int
    drivers_connected: list[str] = Field(
        default_factory=list, description="Bağlı kanal sürücüleri; boşsa hiçbiri"
    )


def _ozet(bildirim: Notification, adlar: dict[UUID, str]) -> BildirimOzet:
    return BildirimOzet(
        id=bildirim.id,
        kind=bildirim.kind,
        kind_label=TUR_ETIKETLERI.get(bildirim.kind, bildirim.kind),
        channel=bildirim.channel,
        user_id=bildirim.user_id,
        user_name=adlar.get(bildirim.user_id, "—"),
        title=bildirim.title,
        body=bildirim.body,
        send_at=bildirim.send_at,
        status=bildirim.status,
        status_label=DURUM_ETIKETLERI.get(bildirim.status, bildirim.status),
        attempts=bildirim.attempts,
        error_code=bildirim.error_code,
        error_detail=bildirim.error_detail,
        run_id=bildirim.run_id,
        branch_id=bildirim.branch_id,
    )


@router.get("/notifications", summary="Teslimat izi")
def bildirim_listesi(
    servis: Servis,
    kullanicilar: KullaniciServis,
    _: Yonetici,
    delivery_status: Literal["queued", "sent", "delivered", "failed", "suppressed", "all"] = "all",
    limit: int = 200,
) -> list[BildirimOzet]:
    adlar = {k.id: k.full_name for k in kullanicilar.list_users(include_inactive=True)}
    kayitlar = servis.list_notifications(
        status=None if delivery_status == "all" else delivery_status, limit=limit
    )
    return [_ozet(b, adlar) for b in kayitlar]


@router.get("/notifications/counts", summary="Kuyruk sayaçları")
def bildirim_sayaclari(servis: Servis, _: Yonetici) -> BildirimSayaclari:
    return BildirimSayaclari(**servis.counts(), drivers_connected=servis.driver_names())
