"""Rapor testleri (ST-088, ST-145; FR-1207, FR-1208, FR-1220).

İki iddia sınanıyor: **sayılar tek tanımdan geliyor** (pano ile rapor
aynı güne aynı cevabı veriyor) ve **açık pencereler yüzdeyi bozmuyor**.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from conftest import oturum_ac
from talimatname.api.app import create_app
from talimatname.domain.answers import Answer
from talimatname.domain.plans import Run
from talimatname.domain.reports import Counters, measurement, outcome
from talimatname.domain.templates import Item
from talimatname.infra.memory import (
    MemoryAnswerRepository,
    MemoryOrganizationRepository,
    MemoryPlanRepository,
    MemoryTemplateRepository,
    sabit_id,
)
from talimatname.services.plans import PlanService
from talimatname.services.reports import ReportService
from talimatname.settings import Settings

AN = datetime(2026, 11, 20, 12, 0, tzinfo=UTC)
KADIKOY = sabit_id("sube:KDK")


def _kosu(
    gun: date,
    *,
    status: str = "submitted",
    gec: bool = False,
    result: str | None = "passed",
    branch_id: UUID = KADIKOY,
) -> Run:
    baslangic = datetime.combine(gun, datetime.min.time(), tzinfo=UTC) + timedelta(hours=22)
    return Run(
        id=uuid4(),
        plan_id=sabit_id("plan:kapanis"),
        template_version_id=sabit_id("surum:kapanis:1"),
        branch_id=branch_id,
        business_day=gun,
        window_start=baslangic,
        window_end=baslangic + timedelta(hours=2),
        tolerance_end=baslangic + timedelta(hours=4),
        status=status,  # type: ignore[arg-type]
        result=result,  # type: ignore[arg-type]
        submitted_at=(baslangic + timedelta(hours=3 if gec else 1))
        if status == "submitted"
        else None,
    )


class Dunya:
    def __init__(self) -> None:
        self.planlar = MemoryPlanRepository(seed=False)
        self.cevaplar = MemoryAnswerRepository()
        self.sablonlar = MemoryTemplateRepository()
        self.org = MemoryOrganizationRepository()
        self.servis = ReportService(
            self.planlar,
            self.cevaplar,
            self.sablonlar,
            self.org,
            now=lambda: AN,
        )

    def ekle(self, *kosular: Run) -> None:
        self.planlar.save_runs(list(kosular))

    def cevap(self, run: Run, item: Item, deger: object, *, state: str = "passed") -> None:
        self.cevaplar.save_answer(
            Answer(
                id=uuid4(),
                run_id=run.id,
                item_id=item.id,
                state=state,  # type: ignore[arg-type]
                value=deger,
                answered_at=run.submitted_at or run.window_start,
            )
        )


@pytest.fixture
def dunya() -> Dunya:
    return Dunya()


# --- alan: sayaçlar ---------------------------------------------------


def test_acik_pencere_yuzdeye_girmez() -> None:
    """Ayın ortasında henüz olmamış işi kayıp saymak raporu yanlış okutur."""
    sayac = Counters().plus("on_time", failed=False, not_done=0)
    sayac = sayac.plus("open", failed=False, not_done=0)
    sayac = sayac.plus("open", failed=False, not_done=0)

    assert sayac.total == 3
    assert sayac.closed == 1
    assert sayac.on_time_percent == 100


def test_olculecek_sey_yoksa_yuzde_yok() -> None:
    """Sıfır 'hiçbiri zamanında değil' demek olurdu."""
    assert Counters().on_time_percent is None
    assert Counters().plus("open", failed=False, not_done=0).on_time_percent is None


def test_sonuc_panonun_turetmesiyle_ayni() -> None:
    gun = date(2026, 11, 2)
    assert outcome(_kosu(gun), AN) == "on_time"
    assert outcome(_kosu(gun, gec=True), AN) == "late"
    assert outcome(_kosu(gun, status="scheduled", result=None), AN) == "missed"
    assert outcome(_kosu(gun, status="cancelled", result=None), AN) == "cancelled"
    # Toleransı dolmamış, bugünün açık penceresi: kayıp değil.
    bugun = _kosu(AN.date(), status="scheduled", result=None)
    assert outcome(replace(bugun, tolerance_end=AN + timedelta(hours=2)), AN) == "open"


def test_olcum_sayiya_cevrilemezse_atlanir() -> None:
    """Denetime giden günlükte 'bilinmiyor' satırı olmamalı."""
    gun = date(2026, 11, 2)
    run = _kosu(gun)
    madde = Item(id=uuid4(), order=1, type="temperature", title="Dolap", min_value=0, max_value=4)
    cevap = Answer(id=uuid4(), run_id=run.id, item_id=madde.id, state="passed", value="ölçülemedi")

    assert measurement(cevap, madde, run) is None
    assert measurement(replace(cevap, value=3.5), madde, run) is not None


def test_aralik_disi_iki_yondende_isaretlenir() -> None:
    gun = date(2026, 11, 2)
    run = _kosu(gun)
    madde = Item(id=uuid4(), order=1, type="temperature", title="Dolap", min_value=0, max_value=4)

    def olc(deger: float) -> bool:
        cevap = Answer(id=uuid4(), run_id=run.id, item_id=madde.id, state="passed", value=deger)
        nokta = measurement(cevap, madde, run)
        assert nokta is not None
        return nokta.out_of_range

    assert olc(2.0) is False
    assert olc(6.0) is True
    assert olc(-1.0) is True


# --- servis: aylık özet ----------------------------------------------


def test_aylik_ozet_sayar_ve_sube_kirilimini_verir(dunya: Dunya) -> None:
    kasim = date(2026, 11, 1)
    dunya.ekle(
        _kosu(kasim + timedelta(days=1)),
        _kosu(kasim + timedelta(days=2), gec=True),
        _kosu(kasim + timedelta(days=3), status="scheduled", result=None),
        _kosu(kasim + timedelta(days=4), result="failed"),
        _kosu(kasim + timedelta(days=5), branch_id=sabit_id("sube:USK")),
    )

    ozet = dunya.servis.monthly(2026, 11)

    assert ozet.counters.total == 5
    assert ozet.counters.on_time == 3  # 2 Kadıköy + 1 Üsküdar
    assert ozet.counters.late == 1
    assert ozet.counters.missed == 1
    assert ozet.counters.failed == 1
    assert ozet.counters.on_time_percent == 60
    assert {s.branch_code for s in ozet.branches} == {"KDK", "USK"}


def test_aylik_ozet_ayin_disina_bakmaz(dunya: Dunya) -> None:
    dunya.ekle(_kosu(date(2026, 10, 31)), _kosu(date(2026, 11, 1)), _kosu(date(2026, 12, 1)))

    ozet = dunya.servis.monthly(2026, 11)

    assert ozet.counters.total == 1
    assert ozet.first_day == date(2026, 11, 1)
    assert ozet.last_day == date(2026, 11, 30)


def test_en_kotu_sube_once_gelir(dunya: Dunya) -> None:
    """Denetim konuşması 'hangi şube' sorusuyla başlıyor."""
    kasim = date(2026, 11, 1)
    dunya.ekle(
        _kosu(kasim + timedelta(days=1)),
        _kosu(kasim + timedelta(days=2)),
        _kosu(kasim + timedelta(days=1), gec=True, branch_id=sabit_id("sube:USK")),
        _kosu(kasim + timedelta(days=2), gec=True, branch_id=sabit_id("sube:USK")),
    )

    ozet = dunya.servis.monthly(2026, 11)

    assert [s.branch_code for s in ozet.worst_branches] == ["USK", "KDK"]
    assert ozet.worst_branches[0].counters.on_time_percent == 0


def test_yapilamadi_maddeleri_sayilir(dunya: Dunya) -> None:
    run = _kosu(date(2026, 11, 2))
    dunya.ekle(run)
    madde = Item(id=uuid4(), order=1, type="confirm", title="Zemin")
    dunya.cevap(run, madde, None, state="not_done")
    dunya.cevap(run, madde, None, state="passed")

    ozet = dunya.servis.monthly(2026, 11)

    assert ozet.counters.not_done_items == 1


def test_kapsam_disi_sube_rapora_girmez(dunya: Dunya) -> None:
    dunya.ekle(_kosu(date(2026, 11, 2)), _kosu(date(2026, 11, 2), branch_id=sabit_id("sube:USK")))

    ozet = dunya.servis.monthly(2026, 11, branch_ids={KADIKOY})

    assert ozet.counters.total == 1
    assert [s.branch_code for s in ozet.branches] == ["KDK"]


# --- servis: ölçüm günlüğü -------------------------------------------


def _sicaklik_maddesi(dunya: Dunya) -> Item:
    surum = dunya.sablonlar.version(sabit_id("surum:kapanis:1"))
    assert surum is not None
    return next(m for m in surum.items if m.type == "temperature")


def test_olcum_gunlugu_seriye_gruplar(dunya: Dunya) -> None:
    madde = _sicaklik_maddesi(dunya)
    kosular = [_kosu(date(2026, 11, gun)) for gun in (2, 3, 4)]
    dunya.ekle(*kosular)
    for run, deger in zip(kosular, (3.0, 3.5, 7.0), strict=True):
        dunya.cevap(run, madde, deger)

    seriler = dunya.servis.measurements(first_day=date(2026, 11, 1), last_day=date(2026, 11, 30))

    assert len(seriler) == 1
    seri = seriler[0]
    assert seri.item_title == madde.title
    assert [n.value for n in seri.points] == [3.0, 3.5, 7.0]
    assert seri.out_of_range_count == 1
    assert seri.points[-1].out_of_range is True


def test_olcum_gunlugu_yalnizca_aralik_disi(dunya: Dunya) -> None:
    madde = _sicaklik_maddesi(dunya)
    kosular = [_kosu(date(2026, 11, gun)) for gun in (2, 3)]
    dunya.ekle(*kosular)
    dunya.cevap(kosular[0], madde, 3.0)
    dunya.cevap(kosular[1], madde, 9.0)

    seriler = dunya.servis.measurements(
        first_day=date(2026, 11, 1), last_day=date(2026, 11, 30), only_out_of_range=True
    )

    assert [n.value for n in seriler[0].points] == [9.0]


def test_aralik_disi_olan_seri_once_gelir(dunya: Dunya) -> None:
    surum = dunya.sablonlar.version(sabit_id("surum:kapanis:1"))
    assert surum is not None
    sicaklik = next(m for m in surum.items if m.type == "temperature")
    run = _kosu(date(2026, 11, 2))
    dunya.ekle(run)
    dunya.cevap(run, sicaklik, 9.0)
    ikinci = replace(sicaklik, id=uuid4(), title="Başka dolap")
    dunya.sablonlar.save_version(replace(surum, sections=(*surum.sections[:1], surum.sections[1])))
    dunya.cevap(run, ikinci, 2.0)

    seriler = dunya.servis.measurements(first_day=date(2026, 11, 1), last_day=date(2026, 11, 30))

    assert seriler[0].out_of_range_count >= 1


# --- uç noktalar ------------------------------------------------------


def _istemci(tmp: Path, rol: str = "admin") -> TestClient:
    return oturum_ac(TestClient(create_app(Settings(evidence_dir=str(tmp)))), rol)


def test_uc_nokta_aylik_ozet(tmp_path: Path) -> None:
    bugun = datetime.now(UTC).date()
    istemci = _istemci(tmp_path)

    yanit = istemci.get(
        "/api/v1/reports/monthly", params={"year": bugun.year, "month": bugun.month}
    )

    assert yanit.status_code == 200
    govde = yanit.json()
    assert govde["month_name"]
    assert govde["counters"]["total"] >= 0
    assert "on_time_percent" in govde["counters"]


def test_uc_nokta_gecersiz_ay_reddedilir(tmp_path: Path) -> None:
    yanit = _istemci(tmp_path).get("/api/v1/reports/monthly", params={"year": 2026, "month": 13})

    assert yanit.status_code == 422


def test_uc_nokta_olcum_gunlugu(tmp_path: Path) -> None:
    bugun = datetime.now(UTC).date()
    istemci = _istemci(tmp_path)

    yanit = istemci.get(
        "/api/v1/reports/measurements",
        params={"first_day": str(bugun - timedelta(days=7)), "last_day": str(bugun)},
    )

    assert yanit.status_code == 200
    assert isinstance(yanit.json(), list)


def test_uc_nokta_galeri(tmp_path: Path) -> None:
    bugun = datetime.now(UTC).date()
    istemci = _istemci(tmp_path)

    yanit = istemci.get(
        "/api/v1/reports/gallery",
        params={"first_day": str(bugun - timedelta(days=7)), "last_day": str(bugun)},
    )

    assert yanit.status_code == 200
    assert isinstance(yanit.json(), list)


def test_uc_nokta_personel_kapsamiyla_suzuluyor(tmp_path: Path) -> None:
    """Personel yalnızca kendi şubesini görür (FR-0205)."""
    bugun = datetime.now(UTC).date()
    personel = _istemci(tmp_path, "staff")

    govde = personel.get(
        "/api/v1/reports/monthly", params={"year": bugun.year, "month": bugun.month}
    ).json()

    assert all(s["branch_code"] == "KDK" for s in govde["branches"])


def test_plan_servisi_ile_ayni_gercek(tmp_path: Path) -> None:
    """Rapor ile pano aynı güne aynı cevabı vermeli: tek türetme."""
    planlar = MemoryPlanRepository()
    org = MemoryOrganizationRepository()
    sablonlar = MemoryTemplateRepository()
    PlanService(planlar, org, sablonlar, now=lambda: AN).generate_all()
    servis = ReportService(planlar, MemoryAnswerRepository(), sablonlar, org, now=lambda: AN)

    ozet = servis.monthly(AN.year, AN.month)
    kosular = [r for r in planlar.runs() if r.business_day.month == AN.month]

    assert ozet.counters.total == len(kosular)
    assert ozet.counters.open + ozet.counters.closed + ozet.counters.cancelled == len(kosular)


# --- PDF uç noktaları (FR-1220, FR-1214) ------------------------------


def _pdf_metni(baytlar: bytes) -> str:
    from io import BytesIO

    from pypdf import PdfReader

    return "\n".join(s.extract_text() or "" for s in PdfReader(BytesIO(baytlar)).pages)


def test_uc_nokta_aylik_pdf(tmp_path: Path) -> None:
    bugun = datetime.now(UTC).date()

    yanit = _istemci(tmp_path).get(
        "/api/v1/reports/monthly.pdf", params={"year": bugun.year, "month": bugun.month}
    )

    assert yanit.status_code == 200
    assert yanit.headers["content-type"] == "application/pdf"
    assert "attachment" in yanit.headers["content-disposition"]
    assert ".pdf" in yanit.headers["content-disposition"]
    assert yanit.content.startswith(b"%PDF")


def test_uc_nokta_olcum_pdf(tmp_path: Path) -> None:
    bugun = datetime.now(UTC).date()

    yanit = _istemci(tmp_path).get(
        "/api/v1/reports/measurements.pdf",
        params={"first_day": str(bugun - timedelta(days=7)), "last_day": str(bugun)},
    )

    assert yanit.status_code == 200
    assert yanit.content.startswith(b"%PDF")


def test_pdf_ekranla_ayni_kapsami_kullanir(tmp_path: Path) -> None:
    """Personelin PDF'i de yalnızca kendi şubesini içerir (FR-0205).

    Kâğıt kendi sorgusunu yazsa kapsam süzgeci atlanabilirdi: denetime
    giden belge, ekranda görünenden fazlasını gösterirdi.
    """
    bugun = datetime.now(UTC).date()
    personel = _istemci(tmp_path, "staff")

    ekran = personel.get(
        "/api/v1/reports/monthly", params={"year": bugun.year, "month": bugun.month}
    ).json()
    kagit = personel.get(
        "/api/v1/reports/monthly.pdf", params={"year": bugun.year, "month": bugun.month}
    )

    assert kagit.status_code == 200
    assert all(s["branch_code"] == "KDK" for s in ekran["branches"])
    assert "BSK" not in _pdf_metni(kagit.content)


def test_pdf_gecersiz_ay_reddedilir(tmp_path: Path) -> None:
    yanit = _istemci(tmp_path).get("/api/v1/reports/monthly.pdf", params={"year": 2026, "month": 0})

    assert yanit.status_code == 422
