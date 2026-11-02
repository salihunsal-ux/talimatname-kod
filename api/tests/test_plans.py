"""Plan, çalıştırma üretimi ve durum testleri (ST-025, ST-026; TC-030…034, TC-037)."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime, time, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from conftest import oturum_ac
from talimatname.api.app import create_app
from talimatname.domain.plans import Assignment, Plan, Run, merge_runs, run_id
from talimatname.domain.validation import ValidationError
from talimatname.domain.window import Anchor, Window, WindowRule
from talimatname.infra.memory import (
    MemoryOrganizationRepository,
    MemoryPlanRepository,
    MemoryTemplateRepository,
    sabit_id,
)
from talimatname.services.plans import (
    BranchNotInScope,
    PlanNotFound,
    PlanService,
    TemplateNotPublished,
)
from talimatname.settings import Settings

KADIKOY = sabit_id("sube:KDK")
BESIKTAS = sabit_id("sube:BSK")
KAPANIS_SURUM = sabit_id("surum:kapanis:1")
ACILIS_TASLAK = sabit_id("surum:acilis:1")
BUGUN = date(2026, 11, 2)


def _servis(gun: date = BUGUN) -> PlanService:
    an = datetime.combine(gun, time(9, 0), tzinfo=UTC)
    return PlanService(
        MemoryPlanRepository(),
        MemoryOrganizationRepository(),
        MemoryTemplateRepository(),
        now=lambda: an,
    )


def _plan(**ek: object) -> Plan:
    alanlar: dict[str, object] = {
        "id": uuid4(),
        "name": "Test planı",
        "template_version_id": KAPANIS_SURUM,
        "branch_ids": (KADIKOY,),
        "rule": WindowRule(
            recurrence="FREQ=DAILY",
            starts_on=BUGUN,
            start_time=time(22, 0),
            duration_minutes=120,
            tolerance_minutes=30,
        ),
    }
    alanlar.update(ek)
    return Plan(**alanlar)  # type: ignore[arg-type]


# --- alan --------------------------------------------------------------


def test_subesiz_plan_olmaz() -> None:
    with pytest.raises(ValidationError, match="En az bir şube"):
        _plan(branch_ids=()).validated()


def test_ayni_sube_iki_kez_secilemez() -> None:
    with pytest.raises(ValidationError, match="iki kez"):
        _plan(branch_ids=(KADIKOY, KADIKOY)).validated()


def test_rol_atamasi_rol_ister() -> None:
    with pytest.raises(ValidationError, match="rol seçilmeli"):
        _plan(assignment=Assignment(kind="role")).validated()


def test_tc030_calistirma_kimligi_tekildir() -> None:
    """FR-0513: aynı pencere iki kez üretilse de tek çalıştırma olur."""
    servis = _servis()
    plan = servis.create(_plan())

    ilk = servis.preview(plan)
    ikinci = servis.preview(plan)

    assert [r.id for r in ilk] == [r.id for r in ikinci]
    assert len({r.id for r in ilk}) == len(ilk)


def test_durum_tolerans_bitince_kacirildi_olur() -> None:
    """BR-02/03: 'kaçırıldı' kaydedilen bir durum değil, zamandan türer."""
    run = Run(
        id=uuid4(),
        plan_id=uuid4(),
        template_version_id=KAPANIS_SURUM,
        branch_id=KADIKOY,
        business_day=BUGUN,
        window_start=datetime(2026, 11, 2, 19, 0, tzinfo=UTC),
        window_end=datetime(2026, 11, 2, 21, 0, tzinfo=UTC),
        tolerance_end=datetime(2026, 11, 2, 21, 30, tzinfo=UTC),
    )

    assert run.state_at(datetime(2026, 11, 2, 18, 0, tzinfo=UTC)) == ("scheduled", False)
    assert run.state_at(datetime(2026, 11, 2, 21, 29, tzinfo=UTC)) == ("scheduled", False)
    assert run.state_at(datetime(2026, 11, 2, 21, 30, tzinfo=UTC)) == ("missed", False)


def test_gonderilmis_calistirma_gec_isaretlenir() -> None:
    temel = Run(
        id=uuid4(),
        plan_id=uuid4(),
        template_version_id=KAPANIS_SURUM,
        branch_id=KADIKOY,
        business_day=BUGUN,
        window_start=datetime(2026, 11, 2, 19, 0, tzinfo=UTC),
        window_end=datetime(2026, 11, 2, 21, 0, tzinfo=UTC),
        tolerance_end=datetime(2026, 11, 2, 21, 30, tzinfo=UTC),
        status="submitted",
    )
    zamaninda = replace(temel, submitted_at=datetime(2026, 11, 2, 20, 55, tzinfo=UTC))
    gec = replace(temel, submitted_at=datetime(2026, 11, 2, 21, 20, tzinfo=UTC))
    sonra = datetime(2026, 11, 3, 9, 0, tzinfo=UTC)

    assert zamaninda.state_at(sonra) == ("submitted", False)
    assert gec.state_at(sonra) == ("submitted", True)


def test_tc037_baslanmis_calistirma_korunur() -> None:
    """FR-0516: plan değişince başlanmamışlar yeniden hesaplanır, ötekiler kalır."""
    ortak = {
        "plan_id": uuid4(),
        "template_version_id": KAPANIS_SURUM,
        "branch_id": KADIKOY,
        "business_day": BUGUN,
        "window_start": datetime(2026, 11, 2, 19, 0, tzinfo=UTC),
        "window_end": datetime(2026, 11, 2, 21, 0, tzinfo=UTC),
        "tolerance_end": datetime(2026, 11, 2, 21, 30, tzinfo=UTC),
    }
    baslanmis = Run(id=uuid4(), status="in_progress", **ortak)  # type: ignore[arg-type]
    baslanmamis = Run(id=uuid4(), **ortak)  # type: ignore[arg-type]

    kaydedilecek, silinecek = merge_runs([baslanmis, baslanmamis], [])

    assert kaydedilecek == []
    assert [r.id for r in silinecek] == [baslanmamis.id]


# --- servis ------------------------------------------------------------


def test_yayinda_olmayan_surume_plan_baglanamaz() -> None:
    with pytest.raises(TemplateNotPublished):
        _servis().create(_plan(template_version_id=ACILIS_TASLAK))


def test_olmayan_sube_reddedilir() -> None:
    with pytest.raises(BranchNotInScope):
        _servis().create(_plan(branch_ids=(uuid4(),)))


def test_olmayan_plan() -> None:
    with pytest.raises(PlanNotFound):
        _servis().get(uuid4())


def test_tc030_yedi_gunluk_ufuk_sube_basina_uretir() -> None:
    servis = _servis()
    plan = servis.create(_plan(branch_ids=(KADIKOY, BESIKTAS)))

    runs = servis.runs_for_day(BUGUN)
    hafta = [
        r
        for gun in range(7)
        for r in servis.runs_for_day(BUGUN + timedelta(days=gun))
        if r.plan_id == plan.id
    ]

    assert len(runs) >= 2
    assert len(hafta) == 14  # 2 şube × 7 gün


def test_uretim_idempotent() -> None:
    servis = _servis()
    plan = servis.create(_plan())

    ikinci = servis.generate(plan.id)

    assert ikinci == (0, 0)  # ikinci koşuda ne eklenir ne silinir


def test_plan_durdurulunca_baslanmamis_calistirmalar_silinir() -> None:
    servis = _servis()
    plan = servis.create(_plan())
    assert [r for r in servis.runs_for_day(BUGUN) if r.plan_id == plan.id]

    servis.set_active(plan.id, False)

    assert [r for r in servis.runs_for_day(BUGUN) if r.plan_id == plan.id] == []


def test_ileri_tarihli_planin_onizlemesi_bos_donmez() -> None:
    """Önizleme planın başlangıcından sayılır; bugünden değil."""
    servis = _servis()
    ileri = _plan(
        rule=WindowRule(
            recurrence="FREQ=DAILY",
            starts_on=BUGUN + timedelta(days=30),
            start_time=time(9, 0),
            duration_minutes=60,
        )
    )

    onizleme = servis.preview(ileri)

    assert len(onizleme) == 7
    assert onizleme[0].business_day == BUGUN + timedelta(days=30)


def test_pasif_subeye_calistirma_uretilmez() -> None:
    org = MemoryOrganizationRepository()
    sube = org.branch(KADIKOY)
    assert sube is not None
    org.save_branch(replace(sube, status="inactive"))
    servis = PlanService(
        MemoryPlanRepository(),
        org,
        MemoryTemplateRepository(),
        now=lambda: datetime.combine(BUGUN, time(9, 0), tzinfo=UTC),
    )

    plan = servis.create(_plan(branch_ids=(KADIKOY, BESIKTAS)))
    uretilen = {r.branch_id for r in servis.preview(plan)}

    assert uretilen == {BESIKTAS}


def test_kapanisa_cipali_plan_vardiya_gunune_yazilir() -> None:
    """Beşiktaş 01:00'de kapanıyor: pencere 00:00'da başlasa da iş günü dünkü vardiya."""
    servis = _servis()
    plan = servis.create(
        _plan(
            branch_ids=(BESIKTAS,),
            rule=WindowRule(
                recurrence="FREQ=DAILY",
                starts_on=BUGUN,
                anchor=Anchor("close", -60),
                duration_minutes=120,
            ),
        )
    )
    ilk = servis.preview(plan)[0]

    assert ilk.business_day == BUGUN
    assert ilk.window_start.isoformat() == "2026-11-02T21:00:00+00:00"  # 00:00 yerel


def test_run_id_plan_sube_ve_pencereye_bagli() -> None:
    """Aynı pencere + farklı şube = farklı kimlik; aynı ikili = aynı kimlik."""
    servis = _servis()
    plan = servis.create(_plan(branch_ids=(KADIKOY, BESIKTAS)))
    onizleme = servis.preview(plan)
    kadikoy = next(r for r in onizleme if r.branch_id == KADIKOY)
    besiktas = next(r for r in onizleme if r.branch_id == BESIKTAS)

    assert kadikoy.id != besiktas.id
    pencere = Window(
        business_day=kadikoy.business_day,
        window_start=kadikoy.window_start,
        window_end=kadikoy.window_end,
        tolerance_end=kadikoy.tolerance_end,
    )
    assert kadikoy.id == run_id(plan.id, KADIKOY, pencere)


# --- uç noktalar -------------------------------------------------------


@pytest.fixture
def istemci() -> TestClient:
    return oturum_ac(TestClient(create_app(Settings())))


def test_uc_nokta_plan_listesi(istemci: TestClient) -> None:
    yanit = istemci.get("/api/v1/plans")
    assert yanit.status_code == 200
    kapanis = next(p for p in yanit.json() if p["name"] == "Günlük kapanış")
    assert kapanis["branch_count"] == 3
    assert kapanis["recurrence"] == "FREQ=DAILY"
    assert kapanis["template_name"].startswith("Kapanış")


def test_tc031_onizleme_kaydetmeden_calisir(istemci: TestClient) -> None:
    surum = next(
        v
        for t in istemci.get("/api/v1/templates").json()
        for v in t["versions"]
        if v["status"] == "published"
    )
    sube = next(s for d in istemci.get("/api/v1/branches").json() for s in d["branches"])
    onceki_plan_sayisi = len(istemci.get("/api/v1/plans").json())

    yanit = istemci.post(
        "/api/v1/plans/preview",
        json={
            "name": "Haftalık derin temizlik",
            "template_version_id": surum["id"],
            "branch_ids": [sube["id"]],
            "schedule": {
                "repeat": "weekly",
                "weekdays": [0],
                "starts_on": "2026-11-02",
                "start_mode": "fixed",
                "start_time": "14:00",
                "duration_minutes": 180,
                "tolerance_minutes": 240,
            },
        },
    )

    assert yanit.status_code == 200
    assert yanit.json()["run_count"] == 1  # 7 günde bir Pazartesi
    assert yanit.json()["runs"][0]["branch_name"] == sube["name"]
    assert len(istemci.get("/api/v1/plans").json()) == onceki_plan_sayisi  # kaydetmedi


def _plan_govdesi(istemci: TestClient, **zamanlama: object) -> dict[str, object]:
    surum = next(
        v
        for t in istemci.get("/api/v1/templates").json()
        for v in t["versions"]
        if v["status"] == "published"
    )
    sube = next(s for d in istemci.get("/api/v1/branches").json() for s in d["branches"])
    temel = {
        "repeat": "daily",
        "starts_on": "2026-11-03",
        "start_mode": "fixed",
        "start_time": "09:00",
        "duration_minutes": 60,
        "tolerance_minutes": 0,
    }
    return {
        "name": "Sınır sınaması",
        "template_version_id": surum["id"],
        "branch_ids": [sube["id"]],
        "schedule": {**temel, **zamanlama},
    }


def _onizle(istemci: TestClient, **zamanlama: object) -> dict[str, object]:
    yanit = istemci.post("/api/v1/plans/preview", json=_plan_govdesi(istemci, **zamanlama))
    assert yanit.status_code == 200, yanit.text
    govde: dict[str, object] = yanit.json()
    return govde


# --- v1 tekrar biçimleri (FR-0503) ------------------------------------


def test_gunluk_birden_cok_saat(istemci: TestClient) -> None:
    """Saat listesi: gün içinde birden çok pencere.

    Motor eskiden pencerenin saatini `start_time`dan alıyordu; bu
    plan günde tek pencereye iniyordu.
    """
    govde = _onizle(istemci, times=["09:00", "14:30"])

    saatler = sorted({k["window_start"][11:16] for k in govde["runs"]})
    gunler = {k["business_day"] for k in govde["runs"]}

    assert len(saatler) == 2, saatler
    # Her iş gününde iki pencere: sayı, gün sayısının iki katı.
    assert len(govde["runs"]) == 2 * len(gunler)


def test_her_n_saat(istemci: TestClient) -> None:
    """08:00–14:00 arası her 2 saat → günde 4 pencere."""
    govde = _onizle(istemci, start_time="08:00", every_hours=2, until_time="14:00")

    ilk_gun = [k for k in govde["runs"] if k["business_day"] == govde["runs"][0]["business_day"]]
    assert len(ilk_gun) == 4, [k["window_start"] for k in ilk_gun]


def test_aylik_ayin_gunu(istemci: TestClient) -> None:
    govde = _onizle(istemci, repeat="monthly", month_day=15)

    assert all(k["business_day"].endswith("-15") for k in govde["runs"])


def test_aylik_ninci_hafta_gunu(istemci: TestClient) -> None:
    """Ayın ikinci Salı'sı gibi kurallar (FR-0503)."""
    govde = _onizle(istemci, repeat="monthly", month_nth=2, month_weekday=1)

    import datetime as _dt

    for kosu in govde["runs"]:
        gun = _dt.date.fromisoformat(kosu["business_day"])
        assert gun.weekday() == 1
        assert 8 <= gun.day <= 14  # ayın ikinci haftası


