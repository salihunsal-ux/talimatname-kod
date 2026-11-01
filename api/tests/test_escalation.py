"""Eskalasyon ve sabah özeti testleri (ST-066, ST-143; TC-073…077, BR-11, BR-27)."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from talimatname.domain.actions import from_critical_item
from talimatname.domain.audit import AuditEvent
from talimatname.infra.memory import (
    MemoryActionRepository,
    MemoryAuditRepository,
    MemoryNotificationRepository,
    MemoryOrganizationRepository,
    MemoryPlanRepository,
    MemoryTemplateRepository,
    MemoryUserRepository,
    sabit_id,
)
from talimatname.services.audit import AuditService
from talimatname.services.digest import DIGEST_AT, DigestService
from talimatname.services.escalation import SMS_AFTER, EscalationService
from talimatname.services.notifications import NotificationService
from talimatname.services.plans import PlanService

KADIKOY = sabit_id("sube:KDK")
ISTANBUL = "Europe/Istanbul"
AYSE = sabit_id("kullanici:+905321110003")  # Kadıköy şube müdürü
MURAT = sabit_id("kullanici:+905321110002")  # Anadolu bölge müdürü
CEM = sabit_id("kullanici:+905321110001")  # yönetici


class Dunya:
    """Testin kurduğu küçük dünya: tohum depolar + servisler, sabit saatle."""

    def __init__(self, an: datetime) -> None:
        self.an = an
        self.planlar = MemoryPlanRepository()
        self.org = MemoryOrganizationRepository()
        self.kullanicilar = MemoryUserRepository()
        self.aksiyonlar = MemoryActionRepository()
        self.bildirim = NotificationService(
            MemoryNotificationRepository(), self.kullanicilar, now=lambda: self.an
        )
        PlanService(
            self.planlar, self.org, MemoryTemplateRepository(), now=lambda: self.an
        ).generate_all()
        self.izi = AuditService(MemoryAuditRepository(), now=lambda: self.an)
        self.eskalasyon = EscalationService(
            self.planlar,
            self.org,
            self.kullanicilar,
            self.aksiyonlar,
            self.bildirim,
            self.izi,
            now=lambda: self.an,
        )
        self.ozet = DigestService(
            self.planlar,
            self.org,
            self.kullanicilar,
            self.aksiyonlar,
            self.bildirim,
            now=lambda: self.an,
        )

    def kacir(self, gun: date | None = None) -> None:
        """Kadıköy'ün bir çalıştırmasını kaçırılmış yapar.

        `gun` verilirse iş günü de değiştirilir: sabah özeti **önceki**
        iş gününe bakıyor (BR-27), eskalasyon ise tolerans anına.
        """
        for run in self.planlar.runs():
            if run.branch_id == KADIKOY:
                self.planlar.save_run(
                    replace(
                        run,
                        status="missed",
                        business_day=gun or run.business_day,
                        tolerance_end=self.an - timedelta(minutes=5),
                    )
                )
                return
        raise AssertionError("Kadıköy çalıştırması bulunamadı")

    def kritik_aksiyon(self) -> object:
        run = next(r for r in self.planlar.runs() if r.branch_id == KADIKOY)
        aksiyon = from_critical_item(
            run_id=run.id,
            item_id=sabit_id("madde:buzdolabi"),
            branch_id=KADIKOY,
            item_title="Buzdolabı sıcaklığı",
            plan_name="Günlük kapanış",
            now=self.an,
        )
        self.aksiyonlar.save_action(aksiyon)
        return aksiyon

    def alicilar(self, kind: str) -> set[object]:
        return {b.user_id for b in self.bildirim.list_notifications() if b.kind == kind}

    def olaylar(self, tur: str) -> list[AuditEvent]:
        return [o for o in self.izi._repo.events(limit=500) if o.event_type == tur]

    def muduru_pasiflestir(self) -> None:
        """Kadıköy'ün müdürünü pasife alır: basamak boşalır (FR-0915)."""
        mudur = self.kullanicilar.user(AYSE)
        assert mudur is not None
        self.kullanicilar.save_user(replace(mudur, status="inactive"))


def _an() -> datetime:
    """Sabah özeti penceresinin dışında bir öğle vakti."""
    return datetime(2026, 3, 2, 12, 0, tzinfo=ZoneInfo(ISTANBUL)).astimezone(UTC)


# --- eskalasyon -------------------------------------------------------


