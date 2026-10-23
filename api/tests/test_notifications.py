"""Bildirim ve hatırlatma testleri (ST-044, ST-045; TC-035, FR-0509, FR-1004…1007)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from conftest import oturum_ac
from talimatname.api.app import create_app
from talimatname.domain.notifications import (
    REMINDER_BEFORE_CLOSE,
    Notification,
    defer_past_quiet_hours,
    notification_id,
    quiet_hours,
    reminder_slots,
)
from talimatname.domain.users import User
from talimatname.infra.memory import (
    MemoryNotificationRepository,
    MemoryOrganizationRepository,
    MemoryPlanRepository,
    MemoryTemplateRepository,
    MemoryUserRepository,
    sabit_id,
)
from talimatname.services.notifications import (
    ChannelDriver,
    DriverResult,
    NotificationService,
)
from talimatname.services.plans import PlanService
from talimatname.services.reminders import CATCH_UP, ReminderService
from talimatname.services.scheduler import SchedulerService
from talimatname.settings import Settings

KADIKOY = sabit_id("sube:KDK")
ISTANBUL = "Europe/Istanbul"


class SayanSurucu:
    """Test sürücüsü: kaç çağrı geldiğini sayar, istenirse hata döndürür."""

    channel = "push"

    def __init__(self, *, basarili: bool = True) -> None:
        self.gonderilenler: list[tuple[Notification, User]] = []
        self._basarili = basarili

    def send(self, notification: Notification, user: User) -> DriverResult:
        self.gonderilenler.append((notification, user))
        if self._basarili:
            return DriverResult.basarili()
        return DriverResult.hata("token-gecersiz", "cihaz kaydı bulunamadı")


def _servis(surucu: ChannelDriver | None = None, an: datetime | None = None) -> NotificationService:
    zaman = an or datetime(2026, 3, 2, 10, 0, tzinfo=UTC)
    return NotificationService(
        MemoryNotificationRepository(),
        MemoryUserRepository(),
        drivers=[surucu] if surucu else (),
        now=lambda: zaman,
    )


def _kullanici() -> User:
    kisi = MemoryUserRepository().user_by_phone("+905321110005")
    assert kisi is not None
    return kisi


def _kuyrukla(
    servis: NotificationService, *, send_at: datetime, kind: str = "run_opened", slot: str = "a"
) -> Notification:
    return servis.queue(
        kind=kind,  # type: ignore[arg-type]
        user=_kullanici(),
        subject_id=sabit_id("calistirma:1"),
        title="Günlük kapanış başladı",
        body="Kadıköy · liste şimdi açıldı",
        send_at=send_at,
        timezone=ISTANBUL,
        slot=slot,
    )


# --- alan -------------------------------------------------------------


def test_tc035_iki_sabit_hatirlatma() -> None:
    """Açılış ve bitişe 30 dk kala (FR-0509)."""
    basla = datetime(2026, 3, 2, 19, 0, tzinfo=UTC)
    biter = basla + timedelta(hours=3)

    slotlar = reminder_slots(basla, biter)

    assert [s[0] for s in slotlar] == ["run_opened", "window_closing"]
    assert slotlar[0][1] == basla
    assert slotlar[1][1] == biter - REMINDER_BEFORE_CLOSE


def test_kisa_pencerede_tek_hatirlatma() -> None:
    """20 dakikalık pencerede iki bildirim aynı ana düşerdi; biri yeter."""
    basla = datetime(2026, 3, 2, 19, 0, tzinfo=UTC)
    slotlar = reminder_slots(basla, basla + timedelta(minutes=20))
    assert [s[0] for s in slotlar] == ["run_opened"]


def test_tekil_kimlik_ayni_dilimde_ayni() -> None:
    kisi, konu = uuid4(), uuid4()
    assert notification_id("run_opened", kisi, konu, "acilis") == notification_id(
        "run_opened", kisi, konu, "acilis"
    )
    assert notification_id("run_opened", kisi, konu, "acilis") != notification_id(
        "run_opened", kisi, konu, "kapanis-30"
    )


@pytest.mark.parametrize(
    ("saat", "sessiz"),
    [(22, False), (23, True), (2, True), (6, True), (7, False), (12, False)],
)
def test_sessiz_saatler_yerel_saate_gore(saat: int, sessiz: bool) -> None:
    """23:00–07:00 **yerel** duvar saatidir (FR-1004), UTC değil."""
    an = datetime(2026, 3, 2, saat, 30, tzinfo=ZoneInfo(ISTANBUL)).astimezone(UTC)
    assert quiet_hours(an, ISTANBUL) is sessiz


def test_sessiz_saatteki_bildirim_sabaha_otelenir() -> None:
    gece = datetime(2026, 3, 2, 2, 30, tzinfo=ZoneInfo(ISTANBUL)).astimezone(UTC)
    otelenmis = defer_past_quiet_hours(gece, ISTANBUL)
    assert otelenmis > gece
    assert not quiet_hours(otelenmis, ISTANBUL)


def test_gece_vardiyasi_hatirlatmasi_sabaha_otelenmez() -> None:
    """Kapanış listesi gece yapılır; hatırlatmasını susturmak ürünü susturur.

    FR-1004 yönetici bildirimlerini öteler. Pencereye bağlı iş
    hatırlatması ötelenirse pencere kapandıktan saatler sonra
    "30 dakika kaldı" yazar — bu gürültü değil, yanlış bilgi.
    """
    gece = datetime(2026, 3, 3, 0, 30, tzinfo=ZoneInfo(ISTANBUL)).astimezone(UTC)
    assert quiet_hours(gece, ISTANBUL)

    servis = _servis(an=gece)
    kayit = _kuyrukla(servis, send_at=gece, kind="window_closing", slot="kapanis-30")

    assert kayit.send_at == gece


def test_yonetim_bildirimi_sabaha_otelenir() -> None:
    gece = datetime(2026, 3, 3, 0, 30, tzinfo=ZoneInfo(ISTANBUL)).astimezone(UTC)
    servis = _servis(an=gece)

    kayit = _kuyrukla(servis, send_at=gece, kind="daily_digest", slot="ozet")

    assert kayit.send_at > gece
    assert not quiet_hours(kayit.send_at, ISTANBUL)


def test_kritik_olay_hic_beklemez() -> None:
    gece = datetime(2026, 3, 3, 0, 30, tzinfo=ZoneInfo(ISTANBUL)).astimezone(UTC)
    servis = _servis(an=gece)

    kayit = _kuyrukla(servis, send_at=gece, kind="critical_failed", slot="kritik")

    assert kayit.send_at == gece
    assert kayit.critical


# --- servis -----------------------------------------------------------


def test_kuyruk_idempotent() -> None:
    servis = _servis()
    an = datetime(2026, 3, 2, 10, 0, tzinfo=UTC)
    birinci = _kuyrukla(servis, send_at=an)
    ikinci = _kuyrukla(servis, send_at=an)

    assert birinci.id == ikinci.id
    assert servis.counts()["total"] == 1


def test_surucu_yoksa_gonderildi_denmez() -> None:
    """Ürün kararı: gönderilmemiş bildirim gönderilmiş sayılmaz."""
    an = datetime(2026, 3, 2, 10, 0, tzinfo=UTC)
    servis = _servis(an=an)
    kayit = _kuyrukla(servis, send_at=an - timedelta(minutes=1))

    sayac = servis.dispatch(an)

    assert sayac == {"sent": 0, "failed": 1, "suppressed": 0}
    sonuc = servis.get(kayit.id)
    assert sonuc.status == "failed"
    assert sonuc.error_code == "surucu-yok"
    assert servis.driver_names() == []


def test_surucu_varsa_kanala_verilir_ama_teslim_sayilmaz() -> None:
    an = datetime(2026, 3, 2, 10, 0, tzinfo=UTC)
    surucu = SayanSurucu()
    servis = _servis(surucu, an=an)
    kayit = _kuyrukla(servis, send_at=an)

    assert servis.dispatch(an)["sent"] == 1
    assert servis.get(kayit.id).status == "sent"  # "delivered" değil
    assert len(surucu.gonderilenler) == 1

    servis.mark_delivered(kayit.id, an + timedelta(seconds=5))
    assert servis.get(kayit.id).status == "delivered"


def test_surucu_hatasi_koduyla_kaydedilir() -> None:
    an = datetime(2026, 3, 2, 10, 0, tzinfo=UTC)
    servis = _servis(SayanSurucu(basarili=False), an=an)
    kayit = _kuyrukla(servis, send_at=an)

    assert servis.dispatch(an)["failed"] == 1
    assert servis.get(kayit.id).error_code == "token-gecersiz"


def test_zamani_gelmemis_bildirim_gonderilmez() -> None:
    an = datetime(2026, 3, 2, 10, 0, tzinfo=UTC)
    surucu = SayanSurucu()
    servis = _servis(surucu, an=an)
    _kuyrukla(servis, send_at=an + timedelta(hours=1))

    assert servis.dispatch(an) == {"sent": 0, "failed": 0, "suppressed": 0}
    assert surucu.gonderilenler == []


def test_pasif_kullaniciya_gonderilmez() -> None:
    an = datetime(2026, 3, 2, 10, 0, tzinfo=UTC)
    depo = MemoryUserRepository()
    kisi = depo.user_by_phone("+905321110005")
    assert kisi is not None
    surucu = SayanSurucu()
    servis = NotificationService(
        MemoryNotificationRepository(), depo, drivers=[surucu], now=lambda: an
    )
    kayit = servis.queue(
        kind="run_opened",
        user=kisi,
        subject_id=uuid4(),
        title="Liste açıldı",
        body="",
        send_at=an,
        timezone=ISTANBUL,
    )

    from dataclasses import replace

    depo.save_user(replace(kisi, status="inactive"))
    assert servis.dispatch(an)["suppressed"] == 1
    assert servis.get(kayit.id).status == "suppressed"
    assert surucu.gonderilenler == []


# --- hatırlatma + zamanlayıcı ----------------------------------------


def _hatirlatma_kurulumu(an: datetime) -> tuple[ReminderService, NotificationService]:
    planlar = MemoryPlanRepository()
    org = MemoryOrganizationRepository()
    PlanService(planlar, org, MemoryTemplateRepository(), now=lambda: an).generate_all()
    bildirim = NotificationService(
        MemoryNotificationRepository(), MemoryUserRepository(), now=lambda: an
    )
    return (
        ReminderService(planlar, org, MemoryUserRepository(), bildirim, now=lambda: an),
        bildirim,
    )


def test_hatirlatma_kuyruga_girer_ve_tekrar_etmez() -> None:
    an = datetime.now(UTC)
    hatirlatma, bildirim = _hatirlatma_kurulumu(an)

    birinci = hatirlatma.schedule(an)
    toplam = bildirim.counts()["total"]
    hatirlatma.schedule(an)

    assert birinci > 0
    assert bildirim.counts()["total"] == toplam  # ikinci tur kopya üretmedi


def test_hatirlatma_yalnizca_isi_yapanlara_gider() -> None:
    """Yöneticiye hatırlatma gitmez; ona kaçırma ve eskalasyon gider."""
    an = datetime.now(UTC)
    hatirlatma, bildirim = _hatirlatma_kurulumu(an)
    hatirlatma.schedule(an)

    depo = MemoryUserRepository()
    alicilar = {b.user_id for b in bildirim.list_notifications()}
    roller = {r for kid in alicilar for r in (depo.user(kid).roles if depo.user(kid) else ())}

    assert roller
    assert "admin" not in roller
    assert "region_manager" not in roller


def test_cok_gecmis_hatirlatma_gonderilmez() -> None:
    """Zamanlayıcı durduysa 'şimdi başladı' demek yalan olurdu."""
    an = datetime.now(UTC)
    hatirlatma, bildirim = _hatirlatma_kurulumu(an)

    hatirlatma.schedule(an)
    for kayit in bildirim.list_notifications():
        assert kayit.send_at >= an - CATCH_UP


def test_zamanlayici_turu_hatirlatmalari_sayar() -> None:
    an = datetime.now(UTC)
    planlar = MemoryPlanRepository()
    org = MemoryOrganizationRepository()
    sablonlar = MemoryTemplateRepository()
    bildirim = NotificationService(
        MemoryNotificationRepository(), MemoryUserRepository(), now=lambda: an
    )
    hatirlatma = ReminderService(planlar, org, MemoryUserRepository(), bildirim, now=lambda: an)
    zamanlayici = SchedulerService(
        planlar, org, sablonlar, None, hatirlatma, bildirim, now=lambda: an
    )

    sonuc = zamanlayici.tick()

    assert sonuc.reminders_queued > 0
    assert not sonuc.quiet


# --- uç noktalar ------------------------------------------------------


def _istemci(rol: str = "admin") -> TestClient:
    return oturum_ac(TestClient(create_app(Settings(environment="dev"))), rol)


def test_uc_nokta_teslimat_izi_eksikligi_gizlemez() -> None:
    yanit = _istemci().get("/api/v1/notifications/counts")
    assert yanit.status_code == 200
    govde = yanit.json()
    assert govde["drivers_connected"] == []  # push ve SMS henüz bağlı değil

    liste = _istemci().get("/api/v1/notifications").json()
    if liste:
        assert all(b["status"] != "delivered" for b in liste)


def test_uc_nokta_teslimat_izi_yoneticiye_ozel() -> None:
    assert _istemci("branch_manager").get("/api/v1/notifications").status_code == 403
