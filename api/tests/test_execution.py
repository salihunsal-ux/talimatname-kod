"""Cevap yazma ve gönderim testleri (ST-030, ST-033; TC-040, TC-045, TC-114)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from conftest import oturum_ac
from talimatname.api.app import create_app
from talimatname.domain.actions import from_critical_item
from talimatname.domain.answers import RunLocked, clock_skew
from talimatname.infra.memory import (
    MemoryActionRepository,
    MemoryAnswerRepository,
    MemoryOrganizationRepository,
    MemoryPlanRepository,
    MemoryTemplateRepository,
    sabit_id,
)
from talimatname.services.execution import (
    ExecutionService,
    ItemNotInTemplate,
    RunClosed,
    SubmissionIncomplete,
    WindowClosed,
)
from talimatname.services.plans import PlanService
from talimatname.settings import Settings

KAPANIS_SURUM = sabit_id("surum:kapanis:1")


def _kurulum(
    an: datetime | None = None,
) -> tuple[ExecutionService, UUID, MemoryPlanRepository, datetime]:
    """Bugünün ilk çalıştırmasını penceresi açıkken ele alır."""
    plan_deposu = MemoryPlanRepository()
    org = MemoryOrganizationRepository()
    sablonlar = MemoryTemplateRepository()
    PlanService(plan_deposu, org, sablonlar).generate_all()
    run = sorted(
        (r for r in plan_deposu.runs() if r.status == "scheduled"),
        key=lambda r: r.window_start,
    )[0]
    simdi = an or (run.window_start + timedelta(minutes=5))
    servis = ExecutionService(MemoryAnswerRepository(), plan_deposu, sablonlar, now=lambda: simdi)
    return servis, run.id, plan_deposu, simdi


def _cevapla(servis: ExecutionService, run_id: UUID, **ek: object) -> None:
    """Tüm cevaplanabilir maddeleri geçer olarak işaretler."""
    gorunum = servis.view(run_id)
    for madde in gorunum.version.items:
        if not madde.scored:
            continue
        servis.write_answer(
            run_id=run_id,
            answer_id=uuid4(),
            item_id=madde.id,
            state="passed",
            evidence_count=1 if madde.photo_required else 0,
            **ek,  # type: ignore[arg-type]
        )


# --- alan --------------------------------------------------------------


def test_br13_cihaz_saati_sapmasi_hesaplanir() -> None:
    sunucu = datetime(2026, 11, 2, 22, 0, tzinfo=UTC)

    assert clock_skew(sunucu, None) is None
    assert clock_skew(sunucu, sunucu + timedelta(minutes=25)) == 25
    assert clock_skew(sunucu, sunucu - timedelta(minutes=3)) == -3


def test_br13_buyuk_sapma_bayraklanir() -> None:
    servis, run_id, _, an = _kurulum()
    an = servis._now()
    madde = next(m for m in servis.view(run_id).version.items if m.scored)

    cevap = servis.write_answer(
        run_id=run_id,
        answer_id=uuid4(),
        item_id=madde.id,
        state="passed",
        device_reported_at=an + timedelta(minutes=40),
    )

    assert cevap.clock_skew_minutes == 40
    assert cevap.clock_flagged is True


# --- yazma -------------------------------------------------------------


def test_tc040_cevap_yazma_idempotent() -> None:
    """ADR-0013 devir sözleşmesi: aynı kimlikle ikinci yazma kayıt açmaz."""
    servis, run_id, _, _ = _kurulum()
    madde = next(m for m in servis.view(run_id).version.items if m.scored)
    kimlik = uuid4()

    servis.write_answer(run_id=run_id, answer_id=kimlik, item_id=madde.id, state="passed")
    servis.write_answer(run_id=run_id, answer_id=kimlik, item_id=madde.id, state="failed")

    cevaplar = servis.view(run_id).answers
    assert len(cevaplar) == 1
    assert cevaplar[madde.id].state == "failed"  # son yazan kazanır


def test_ilk_cevap_calistirmayi_devam_ediyora_cevirir() -> None:
    servis, run_id, plan_deposu, _ = _kurulum()
    madde = next(m for m in servis.view(run_id).version.items if m.scored)

    servis.write_answer(run_id=run_id, answer_id=uuid4(), item_id=madde.id, state="passed")

    assert next(r for r in plan_deposu.runs() if r.id == run_id).status == "in_progress"


def test_fr0521_calistirmayi_ilk_acan_alir() -> None:
    servis, run_id, _, _ = _kurulum()
    madde = next(m for m in servis.view(run_id).version.items if m.scored)
    emre, zeynep = uuid4(), uuid4()

    servis.write_answer(
        run_id=run_id, answer_id=uuid4(), item_id=madde.id, state="passed", user_id=emre
    )

    with pytest.raises(RunLocked):
        servis.write_answer(
            run_id=run_id, answer_id=uuid4(), item_id=madde.id, state="passed", user_id=zeynep
        )


def test_sablonda_olmayan_madde_reddedilir() -> None:
    servis, run_id, _, _ = _kurulum()
    with pytest.raises(ItemNotInTemplate):
        servis.write_answer(run_id=run_id, answer_id=uuid4(), item_id=uuid4(), state="passed")


def test_tc045_tolerans_bitince_yazilamaz() -> None:
    servis, run_id, _, _ = _kurulum()
    gorunum = servis.view(run_id)
    gec = ExecutionService(
        MemoryAnswerRepository(),
        _kurulum()[2],
        MemoryTemplateRepository(),
        now=lambda: gorunum.run.tolerance_end + timedelta(minutes=1),
    )
    madde = next(m for m in gorunum.version.items if m.scored)

    with pytest.raises(WindowClosed):
        gec.write_answer(run_id=run_id, answer_id=uuid4(), item_id=madde.id, state="passed")


# --- gönderim ----------------------------------------------------------


def test_tc114_basarisiz_cevapta_kanit_ve_not_zorunlu() -> None:
    """Sabit kural (FR-0405): başarısızda fotoğraf + not olmadan gönderilemez."""
    servis, run_id, _, _ = _kurulum()
    _cevapla(servis, run_id)
    madde = next(m for m in servis.view(run_id).version.items if m.scored)
    servis.write_answer(
        run_id=run_id, answer_id=uuid4(), item_id=madde.id, state="failed", evidence_count=0
    )

    eksikler = {(e.kind) for e in servis.view(run_id).blockers}

    assert eksikler == {"evidence", "note"}


def test_eksik_varken_gonderim_reddedilir_ve_listeyi_doner() -> None:
    servis, run_id, _, _ = _kurulum()

    with pytest.raises(SubmissionIncomplete) as hata:
        servis.submit(run_id)

    assert hata.value.extra["missing"]
    assert hata.value.extra["missing"][0]["kind"] == "unanswered"


def test_tc040_gonderim_puani_ve_sonucu_sunucuda_hesaplar() -> None:
    servis, run_id, plan_deposu, _ = _kurulum()
    _cevapla(servis, run_id)

    gonderilen = servis.submit(run_id)

    assert gonderilen.status == "submitted"
    assert gonderilen.result == "passed"
    assert gonderilen.score_percent == 100
    assert next(r for r in plan_deposu.runs() if r.id == run_id).submitted_at is not None


def test_kritik_madde_basarisizsa_sonuc_basarisiz() -> None:
    servis, run_id, _, _ = _kurulum()
    _cevapla(servis, run_id)
    kritik = next(m for m in servis.view(run_id).version.items if m.critical)
    servis.write_answer(
        run_id=run_id,
        answer_id=uuid4(),
        item_id=kritik.id,
        state="failed",
        evidence_count=1,
        note="Sıcaklık 9 derece, teknisyen çağrıldı",
    )

    gonderilen = servis.submit(run_id)

    assert gonderilen.result == "failed"
    assert gonderilen.score_percent is not None
    assert gonderilen.score_percent < 100


def test_gonderilmis_calistirmaya_tekrar_yazilamaz() -> None:
    servis, run_id, _, _ = _kurulum()
    _cevapla(servis, run_id)
    servis.submit(run_id)
    madde = next(m for m in servis.view(run_id).version.items if m.scored)

    with pytest.raises(RunClosed):
        servis.write_answer(run_id=run_id, answer_id=uuid4(), item_id=madde.id, state="passed")


def test_gonderim_kilidi_birakir() -> None:
    servis, run_id, _, _ = _kurulum()
    kullanici = uuid4()
    _cevapla(servis, run_id, user_id=kullanici)

    servis.submit(run_id, user_id=kullanici)

    assert servis.view(run_id).lock is None


# --- uç noktalar -------------------------------------------------------


@pytest.fixture
def istemci() -> TestClient:
    return oturum_ac(TestClient(create_app(Settings())))


def test_uc_nokta_gorunum_maddeleri_ve_eksikleri_doner(istemci: TestClient) -> None:
    run = istemci.get("/api/v1/runs").json()[0]

    yanit = istemci.get(f"/api/v1/runs/{run['id']}")

    assert yanit.status_code == 200
    govde = yanit.json()
    assert govde["template_name"].startswith("Kapanış")
    assert len(govde["sections"]) == 2
    assert govde["blockers"]
    talimat = next(m for b in govde["sections"] for m in b["items"] if m["type"] == "instruction")
    assert talimat["type_label"] == "Talimat"


def test_uc_nokta_cevap_ve_gonderim(istemci: TestClient) -> None:
    run = istemci.get("/api/v1/runs").json()[0]
    gorunum = istemci.get(f"/api/v1/runs/{run['id']}").json()

    for bolum in gorunum["sections"]:
        for madde in bolum["items"]:
            if madde["type"] == "instruction":
                continue
            istemci.put(
                f"/api/v1/runs/{run['id']}/answers/{uuid4()}",
                json={
                    "item_id": madde["item_id"],
                    "state": "passed",
                    "evidence_count": 1 if madde["photo_required"] else 0,
                },
            )

    yanit = istemci.post(f"/api/v1/runs/{run['id']}/submit", json={})

    assert yanit.status_code == 200
    assert yanit.json()["status"] == "submitted"
    assert yanit.json()["score_percent"] == 100


def test_uc_nokta_eksik_gonderim_422_ve_eksik_listesi(istemci: TestClient) -> None:
    run = istemci.get("/api/v1/runs").json()[1]

    yanit = istemci.post(f"/api/v1/runs/{run['id']}/submit", json={})

    assert yanit.status_code == 422
    govde = yanit.json()
    assert govde["type"] == "urn:talimatname:gonderim-eksik"
    assert govde["missing"][0]["kind"] == "unanswered"


# --- kritik madde → aksiyon (FR-0405, BR-08) --------------------------


def _kritik_kurulum() -> tuple[ExecutionService, UUID, MemoryActionRepository, datetime]:
    plan_deposu = MemoryPlanRepository()
    org = MemoryOrganizationRepository()
    sablonlar = MemoryTemplateRepository()
    aksiyonlar = MemoryActionRepository()
    PlanService(plan_deposu, org, sablonlar).generate_all()
    run = sorted(
        (r for r in plan_deposu.runs() if r.status == "scheduled"),
        key=lambda r: r.window_start,
    )[0]
    simdi = run.window_start + timedelta(minutes=5)
    servis = ExecutionService(
        MemoryAnswerRepository(), plan_deposu, sablonlar, aksiyonlar, now=lambda: simdi
    )
    return servis, run.id, aksiyonlar, simdi


def _kritik_basarisiz_gonder(servis: ExecutionService, run_id: UUID) -> int:
    """Kritik maddeleri başarısız, kalanını geçer işaretleyip gönderir."""
    gorunum = servis.view(run_id)
    kritik = 0
    for madde in gorunum.version.items:
        if not madde.scored:
            continue
        basarisiz = madde.critical
        kritik += int(basarisiz)
        servis.write_answer(
            run_id=run_id,
            answer_id=uuid4(),
            item_id=madde.id,
            state="failed" if basarisiz else "passed",
            note="sıcaklık yüksek" if basarisiz else None,
            evidence_count=1 if (madde.photo_required or basarisiz) else 0,
        )
    servis.submit(run_id)
    return kritik


def test_br08_kritik_madde_basarisizsa_aksiyon_acilir() -> None:
    servis, run_id, aksiyonlar, _ = _kritik_kurulum()

    kritik_sayisi = _kritik_basarisiz_gonder(servis, run_id)

    acilan = [a for a in aksiyonlar.actions() if a.source == "critical_item"]
    assert kritik_sayisi > 0
    assert len(acilan) == kritik_sayisi
    assert all(a.priority == "critical" for a in acilan)


def test_br10_kritik_aksiyonun_vadesi_dort_saat() -> None:
    servis, run_id, aksiyonlar, _ = _kritik_kurulum()
    _kritik_basarisiz_gonder(servis, run_id)

    aksiyon = next(a for a in aksiyonlar.actions() if a.source == "critical_item")

    assert aksiyon.due_at - aksiyon.opened_at == timedelta(hours=4)


def test_kritik_aksiyon_kimligi_calistirma_ve_maddeden_turer() -> None:
    """Cevap kimliği cihazda üretiliyor; ondan türeseydi senkte kopya doğardı."""
    an = datetime.now(UTC)
    run_a, run_b, madde = uuid4(), uuid4(), uuid4()
    ortak = {
        "branch_id": uuid4(),
        "item_title": "Buzdolabı sıcaklığı",
        "plan_name": "Günlük kapanış",
        "now": an,
    }

    birinci = from_critical_item(run_id=run_a, item_id=madde, **ortak)  # type: ignore[arg-type]
    ikinci = from_critical_item(run_id=run_a, item_id=madde, **ortak)  # type: ignore[arg-type]
    baska = from_critical_item(run_id=run_b, item_id=madde, **ortak)  # type: ignore[arg-type]

    assert birinci.id == ikinci.id
    assert birinci.id != baska.id


def test_kritik_madde_gecerse_aksiyon_acilmaz() -> None:
    servis, run_id, aksiyonlar, _ = _kritik_kurulum()
    _cevapla(servis, run_id)
    servis.submit(run_id)

    assert [a for a in aksiyonlar.actions() if a.source == "critical_item"] == []