def test_tc073_kacirilan_liste_sube_muduruna_gider() -> None:
    """Bölge müdürü uyandırılmaz: o, sabah özetinde görür (BR-11)."""
    dunya = Dunya(_an())
    dunya.kacir()

    sonuc = dunya.eskalasyon.run()

    assert sonuc["missed"] >= 1
    alicilar = dunya.alicilar("run_missed")
    assert AYSE in alicilar
    assert MURAT not in alicilar


def test_eskalasyon_tekrar_kosunca_kopya_uretmez() -> None:
    dunya = Dunya(_an())
    dunya.kacir()

    dunya.eskalasyon.run()
    toplam = dunya.bildirim.counts()["total"]
    dunya.eskalasyon.run()

    assert dunya.bildirim.counts()["total"] == toplam


def test_eskalasyon_adimi_gunluge_yaziliyor() -> None:
    """FR-0913: her adım olay günlüğüne.

    Aksiyonun yorum dizisine yazma yarısı v1'de yok: yorum dizisi
    v1.1'e bırakıldı (ADR-0008).
    """
    dunya = Dunya(_an())
    dunya.kacir()

    dunya.eskalasyon.run()

    olaylar = dunya.olaylar("aksiyon.eskalasyon")
    assert len(olaylar) == 1
    assert olaylar[0].after["tetik"] == "kacirilan-liste"
    assert olaylar[0].after["adim"] == "branch_manager"
    assert olaylar[0].after["alici"] == "1"
    assert olaylar[0].object_type == "calistirma"


def test_ayni_adim_ikinci_turda_gunluge_yazilmiyor() -> None:
    """Tur dakikada bir koşuyor; kuyruk idempotent ama günlük değil.

    Yazsaydık, hiçbir şey olmadığı hâlde zincir her dakika büyürdü.
    """
    dunya = Dunya(_an())
    dunya.kacir()
    dunya.eskalasyon.run()

    dunya.eskalasyon.run()

    assert len(dunya.olaylar("aksiyon.eskalasyon")) == 1


def test_fr0915_alicisi_olmayan_adim_gunluge_dusuyor() -> None:
    """Sessizce bir üste geçmek, eskalasyonun kaybolduğu yerdir."""
    dunya = Dunya(_an())
    dunya.muduru_pasiflestir()
    dunya.kacir()

    dunya.eskalasyon.run()

    atlanan = dunya.olaylar("aksiyon.alici_yok")
    assert len(atlanan) == 1
    assert atlanan[0].after["eksik_adim"] == "branch_manager"
    assert atlanan[0].after["yurutulen_adim"] == "region_manager"
    # Bildirim bölge müdürüne gitti: adım atlandı ama iş durmadı.
    assert MURAT in dunya.alicilar("run_missed")
    assert dunya.olaylar("aksiyon.eskalasyon")[0].after["adim"] == "region_manager"


def test_gunluk_kisisel_veri_tasimiyor() -> None:
    """BR-21: kaç kişiye gittiği yazılıyor, kim olduğu değil."""
    dunya = Dunya(_an())
    dunya.kacir()

    dunya.eskalasyon.run()

    metin = str(dunya.olaylar("aksiyon.eskalasyon")[0].after)
    assert "Ayşe" not in metin
    assert "905321110003" not in metin


def test_tc074_kritik_madde_sube_ve_bolge_muduruna_gider() -> None:
    dunya = Dunya(_an())
    dunya.kritik_aksiyon()

    dunya.eskalasyon.run()

    alicilar = dunya.alicilar("critical_failed")
    assert {AYSE, MURAT} <= alicilar


def test_tc075_teslim_edilmeyen_kritik_sms_tetikler() -> None:
    """FR-1008: 10 dk içinde teslim yoksa ikinci yol denenir.

    Sürücü bağlı değilken push `failed` oluyor; bu da "teslim edilmedi"
    sayılır — kritik bildirimin susması kabul edilemez.
    """
    dunya = Dunya(_an())
    dunya.kritik_aksiyon()
    dunya.eskalasyon.run()
    dunya.bildirim.dispatch(dunya.an)  # sürücü yok: failed

    dunya.an = dunya.an + SMS_AFTER + timedelta(minutes=1)
    sonuc = dunya.eskalasyon.run(dunya.an)

    assert sonuc["sms"] >= 1
    sms = [b for b in dunya.bildirim.list_notifications() if b.channel == "sms"]
    assert sms
    assert all(b.kind == "critical_failed" for b in sms)