def test_bitis_tarihi(istemci: TestClient) -> None:
    """Bitiş tarihinden sonra çalıştırma üretilmez."""
    tam = _onizle(istemci, starts_on="2026-11-03")
    sinirli = _onizle(istemci, starts_on="2026-11-03", ends_on="2026-11-05")

    assert len(sinirli["runs"]) < len(tam["runs"])
    assert all(k["business_day"] <= "2026-11-05" for k in sinirli["runs"])


def test_aylik_plan_gun_kurali_istiyor(istemci: TestClient) -> None:
    yanit = istemci.post("/api/v1/plans/preview", json=_plan_govdesi(istemci, repeat="monthly"))

    assert yanit.status_code == 422
    assert "ayın günü" in yanit.text


def test_calisma_saatinden_turetilen_pencere_gun_icinde_tekrarlanamaz(
    istemci: TestClient,
) -> None:
    """Açılış/kapanış günde bir kez; ikisi birlikte anlamsız."""
    yanit = istemci.post(
        "/api/v1/plans/preview",
        json=_plan_govdesi(
            istemci,
            start_mode="anchor",
            anchor_reference="close",
            start_time=None,
            times=["09:00", "14:00"],
        ),
    )

    assert yanit.status_code == 422


def test_uc_nokta_tolerans_tavani(istemci: TestClient) -> None:
    """FR-0506: tolerans en çok 240 dk.

    Sınırsızken "Geç tamamlandı" ile "Kaçırıldı" arasındaki fark
    kalmıyordu: 16 saat sonra gönderilen liste de geç sayılıyordu.
    """
    yanit = istemci.post("/api/v1/plans", json=_plan_govdesi(istemci, tolerance_minutes=1000))

    assert yanit.status_code == 422, yanit.text
    assert any(h["alan"].endswith("tolerance_minutes") for h in yanit.json()["errors"])


