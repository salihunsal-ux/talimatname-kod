"""Zamanlayıcı testleri (ST-027; TC-034)."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, time, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from conftest import oturum_ac
from talimatname import scheduler as zamanlayici
from talimatname.api.app import create_app
from talimatname.domain.plans import Run
from talimatname.infra.memory import (
    MemoryEvidenceRepository,
    MemoryOrganizationRepository,
    MemoryPlanRepository,
    MemoryTemplateRepository,
    MemoryUserRepository,
    sabit_id,
)
from talimatname.services.evidence import EvidenceService
from talimatname.services.plans import PlanService
from talimatname.services.scheduler import SchedulerService
from talimatname.services.storage import LocalObjectStore
from talimatname.settings import Settings

BESIKTAS = sabit_id("sube:BSK")


def _calistirma(depo: MemoryPlanRepository, run_id: UUID) -> Run:
    return next(r for r in depo.runs() if r.id == run_id)


def _zamanlayici(an: datetime | None = None) -> tuple[SchedulerService, MemoryPlanRepository]:
    depo = MemoryPlanRepository()
    simdi = an or datetime.now(UTC)
    servis = SchedulerService(
        depo,
        MemoryOrganizationRepository(),
        MemoryTemplateRepository(),
        now=lambda: simdi,
    )
    return servis, depo


def test_tur_ufku_uretir_ve_ikinci_turda_sessizdir() -> None:
    """Üretim idempotent: ikinci tur ne ekler ne siler."""
    servis, _ = _zamanlayici()

    ilk = servis.tick()
    ikinci = servis.tick()

    assert ilk.created > 0
    assert ikinci.created == 0
    assert ikinci.deleted == 0
    assert ikinci.quiet is True


def test_tolerans_dolan_calistirma_kacirildi_yazilir() -> None:
    """FR-0514: kaçırma bir olaydır; aksiyon ve bildirim için kalıcı yazılır."""
    servis, depo = _zamanlayici()
    dun = sabit_id(
        f"calistirma:sube:BSK:{(datetime.now(UTC).date() - timedelta(days=1)).isoformat()}"
    )

    assert _calistirma(depo, dun).status == "scheduled"

    sonuc = servis.tick()

    assert sonuc.missed >= 1
    assert _calistirma(depo, dun).status == "missed"


def test_gonderilmis_calistirmaya_dokunulmaz() -> None:
    servis, depo = _zamanlayici()
    dun = datetime.now(UTC).date() - timedelta(days=1)
    gonderilen = sabit_id(f"calistirma:sube:KDK:{dun.isoformat()}")

    servis.tick()

    assert _calistirma(depo, gonderilen).status == "submitted"


def test_yapilmayacak_isaretli_calistirma_kacirilmaz() -> None:
    """İlk tur geçmişi kapatır; ölçüm **ikinci** turda.

    Tek turda ölçseydik sonuç saate bağlı olurdu: gece yarısından
    sonra tohumun başka çalıştırmaları da kaçırılmış sayılıyor ve
    `missed == 0` beklentisi tutmuyordu.
    """
    servis, depo = _zamanlayici()
    servis.tick()

    dun = datetime.now(UTC).date() - timedelta(days=1)
    hedef = _calistirma(depo, sabit_id(f"calistirma:sube:BSK:{dun.isoformat()}"))
    depo.save_run(replace(hedef, status="cancelled", cancel_reason="Şube kapalıydı"))

    sonuc = servis.tick()

    assert _calistirma(depo, hedef.id).status == "cancelled"
    assert sonuc.missed == 0


def test_penceresi_acik_calistirma_kacirilmaz() -> None:
    """Tolerans bitmeden kapanış yapılmaz."""
    bugun = datetime.now(UTC).date()
    an = datetime.combine(bugun, time(12, 0), tzinfo=UTC)
    servis, depo = _zamanlayici(an)

    servis.tick()
    bugunku = [r for r in depo.runs() if r.business_day == bugun]

    assert bugunku
    assert all(r.status == "scheduled" for r in bugunku)


def test_kapanis_kendi_basina_cagrilabilir() -> None:
    servis, depo = _zamanlayici()
    ileri = datetime.now(UTC) + timedelta(days=30)

    servis.tick()  # ufku üret
    sayac = servis.close_expired(ileri)

    assert sayac > 0
    assert all(r.status != "scheduled" for r in depo.runs())


# --- bekleyen kanıt süpürücüsü ----------------------------------------


def test_tur_bekleyen_kaniti_supuruyor(tmp_path: Path) -> None:
    """Süpürücü turun parçası: kimse elle çağırmayacak.

    Baytı gelmemiş kayıt özet kilidini (FR-0614) tutuyor; kilidi
    açacak tek yer zamanlayıcı.
    """
    gecmis = datetime.now(UTC) - timedelta(days=30)
    saat = [gecmis]  # kayıt geçmişte açılıyor, süpürme bugün koşuyor
    planlar = MemoryPlanRepository()
    org = MemoryOrganizationRepository()
    PlanService(planlar, org, MemoryTemplateRepository(), now=lambda: gecmis).generate_all()
    kanitlar = MemoryEvidenceRepository()
    kanit_servisi = EvidenceService(
        kanitlar,
        planlar,
        org,
        LocalObjectStore(tmp_path),
        MemoryUserRepository(),
        settings=Settings(environment="dev"),
        now=lambda: saat[0],
    )
    kanit_servisi.start(
        run_id=planlar.runs()[0].id,
        answer_id=uuid4(),
        item_id=sabit_id("madde:1"),
        sha256="a" * 64,
        content_type="image/jpeg",
        size_bytes=1024,
    )
    saat[0] = datetime.now(UTC)

    servis = SchedulerService(
        planlar,
        org,
        MemoryTemplateRepository(),
        evidence=kanit_servisi,
        now=lambda: datetime.now(UTC),
    )
    sonuc = servis.tick()

    assert sonuc.swept == 1
    assert kanitlar.evidences() == []


# --- uç nokta ---------------------------------------------------------


@pytest.fixture
def istemci() -> TestClient:
    return oturum_ac(TestClient(create_app(Settings())))


def test_uc_nokta_tur_ozeti_doner(istemci: TestClient) -> None:
    yanit = istemci.post("/api/v1/scheduler/tick")

    assert yanit.status_code == 200
    govde = yanit.json()
    assert {"at", "created", "deleted", "missed"} <= set(govde)
    assert govde["created"] >= 0


def test_uc_nokta_ikinci_tur_bos_doner(istemci: TestClient) -> None:
    istemci.post("/api/v1/scheduler/tick")
    ikinci = istemci.post("/api/v1/scheduler/tick").json()

    assert ikinci["created"] == 0
    assert ikinci["deleted"] == 0


# --- nabız (kap sağlık kontrolü) -------------------------------------
#
# Zamanlayıcı bir HTTP sunucusu değil: imajın `curl :8000` kontrolünü
# miras alınca 5 gün boyunca "unhealthy" göründü, oysa turlar dönüyordu.
# Nabız dosyası her **başarılı** turdan sonra tazeleniyor.


def test_nabiz_taze_dosya_saglikli(tmp_path: Path) -> None:
    an = datetime(2026, 11, 7, 20, 0, tzinfo=UTC)
    nabiz = tmp_path / "nabiz"
    zamanlayici.nabiz_yaz(nabiz, an)

    assert zamanlayici.nabiz_denetle(nabiz, 200, an + timedelta(seconds=90)) == 0


def test_nabiz_bayatlayinca_sagliksiz(tmp_path: Path) -> None:
    an = datetime(2026, 11, 7, 20, 0, tzinfo=UTC)
    nabiz = tmp_path / "nabiz"
    zamanlayici.nabiz_yaz(nabiz, an)

    assert zamanlayici.nabiz_denetle(nabiz, 200, an + timedelta(seconds=201)) == 1


def test_nabiz_yoksa_sagliksiz(tmp_path: Path) -> None:
    assert zamanlayici.nabiz_denetle(tmp_path / "hic-yok", 200) == 1


def test_bozuk_nabiz_sagliksiz(tmp_path: Path) -> None:
    nabiz = tmp_path / "nabiz"
    nabiz.write_text("bu bir tarih degil", encoding="utf-8")

    assert zamanlayici.nabiz_denetle(nabiz, 200) == 1


def test_nabiz_yazilamiyorsa_tur_dusmez(tmp_path: Path) -> None:
    """Dosya yazılamazsa uyarı kalır, süreç devam eder."""
    zamanlayici.nabiz_yaz(tmp_path / "olmayan-klasor" / "nabiz")


def test_tek_tur_nabiz_birakir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    nabiz = tmp_path / "nabiz"
    monkeypatch.setattr(zamanlayici, "tek_tur", lambda: 0)

    assert zamanlayici.main(["--once", "--nabiz", str(nabiz)]) == 0
    assert zamanlayici.nabiz_yasi(nabiz) is not None


def test_denetim_veritabanina_baglanmaz(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Sağlık kontrolü saniyede bir koşabilir: tur servisini kurmamalı."""

    def patlasin() -> None:
        raise AssertionError("sağlık kontrolü tur koşmamalı")

    monkeypatch.setattr(zamanlayici, "tek_tur", patlasin)

    assert zamanlayici.main(["--nabiz-denetle", str(tmp_path / "yok")]) == 1