def test_sms_on_dakika_dolmadan_tetiklenmez() -> None:
    dunya = Dunya(_an())
    dunya.kritik_aksiyon()
    dunya.eskalasyon.run()
    dunya.bildirim.dispatch(dunya.an)

    dunya.an = dunya.an + timedelta(minutes=5)
    assert dunya.eskalasyon.run(dunya.an)["sms"] == 0


def test_tc077_aksiyon_kapaninca_merdiven_durur() -> None:
    """FR-0914: kapanmış işin ardından bildirim gelmesi güveni aşındırır."""
    dunya = Dunya(_an())
    aksiyon = dunya.kritik_aksiyon()
    dunya.eskalasyon.run()

    kapali = replace(aksiyon, status="closed", closed_at=dunya.an, close_note="düzeltildi")  # type: ignore[arg-type]
    dunya.aksiyonlar.save_action(kapali)
    sonuc = dunya.eskalasyon.run()

    assert sonuc["stopped"] >= 1
    bekleyen = [b for b in dunya.bildirim.list_notifications() if b.status == "queued"]
    assert all(b.action_id != aksiyon.id for b in bekleyen)  # type: ignore[attr-defined]


def test_tc076_sube_muduru_yoksa_ust_adima_cikilir() -> None:
    """FR-0915: alıcı yoksa sessizce düşmez, bir üst adıma gider."""
    dunya = Dunya(_an())
    ayse = dunya.kullanicilar.user(AYSE)
    assert ayse is not None
    dunya.kullanicilar.save_user(replace(ayse, status="inactive"))
    dunya.kacir()

    dunya.eskalasyon.run()

    alicilar = dunya.alicilar("run_missed")
    assert AYSE not in alicilar
    assert MURAT in alicilar


# --- sabah özeti ------------------------------------------------------


def _ozet_ani() -> datetime:
    """07:00'den 10 dakika önce: özet hazırlama penceresi."""
    yerel = datetime(2026, 3, 2, DIGEST_AT.hour, 0, tzinfo=ZoneInfo(ISTANBUL)) - timedelta(
        minutes=10
    )
    return yerel.astimezone(UTC)


def test_br27_ozet_bolge_muduru_ve_yoneticiye_gider() -> None:
    dunya = Dunya(_ozet_ani())

    sayi = dunya.ozet.schedule()

    assert sayi > 0
    alicilar = dunya.alicilar("daily_digest")
    assert {MURAT, CEM} <= alicilar
    assert AYSE not in alicilar  # şube müdürüne kaçırma zaten anında gitti


def test_br27_ozet_push_ve_eposta_olarak_kuyruga_girer() -> None:
    dunya = Dunya(_ozet_ani())
    dunya.ozet.schedule()

    kanallar = {b.channel for b in dunya.bildirim.list_notifications() if b.kind == "daily_digest"}
    assert kanallar == {"push", "email"}


def test_br27_sorun_yoksa_her_sey_yolunda_denir() -> None:
    """Sessizlik iyi haberle bozuk entegrasyonu ayırt etmiyor: özet yine gider."""
    dunya = Dunya(_ozet_ani())
    dunya.ozet.schedule()

    ozetler = [b for b in dunya.bildirim.list_notifications() if b.kind == "daily_digest"]
    assert ozetler
    assert any("her şey yolunda" in b.title for b in ozetler)


def test_ozet_sorunlari_basliga_yazar() -> None:
    dunya = Dunya(_ozet_ani())
    dun = dunya.an.astimezone(ZoneInfo(ISTANBUL)).date() - timedelta(days=1)
    dunya.kacir(dun)

    dunya.ozet.schedule()

    ozetler = [b for b in dunya.bildirim.list_notifications() if b.kind == "daily_digest"]
    assert any("kaçırılan liste" in b.title for b in ozetler)


def test_ozet_gunde_bir_kez() -> None:
    dunya = Dunya(_ozet_ani())
    dunya.ozet.schedule()
    toplam = dunya.bildirim.counts()["total"]

    dunya.ozet.schedule()

    assert dunya.bildirim.counts()["total"] == toplam


def test_saati_gecmis_ozet_sonradan_gonderilmez() -> None:
    """Dünkü sabah özeti bugün öğlen gelirse okunmaz."""
    dunya = Dunya(_an())  # yerel öğlen
    assert dunya.ozet.schedule() == 0