def test_uc_nokta_pencere_ve_tolerans_toplami(istemci: TestClient) -> None:
    """FR-0504: pencere + tolerans ≤ 24 saat; yoksa ertesi günle çakışır."""
    yanit = istemci.post(
        "/api/v1/plans",
        json=_plan_govdesi(istemci, duration_minutes=1440, tolerance_minutes=240),
    )

    assert yanit.status_code == 422, yanit.text
    assert "1440" in yanit.text


def test_uc_nokta_sinirin_tam_ucu_kabul(istemci: TestClient) -> None:
    yanit = istemci.post(
        "/api/v1/plans",
        json=_plan_govdesi(istemci, duration_minutes=1200, tolerance_minutes=240),
    )

    assert yanit.status_code == 201, yanit.text


def test_uc_nokta_haftalik_planda_gun_secilmeli(istemci: TestClient) -> None:
    surum = next(
        v
        for t in istemci.get("/api/v1/templates").json()
        for v in t["versions"]
        if v["status"] == "published"
    )
    sube = next(s for d in istemci.get("/api/v1/branches").json() for s in d["branches"])

    yanit = istemci.post(
        "/api/v1/plans/preview",
        json={
            "name": "Eksik",
            "template_version_id": surum["id"],
            "branch_ids": [sube["id"]],
            "schedule": {
                "repeat": "weekly",
                "weekdays": [],
                "starts_on": "2026-11-02",
                "start_mode": "fixed",
                "start_time": "14:00",
                "duration_minutes": 180,
            },
        },
    )

    assert yanit.status_code == 422


def test_uc_nokta_gunun_calistirmalari(istemci: TestClient) -> None:
    yanit = istemci.get("/api/v1/runs")
    assert yanit.status_code == 200
    assert len(yanit.json()) >= 3  # tohum plan 3 şubede
    ilk = yanit.json()[0]
    assert ilk["status"] in ("scheduled", "in_progress", "submitted", "missed")
    assert ilk["branch_name"]
