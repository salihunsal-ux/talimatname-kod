"""Saatlik tuvalet kontrolü: şablon, plan önerisi ve kaçırma gruplaması.

Üçü birlikte yazıldı. Şablon tek başına eklenseydi ürünün en gürültülü
parçası yedi katına çıkardı: günde iki listede 149 açık "kaçırılan
liste" aksiyonu varken, saatlik liste şubede günde yedi çalıştırma
demek. Bir öğleden sonrayı atlayan şube tek ihmal için 4–6 aksiyon
üretirdi ve aksiyon listesi okunamaz hâle gelirdi.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from conftest import oturum_ac
from talimatname.api.app import create_app
from talimatname.domain.actions import from_missed_runs, missed_run_source
from talimatname.domain.plans import Run
from talimatname.infra.memory import (
    MemoryActionRepository,
    MemoryOrganizationRepository,
    MemoryPlanRepository,
)
from talimatname.services.actions import ActionService
from talimatname.services.library import TUVALET
from talimatname.settings import Settings

AN = datetime(2026, 11, 11, 23, 0, tzinfo=UTC)


# --- şablon -----------------------------------------------------------


def test_sablon_urun_belgesindeki_sayilari_tutuyor() -> None:
    """02-urun/07 §3: 7 madde, kritik yok, fotoğraf isteğe bağlı."""
    maddeler = [m for b in TUVALET.sections for m in b.items]

    assert len(maddeler) == 7
    assert not any(m.critical for m in maddeler)
    foto = next(m for m in maddeler if m.type == "photo")
    assert foto.required is False


def test_sablon_sube_saatine_baglanmiyor() -> None:
    """Gün içi tekrar sabit saat ister: açılış/kapanış günde bir kez."""
    assert TUVALET.plan.anchor is None
    assert TUVALET.plan.start_time == time(10, 0)


# --- plan önerisi -----------------------------------------------------


def test_her_iki_saatte_bir_pencere() -> None:
    """10:00–22:00 arası her 2 saat: yedi pencere."""
    saatler = [s.strftime("%H:%M") for s in TUVALET.plan.saatler()]

    assert saatler == ["10:00", "12:00", "14:00", "16:00", "18:00", "20:00", "22:00"]


def test_rrule_saat_basina_bir_satir() -> None:
    """`BYHOUR=10,12` yazmak dakikası farklı saatlerde yanlış pencere üretir."""
    satirlar = TUVALET.plan.rrule().splitlines()

    assert len(satirlar) == 7
    assert satirlar[0] == "RRULE:FREQ=DAILY;BYHOUR=10;BYMINUTE=0"


def test_tek_pencereli_sablon_tekrar_dizgesini_bozmuyor() -> None:
    from talimatname.services.library import KAPANIS

    assert KAPANIS.plan.rrule() == KAPANIS.plan.recurrence


def test_capa_ve_sabit_saat_birlikte_olmaz() -> None:
    from talimatname.domain.window import Anchor
    from talimatname.services.library import PlanDefaults

    with pytest.raises(ValueError, match="birlikte olmaz"):
        PlanDefaults(
            anchor=Anchor("open", 0),
            start_time=time(10, 0),
            duration_minutes=15,
            tolerance_minutes=0,
        )


def test_uc_nokta_oneri_saatlik_cikiyor(tmp_path: Path) -> None:
    istemci = oturum_ac(TestClient(create_app(Settings(evidence_dir=str(tmp_path)))), "admin")
    surum = istemci.post("/api/v1/setup/template", json={"key": "tuvalet-hijyen"}).json()

    oneri = istemci.get(f"/api/v1/setup/plan-proposal?version_id={surum['version_id']}").json()

    assert oneri["anchor_reference"] is None
    assert oneri["start_time"].startswith("10:00")
    assert len(oneri["recurrence"].splitlines()) == 7
    assert oneri["window"].startswith("Günlük · 10:00 · gün içinde 7 pencere")


def test_tekrar_adi_cok_satirli_rrule_ile_bozulmuyor() -> None:
    """Dizginin tamamı etiket sanılıyordu: pencere metni RRULE kusuyordu."""
    from talimatname.api.routers.setup import _tekrar_adi
    from talimatname.services.library import DENETIM, KAPANIS

    assert _tekrar_adi(TUVALET.plan.rrule()) == "Günlük"
    assert _tekrar_adi(KAPANIS.plan.rrule()) == "Günlük"
    assert _tekrar_adi(DENETIM.plan.rrule()) == "Aylık"


def test_uc_nokta_kutuphanede_pencere_metni(tmp_path: Path) -> None:
    istemci = oturum_ac(TestClient(create_app(Settings(evidence_dir=str(tmp_path)))), "admin")

    kutuphane = istemci.get("/api/v1/setup/library").json()

    tuvalet = next(s for s in kutuphane if s["key"] == "tuvalet-hijyen")
    assert tuvalet["item_count"] == 7
    assert "10:00–22:00 arası her 2 saat" in tuvalet["window"]


# --- kaçırma gruplaması -----------------------------------------------


def _kacirilan(plan_id: UUID, sube_id: UUID, gun: date, saat: int) -> Run:
    baslangic = datetime(gun.year, gun.month, gun.day, saat, tzinfo=UTC)
    return Run(
        id=uuid4(),
        plan_id=plan_id,
        template_version_id=uuid4(),
        branch_id=sube_id,
        business_day=gun,
        window_start=baslangic,
        window_end=baslangic + timedelta(minutes=15),
        tolerance_end=baslangic + timedelta(minutes=15),
        status="missed",
    )


def test_ayni_gun_yedi_kacirma_tek_aksiyon() -> None:
    """Satır çoğalmıyor, başlık sayıyı söylüyor."""
    planlar = MemoryPlanRepository()
    aksiyonlar = MemoryActionRepository()
    sube = MemoryOrganizationRepository().branches()[0].id
    plan_id = planlar.plans()[0].id
    gun = date(2026, 11, 10)
    for saat in range(10, 23, 2):
        planlar.save_run(_kacirilan(plan_id, sube, gun, saat))

    servis = ActionService(aksiyonlar, MemoryOrganizationRepository(), planlar, now=lambda: AN)
    servis.sync_from_runs()

    kacirma = [a for a in aksiyonlar.actions() if a.source == "missed_run"]
    bugunku = [
        a
        for a in kacirma
        if a.id
        == from_missed_runs(
            branch_id=sube, plan_id=plan_id, plan_name="x", business_day=gun, count=7, now=AN
        ).id
    ]
    assert len(bugunku) == 1
    assert "7 kez yapılmadı" in bugunku[0].title


def test_ikinci_tur_yeni_aksiyon_acmiyor_vadeyi_uzatmiyor() -> None:
    planlar = MemoryPlanRepository()
    aksiyonlar = MemoryActionRepository()
    sube = MemoryOrganizationRepository().branches()[0].id
    plan_id = planlar.plans()[0].id
    gun = date(2026, 11, 10)
    planlar.save_run(_kacirilan(plan_id, sube, gun, 10))
    servis = ActionService(aksiyonlar, MemoryOrganizationRepository(), planlar, now=lambda: AN)
    servis.sync_from_runs()
    kaynak = missed_run_source(sube, plan_id, gun)
    ilk = next(a for a in aksiyonlar.actions() if a.source_id == kaynak)

    planlar.save_run(_kacirilan(plan_id, sube, gun, 12))
    gec = ActionService(
        aksiyonlar, MemoryOrganizationRepository(), planlar, now=lambda: AN + timedelta(hours=3)
    )
    acilan = gec.sync_from_runs()

    sonra = next(a for a in aksiyonlar.actions() if a.source_id == kaynak)
    assert acilan == 0
    assert sonra.due_at == ilk.due_at  # vade ilk kaçırmadan sayılıyor
    assert "2 kez yapılmadı" in sonra.title


def test_kapatilmis_aksiyon_yeniden_acilmiyor() -> None:
    """Müdür kapattıysa o gün için karar verilmiş demektir."""
    from dataclasses import replace

    planlar = MemoryPlanRepository()
    aksiyonlar = MemoryActionRepository()
    sube = MemoryOrganizationRepository().branches()[0].id
    plan_id = planlar.plans()[0].id
    gun = date(2026, 11, 10)
    planlar.save_run(_kacirilan(plan_id, sube, gun, 10))
    servis = ActionService(aksiyonlar, MemoryOrganizationRepository(), planlar, now=lambda: AN)
    servis.sync_from_runs()
    kaynak = missed_run_source(sube, plan_id, gun)
    acik = next(a for a in aksiyonlar.actions() if a.source_id == kaynak)
    aksiyonlar.save_action(replace(acik, status="closed", close_note="konuşuldu"))

    planlar.save_run(_kacirilan(plan_id, sube, gun, 12))
    servis.sync_from_runs()

    kapali = next(a for a in aksiyonlar.actions() if a.source_id == kaynak)
    assert kapali.status == "closed"
    assert "2 kez" not in kapali.title
