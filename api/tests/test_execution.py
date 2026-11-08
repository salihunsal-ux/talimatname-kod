"""Cevap yazma ve gönderim testleri (ST-030, ST-033; TC-040, TC-045, TC-114)."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from conftest import json_madde_degeri, madde_degeri, oturum_ac
from talimatname.api.app import create_app
from talimatname.domain.actions import from_critical_item
from talimatname.domain.answers import LOCK_MINUTES, clock_skew
from talimatname.domain.errors import RunLocked
from talimatname.domain.templates import Item
from talimatname.domain.validation import ValidationError
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
    WindowNotOpen,
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
            value=madde_degeri(madde, "passed"),
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
        value=madde_degeri(kritik, "failed"),
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
def istemci(tmp_path: Path) -> TestClient:
    """Kanıt dosyaları geçici dizine: depo testten kirlenmesin."""
    return oturum_ac(TestClient(create_app(Settings(evidence_dir=str(tmp_path)))))


def _surum_degerleri(istemci: TestClient, run_id: str) -> dict[str, object]:
    """Madde kimliği → maddeyi geçiren değer, **istemcinin yolundan**.

    Seçenek etiketleri çalıştırma görünümünde yok: cihaz şablon sürümünü
    manifestten öğrenip bir kez indiriyor ve önbelleğe alıyor
    (`ManifestSurumu`). Test de aynı yolu izliyor — yoksa sunucunun
    seçenek denetimi (BR-06) sınanmış sayılmaz.
    """
    manifest = istemci.get("/api/v1/sync/manifest").json()
    surum_id = next(k["template_version_id"] for k in manifest["runs"] if k["run_id"] == run_id)
    surum = istemci.get(f"/api/v1/template-versions/{surum_id}").json()
    return {
        madde["id"]: json_madde_degeri(madde, "passed")
        for bolum in surum["sections"]
        for madde in bolum["items"]
    }


def _acik_calistirma(istemci: TestClient) -> dict[str, object]:
    """Yazılabilir bir çalıştırma seçer: **penceresi hâlâ açık** olan.

    Listenin ilkini körlemesine almak testi duvar saatine bağlıyordu:
    gece yarısından sonra ilk sıradaki çalıştırmanın toleransı dolmuş
    oluyor ve yazma 409 dönüyordu (CI de bu saatte kırmızı yanardı).

    İki uçlu bakılır. Eskiden yalnızca tolerans bitişi denetleniyordu;
    pencereye daha saatler varken de "açık" sayılıyordu — sunucu buna
    izin verdiği için test geçiyordu. `pencere-acilmadi` kuralı
    geldiğinde ortaya çıktı (bağımsız test turu Y-1).
    """
    simdi = datetime.now(UTC)
    acik = [
        k
        for k in istemci.get("/api/v1/runs").json()
        if datetime.fromisoformat(k["writable_from"]) <= simdi
        and datetime.fromisoformat(k["tolerance_end"]) > simdi
        and k["status"] in ("scheduled", "in_progress")
    ]
    if acik:
        return acik[0]  # type: ignore[no-any-return]
    return _simdi_acik_calistirma_kur(istemci)


def _simdi_acik_calistirma_kur(istemci: TestClient) -> dict[str, object]:
    """Şu an yazılabilir bir çalıştırma **üretir**.

    Tohumdaki pencereler sabit saatlerde; testi hangi saatte koştuğuna
    bağlamamak için gerektiğinde penceresi şu anı kapsayan bir plan
    kuruluyor ve zamanlayıcı elle çevriliyor.

    Plan açmak yönetici işi, ama bu yardımcıyı şube müdürü de çağırıyor:
    kurulum süresince belirteç geçici olarak yöneticiye çevrilip
    çağıranın belirteci geri takılıyor.
    """
    # Şube **çağıranın kapsamından** seçilir: yöneticiye çevirip ilk
    # şubeyi almak, şube müdürünü kendi göremediği bir çalıştırmayla
    # bırakıyordu (403).
    #
    # Şubeler **sırayla** deneniyor: ilkini körlemesine almak testi
    # şubenin çalışma takvimine bağlıyordu. Haftada 6 gün açık bir şube
    # (tohumda Ataşehir ve Bornova) kapalı gününde çalıştırma üretmez
    # (BR-17) ve plan kurulsa bile liste boş dönerdi — süit yalnızca
    # pazar günleri kırmızı yanardı.
    subeler = [s for d in istemci.get("/api/v1/branches").json() for s in d["branches"]]
    cagiranin_belirteci = istemci.headers.get("Authorization")
    for sira, sube in enumerate(subeler):
        oturum_ac(istemci, "admin")
        try:
            _yazilabilir_plan_kur(istemci, sube["id"], sira)
        finally:
            if cagiranin_belirteci is not None:
                istemci.headers["Authorization"] = cagiranin_belirteci
        acik = _yazilabilir_varsa(istemci)
        if acik is not None:
            return acik
    raise AssertionError("hiçbir şubede yazılabilir çalıştırma kurulamadı (hepsi kapalı mı?)")


def _yazilabilir_varsa(istemci: TestClient) -> dict[str, object] | None:
    """Şu an yazılabilir çalıştırma; yoksa None (çağıran başka şube dener)."""
    simdi = datetime.now(UTC)
    acik = [
        k
        for k in istemci.get("/api/v1/runs").json()
        if datetime.fromisoformat(k["writable_from"]) <= simdi
        and datetime.fromisoformat(k["tolerance_end"]) > simdi
        and k["status"] in ("scheduled", "in_progress")
    ]
    return acik[0] if acik else None  # type: ignore[no-any-return]


def _yazilabilir_plan_kur(istemci: TestClient, sube_id: str, sira: int = 0) -> None:
    surum = next(
        v
        for t in istemci.get("/api/v1/templates").json()
        for v in t["versions"]
        if v["status"] == "published"
    )
    yerel = datetime.now(ZoneInfo("Europe/Istanbul"))
    basla = (yerel - timedelta(minutes=30)).replace(second=0, microsecond=0)

    plan = istemci.post(
        "/api/v1/plans",
        json={
            "name": f"Yazılabilir pencere (test {sira})",
            "template_version_id": surum["id"],
            "branch_ids": [sube_id],
            "schedule": {
                "repeat": "daily",
                "starts_on": basla.date().isoformat(),
                "start_mode": "fixed",
                "start_time": basla.strftime("%H:%M"),
                "duration_minutes": 240,
                "tolerance_minutes": 60,
            },
        },
    )
    assert plan.status_code in (200, 201), plan.text
    tur = istemci.post("/api/v1/scheduler/tick")
    assert tur.status_code in (200, 201), tur.text


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


def test_gorunum_sube_adini_doner(istemci: TestClient) -> None:
    """Kart kendi başına "hangi şube" sorusuna cevap verebilmeli.

    Panoda detay ızgaranın altında açılıyor; yanıtta yalnızca
    `branch_id` varken ekranda şubeyi gösterecek hiçbir şey yoktu ve
    üç şubenin kartı birbirinin aynısı görünüyordu.
    """
    run = istemci.get("/api/v1/runs").json()[0]

    govde = istemci.get(f"/api/v1/runs/{run['id']}").json()

    sube = istemci.get(f"/api/v1/branches/{govde['branch_id']}").json()
    assert govde["branch_name"] == sube["name"]
    assert govde["branch_name"]


def test_uc_nokta_cevap_ve_gonderim(istemci: TestClient) -> None:
    """Gönderim kanıtı **sayar**, cihazın beyanına bakmaz (FR-0607).

    Cevapta "1 fotoğraf var" yazması yetmiyor: fotoğraf depoda ve
    özeti doğrulanmış olmalı. Çevrimdışı yolda beyan dosyadan saatler
    önce geliyor (ST-054); gönderimi beyana açmak, kanıtlı listenin
    tek iddiasını istemciye bırakmak olurdu.
    """
    run = _acik_calistirma(istemci)
    gorunum = istemci.get(f"/api/v1/runs/{run['id']}").json()
    degerler = _surum_degerleri(istemci, str(run["id"]))

    cevap_idleri: dict[str, str] = {}
    fotograf_isteyen: list[str] = []
    for bolum in gorunum["sections"]:
        for madde in bolum["items"]:
            if madde["type"] == "instruction":
                continue
            cevap_id = str(uuid4())
            cevap_idleri[madde["item_id"]] = cevap_id
            if madde["photo_required"]:
                fotograf_isteyen.append(madde["item_id"])
            yazma = istemci.put(
                f"/api/v1/runs/{run['id']}/answers/{cevap_id}",
                json={
                    "item_id": madde["item_id"],
                    "state": "passed",
                    "value": degerler[madde["item_id"]],
                    # Beyan: cihaz "fotoğraf çektim" diyor, henüz yüklemedi.
                    "evidence_count": 1 if madde["photo_required"] else 0,
                },
            )
            assert yazma.status_code == 200, yazma.text

    assert fotograf_isteyen, "tohumda fotoğraf zorunlu madde yok"
    erken = istemci.post(f"/api/v1/runs/{run['id']}/submit", json={})
    assert erken.status_code == 422
    assert {e["kind"] for e in erken.json()["missing"]} == {"evidence"}

    for madde_id in fotograf_isteyen:
        icerik = f"sahte-jpeg-{madde_id}".encode()
        izin = istemci.post(
            f"/api/v1/runs/{run['id']}/answers/{cevap_idleri[madde_id]}/evidence",
            json={
                "item_id": madde_id,
                "sha256": hashlib.sha256(icerik).hexdigest(),
                "content_type": "image/jpeg",
                "size_bytes": len(icerik),
            },
        ).json()
        assert istemci.put(izin["upload_url"], content=icerik).status_code == 200
        assert (
            istemci.post(f"/api/v1/evidence/{izin['evidence']['id']}/complete").status_code == 200
        )

    yanit = istemci.post(f"/api/v1/runs/{run['id']}/submit", json={})

    assert yanit.status_code == 200
    assert yanit.json()["status"] == "submitted"
    assert yanit.json()["score_percent"] == 100


def test_uc_nokta_eksik_gonderim_422_ve_eksik_listesi(istemci: TestClient) -> None:
    run = _acik_calistirma(istemci)

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
        durum = "failed" if basarisiz else "passed"
        servis.write_answer(
            run_id=run_id,
            answer_id=uuid4(),
            item_id=madde.id,
            state=durum,
            value=madde_degeri(madde, durum),
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


# --- Yapılmayacak (FR-0514, TC-038) -----------------------------------


def test_tc038_yapilmayacak_sebeple_isaretlenir(istemci: TestClient) -> None:
    """Planlandı bir çalıştırma, sebebiyle birlikte iptal edilir."""
    mudur = oturum_ac(istemci, "branch_manager")
    kosu = _acik_calistirma(mudur)["id"]

    yanit = mudur.post(f"/api/v1/runs/{kosu}/cancel", json={"reason": "Şube su baskını"})

    assert yanit.status_code == 200, yanit.text
    assert yanit.json()["status"] == "cancelled"
    assert mudur.get(f"/api/v1/runs/{kosu}").json()["status"] == "cancelled"


def test_yapilmayacak_sebep_istiyor(istemci: TestClient) -> None:
    """Sebepsiz iptal, denetimde kaçırılmış listeden ayırt edilemez."""
    mudur = oturum_ac(istemci, "branch_manager")
    kosu = _acik_calistirma(mudur)["id"]

    yanit = mudur.post(f"/api/v1/runs/{kosu}/cancel", json={"reason": "   "})

    assert yanit.status_code == 422, yanit.text


def test_gonderilmis_calistirma_iptal_edilemez(istemci: TestClient) -> None:
    """Gönderilmiş listeyi iptal etmek kanıtı geçersiz kılmak olurdu."""
    mudur = oturum_ac(istemci, "branch_manager")
    kosu = _acik_calistirma(mudur)["id"]
    mudur.post(f"/api/v1/runs/{kosu}/cancel", json={"reason": "ilk iptal"})

    ikinci = mudur.post(f"/api/v1/runs/{kosu}/cancel", json={"reason": "yine"})

    assert ikinci.status_code == 409, ikinci.text


def test_personel_yapilmayacak_diyemez(istemci: TestClient) -> None:
    """Rol matrisi: "Yapılmayacak" müdür yetkisi."""
    mudur = oturum_ac(istemci, "branch_manager")
    kosu = _acik_calistirma(mudur)["id"]
    personel = oturum_ac(istemci, "staff")

    yanit = personel.post(f"/api/v1/runs/{kosu}/cancel", json={"reason": "olmaz"})

    assert yanit.status_code == 403


def test_pencere_acilmadan_cevap_yazilamaz() -> None:
    """Y-1: liste penceresinden (hazırlık payı dahil) önce doldurulamaz.

    Bulunduğunda sunucu alt sınır denetlemiyordu: akşam 00:00'da açılacak
    kapanış listesi sabah 11:00'de doldurulabiliyordu. "Pencere içi
    tamamlandı" ölçüsü (FR-1203) buna dayandığı için kural kesin.
    """
    planlar = MemoryPlanRepository()
    sablonlar = MemoryTemplateRepository()
    PlanService(planlar, MemoryOrganizationRepository(), sablonlar).generate_all()

    kosu = next(r for r in planlar.runs() if r.status == "scheduled")
    an = kosu.window_start - timedelta(minutes=30)
    servis = ExecutionService(
        MemoryAnswerRepository(), planlar, sablonlar, now=lambda: an, prep_minutes=15
    )
    surum = sablonlar.version(kosu.template_version_id)
    assert surum is not None
    madde = next(m for m in surum.items if m.scored and not m.critical)

    def yaz(zaman: datetime) -> None:
        nonlocal an
        an = zaman
        servis.write_answer(run_id=kosu.id, answer_id=uuid4(), item_id=madde.id, state="passed")

    # Payın dışında: reddedilir.
    with pytest.raises(WindowNotOpen):
        yaz(kosu.window_start - timedelta(minutes=30))

    # Payın tam ucunda bile henüz erken (pay 15 dk).
    with pytest.raises(WindowNotOpen):
        yaz(kosu.window_start - timedelta(minutes=16))

    # Payın içinde: kabul.
    yaz(kosu.window_start - timedelta(minutes=5))

    # Pencere içinde: kabul.
    yaz(kosu.window_start + timedelta(minutes=5))


def test_hazirlik_payi_sifirken_pencere_tam_zamaninda_acilir() -> None:
    """Pay 0 ise açılış tam pencere başlangıcı: bir saniye öncesi bile erken."""
    planlar = MemoryPlanRepository()
    sablonlar = MemoryTemplateRepository()
    PlanService(planlar, MemoryOrganizationRepository(), sablonlar).generate_all()
    kosu = next(r for r in planlar.runs() if r.status == "scheduled")

    assert kosu.writable_from(0) == kosu.window_start
    assert kosu.writable_from(15) == kosu.window_start - timedelta(minutes=15)


# --- BR-06: sonucu sunucu hesaplar (bağımsız test turu B02) -------------


def _olculen_madde(servis: ExecutionService, run_id: UUID) -> Item:
    madde = next(
        (m for m in servis.view(run_id).version.items if m.type in ("temperature", "number")),
        None,
    )
    assert madde is not None, "tohumda ölçüm maddesi yok"
    assert madde.min_value is not None
    assert madde.max_value is not None
    return madde


def _yaz(servis: ExecutionService, run_id: UUID, madde: Item, **ek: object) -> object:
    return servis.write_answer(
        run_id=run_id,
        answer_id=uuid4(),
        item_id=madde.id,
        **ek,  # type: ignore[arg-type]
    )


def test_br06_aralik_disi_olcum_istemci_gecti_dese_de_basarisiz() -> None:
    """İstemcinin iddiası sonucu belirlemiyor (B02).

    Hatalı bir istemci sürümü ya da elle kurulmuş bir istek, aralık
    dışı ölçümü "geçti" diye yazarsa liste %100 puan alır ve denetim
    izi yalan söyler. Sonuç şablon sürümünden çıkıyor.
    """
    servis, run_id, _, _ = _kurulum()
    madde = _olculen_madde(servis, run_id)

    cevap = _yaz(servis, run_id, madde, state="passed", value=(madde.max_value or 0) + 95)

    assert cevap.state == "failed"  # type: ignore[attr-defined]


def test_br06_aralik_ici_olcum_istemci_basarisiz_dese_de_gecer() -> None:
    """Kural iki yönlü: sunucu suçlamayı da düzeltir."""
    servis, run_id, _, _ = _kurulum()
    madde = _olculen_madde(servis, run_id)
    orta = ((madde.min_value or 0) + (madde.max_value or 0)) / 2

    cevap = _yaz(servis, run_id, madde, state="failed", value=orta)

    assert cevap.state == "passed"  # type: ignore[attr-defined]


def test_br06_aralik_sinirlari_dahildir() -> None:
    """Rapordaki kabul ölçütü: 4,0 geçer, 4,1 geçmez."""
    servis, run_id, _, _ = _kurulum()
    madde = _olculen_madde(servis, run_id)
    ust = madde.max_value or 0

    assert _yaz(servis, run_id, madde, state="passed", value=ust).state == "passed"  # type: ignore[attr-defined]
    assert _yaz(servis, run_id, madde, state="passed", value=madde.min_value).state == "passed"  # type: ignore[attr-defined]
    assert _yaz(servis, run_id, madde, state="passed", value=ust + 0.1).state == "failed"  # type: ignore[attr-defined]


def test_br06_tam_olcum_tam_sayi_kalir() -> None:
    """`6` saklanır, `6.0` değil: uydurma hassasiyet okuyanı yanıltır."""
    servis, run_id, _, _ = _kurulum()
    madde = _olculen_madde(servis, run_id)

    cevap = _yaz(servis, run_id, madde, state="passed", value=float(madde.max_value or 0))

    assert cevap.value == int(madde.max_value or 0)  # type: ignore[attr-defined]
    assert isinstance(cevap.value, int)  # type: ignore[attr-defined]


@pytest.mark.parametrize("deger", [None, "altı", True, float("inf"), float("nan"), [4], {}])
def test_br06_olcum_sayi_degilse_reddedilir(deger: object) -> None:
    """Sayı olmayan, sonsuz ve eksik ölçüm sunucuda durur."""
    servis, run_id, _, _ = _kurulum()
    madde = _olculen_madde(servis, run_id)

    with pytest.raises(ValidationError) as hata:
        _yaz(servis, run_id, madde, state="passed", value=deger)

    assert hata.value.field_name == "value"


def test_br06_ondalik_virgulle_de_okunur() -> None:
    """Çevrimdışı istemci ondalığı virgülle gönderebilir."""
    servis, run_id, _, _ = _kurulum()
    madde = _olculen_madde(servis, run_id)
    disarida = f"{(madde.max_value or 0) + 5},5"

    cevap = _yaz(servis, run_id, madde, state="passed", value=disarida)

    assert cevap.state == "failed"  # type: ignore[attr-defined]
    assert cevap.value == (madde.max_value or 0) + 5.5  # type: ignore[attr-defined]


def test_br06_secim_sonucu_secenegin_gecer_bayragindan_cikar() -> None:
    servis, run_id, _, _ = _kurulum()
    madde = next(m for m in servis.view(run_id).version.items if m.type == "choice")
    kalmaz = next(s for s in madde.options if not s.passing)

    cevap = _yaz(servis, run_id, madde, state="passed", value=kalmaz.label)

    assert cevap.state == "failed"  # type: ignore[attr-defined]


def test_br06_sablonda_olmayan_secenek_reddedilir() -> None:
    servis, run_id, _, _ = _kurulum()
    madde = next(m for m in servis.view(run_id).version.items if m.type == "choice")

    with pytest.raises(ValidationError):
        _yaz(servis, run_id, madde, state="passed", value="Belki")


def test_br06_metin_cevabi_bos_olamaz() -> None:
    servis, run_id, _, _ = _kurulum()
    madde = next(m for m in servis.view(run_id).version.items if m.type == "text")

    with pytest.raises(ValidationError):
        _yaz(servis, run_id, madde, state="passed", value="   ")


def test_br06_talimat_satiri_cevaplanmaz() -> None:
    """FR-0306: talimat bilgi verir, cevap beklemez."""
    servis, run_id, _, _ = _kurulum()
    madde = next(m for m in servis.view(run_id).version.items if m.type == "instruction")

    with pytest.raises(ValidationError) as hata:
        _yaz(servis, run_id, madde, state="passed")

    assert hata.value.field_name == "item_id"


def test_br06_yapilamadi_beyani_yanindaki_olcumu_dusurur() -> None:
    """Beyanın yanında duran bir ölçüm okuyanı yanıltır."""
    servis, run_id, _, _ = _kurulum()
    # Tohumdaki tek ölçüm maddesi kritik, kritik madde de atlanamaz
    # (BR-09): beyanı kritik olmayan bir maddede sınıyoruz.
    madde = next(m for m in servis.view(run_id).version.items if m.scored and not m.critical)

    cevap = _yaz(
        servis,
        run_id,
        madde,
        state="not_done",
        value=99,
        not_done_reason="no_material",
        note="Termometre arızalı",
    )

    assert cevap.state == "not_done"  # type: ignore[attr-defined]
    assert cevap.value is None  # type: ignore[attr-defined]


def test_br06_uc_noktada_da_sunucu_karar_veriyor(istemci: TestClient) -> None:
    """Aynı kural HTTP yolunda: cevap 200 döner ama durumu düzeltilmiş."""
    run = _acik_calistirma(istemci)
    gorunum = istemci.get(f"/api/v1/runs/{run['id']}").json()
    madde = next(
        m
        for bolum in gorunum["sections"]
        for m in bolum["items"]
        if m["type"] in ("temperature", "number") and m["max_value"] is not None
    )

    cevap = istemci.put(
        f"/api/v1/runs/{run['id']}/answers/{uuid4()}",
        json={"item_id": madde["item_id"], "state": "passed", "value": madde["max_value"] + 95},
    )

    assert cevap.status_code == 200, cevap.text
    assert cevap.json()["state"] == "failed"


# --- BR-26: gönderim de kilidi denetler (bağımsız test turu B03) --------


def test_br26_kilit_sahibi_olmayan_gonderemez() -> None:
    """Listeyi A dolduruyorken B gönderemez (B03).

    Yazma denetleniyordu, gönderim denetlenmiyordu: B'nin gönderimi
    kabul ediliyor ve `locked_by` B'ye yazıldığı için kayıt işi
    yapmayan kişiye atfediyordu.
    """
    servis, run_id, planlar, _ = _kurulum()
    a, b = uuid4(), uuid4()
    _cevapla(servis, run_id, user_id=a)

    with pytest.raises(RunLocked):
        servis.submit(run_id, user_id=b)

    assert planlar.run(run_id).status == "in_progress"  # type: ignore[union-attr]


def test_br26_kilit_sahibi_gonderebilir() -> None:
    servis, run_id, _, _ = _kurulum()
    a = uuid4()
    _cevapla(servis, run_id, user_id=a)

    gonderilen = servis.submit(run_id, user_id=a)

    assert gonderilen.status == "submitted"
    assert gonderilen.locked_by == a


def test_br26_kilit_dustukten_sonra_baskasi_gonderebilir() -> None:
    """Kilit 30 dakika yenilenmezse düşer: cihazı kapanan kimseyi kilitlemez."""
    servis, run_id, _, an = _kurulum()
    a, b = uuid4(), uuid4()
    _cevapla(servis, run_id, user_id=a)
    sonra = ExecutionService(
        servis._answers,
        servis._plans,
        servis._templates,
        now=lambda: an + timedelta(minutes=LOCK_MINUTES + 1),
    )

    gonderilen = sonra.submit(run_id, user_id=b)

    assert gonderilen.status == "submitted"


def test_br26_uc_noktada_ikinci_kisi_gonderemez(istemci: TestClient) -> None:
    """Aynı kural HTTP yolunda: 409 `calistirma-kilitli`.

    İki aktör de **aynı** şubede: kapsam hatası (403) kilit hatasını
    gölgelemesin.
    """
    # Kurulum şube müdürüyle (personel şube listesini göremiyor),
    # yazma ve gönderme aynı şubenin iki personeliyle.
    oturum_ac(istemci, "branch_manager")
    run = _acik_calistirma(istemci)
    oturum_ac(istemci, "staff")
    gorunum = istemci.get(f"/api/v1/runs/{run['id']}").json()
    degerler = _surum_degerleri(istemci, str(run["id"]))
    madde = next(
        m for bolum in gorunum["sections"] for m in bolum["items"] if m["type"] != "instruction"
    )
    yazma = istemci.put(
        f"/api/v1/runs/{run['id']}/answers/{uuid4()}",
        json={
            "item_id": madde["item_id"],
            "state": "passed",
            "value": degerler[madde["item_id"]],
        },
    )
    assert yazma.status_code == 200, yazma.text

    # Aynı şubeden **başka** bir kişi gönderimi denerse.
    ikinci = oturum_ac(TestClient(istemci.app), "staff2")
    cevap = ikinci.post(f"/api/v1/runs/{run['id']}/submit", json={})

    assert cevap.status_code == 409, cevap.text
    assert cevap.json()["type"] == "urn:talimatname:calistirma-kilitli"


# --- FR-0405 / BR-10: aksiyon cevapla doğar (bağımsız test turu B04, B05) ---


def test_br10_kritik_basarisiz_cevap_gonderim_beklemeden_aksiyon_aciyor() -> None:
    """9 derecelik buzdolabı kaydedilir kaydedilmez merkeze düşmeli.

    Aksiyon yalnızca gönderimde açılıyordu: liste gönderilene kadar —
    kimi zaman hiç gönderilmeden — kimse haberdar olmuyordu. FR-1008
    "anında" diyor.
    """
    servis, run_id, aksiyonlar, _ = _kritik_kurulum()
    kritik = next(m for m in servis.view(run_id).version.items if m.critical)

    _yaz(
        servis,
        run_id,
        kritik,
        state="failed",
        value=madde_degeri(kritik, "failed"),
        note="Sıcaklık yüksek",
        evidence_count=1,
    )

    acilan = [a for a in aksiyonlar.actions() if a.source == "critical_item"]
    assert len(acilan) == 1
    assert acilan[0].priority == "critical"
    assert servis.view(run_id).run.status != "submitted"


def test_br10_kritik_aksiyon_cevap_tekrar_yazilinca_cogalmiyor() -> None:
    """Çevrimdışı kuyruk aynı cevabı birkaç kez gönderebilir."""
    servis, run_id, aksiyonlar, _ = _kritik_kurulum()
    kritik = next(m for m in servis.view(run_id).version.items if m.critical)
    deger = madde_degeri(kritik, "failed")

    for _ in range(3):
        _yaz(servis, run_id, kritik, state="failed", value=deger, note="Yüksek", evidence_count=1)

    assert len([a for a in aksiyonlar.actions() if a.source == "critical_item"]) == 1


def test_br10_cevap_duzeltilse_de_aksiyon_duruyor() -> None:
    """Ölçüm düzeltilince aksiyon geri alınmaz: olay yaşandı.

    Aksiyon notuyla kapanır (BR-10); silmek kaydı silmek olurdu.
    """
    servis, run_id, aksiyonlar, _ = _kritik_kurulum()
    kritik = next(m for m in servis.view(run_id).version.items if m.critical)
    _yaz(
        servis,
        run_id,
        kritik,
        state="failed",
        value=madde_degeri(kritik, "failed"),
        note="Yüksek",
        evidence_count=1,
    )

    _yaz(servis, run_id, kritik, state="passed", value=madde_degeri(kritik, "passed"))

    assert len([a for a in aksiyonlar.actions() if a.source == "critical_item"]) == 1


def test_br10_yapilamadi_cevabi_aksiyon_aciyor() -> None:
    """BR-10: yapılamadı → orta öncelik, 72 saat (TC-059)."""
    servis, run_id, aksiyonlar, _ = _kritik_kurulum()
    madde = next(m for m in servis.view(run_id).version.items if m.scored and not m.critical)

    _yaz(
        servis,
        run_id,
        madde,
        state="not_done",
        not_done_reason="no_material",
        note="Deterjan bitti",
        evidence_count=1,
    )

    acilan = [a for a in aksiyonlar.actions() if a.source == "not_done"]
    assert len(acilan) == 1
    assert acilan[0].priority == "normal"
    assert acilan[0].due_at - acilan[0].opened_at == timedelta(hours=72)
    assert "Malzeme yok" in (acilan[0].description or "")


def test_br10_yapilamadi_aksiyonu_cogalmiyor() -> None:
    servis, run_id, aksiyonlar, _ = _kritik_kurulum()
    madde = next(m for m in servis.view(run_id).version.items if m.scored and not m.critical)

    for sebep in ("no_material", "no_time"):
        _yaz(
            servis,
            run_id,
            madde,
            state="not_done",
            not_done_reason=sebep,
            note="Yapılamadı",
            evidence_count=1,
        )

    assert len([a for a in aksiyonlar.actions() if a.source == "not_done"]) == 1


def test_br10_gecen_cevap_aksiyon_acmiyor() -> None:
    servis, run_id, aksiyonlar, _ = _kritik_kurulum()
    _cevapla(servis, run_id)

    assert aksiyonlar.actions() == []


# --- gece yarısını aşan pencere (B11'in ikinci yüzü) ------------------


def test_gece_yarisini_asan_calistirma_ertesi_gun_listede_kaliyor(istemci: TestClient) -> None:
    """Kapanış vardiyası 00:30'da kartını kaybetmemeli.

    Pencere 22:00–01:30 ise iş günü **dündür**; saat 00:30'da hesabın
    günü ertesi gündür ama liste hâlâ açıktır. `GET /runs` yalnızca
    bugünü döndürdüğünde kart, personel doldururken ekrandan siliniyordu.
    """
    # Her gün açık bir şube: haftada 6 gün açık olan şube kapalı gününde
    # çalıştırma üretmez (BR-17) ve test o gün kırmızı yanardı.
    sube = next(
        s
        for d in istemci.get("/api/v1/branches").json()
        for s in d["branches"]
        if s["open_days"] == 7
    )
    yerel = datetime.now(ZoneInfo("Europe/Istanbul"))
    # Dün 23:00'te başlayan, bugün devam eden bir pencere.
    basla = (yerel - timedelta(hours=2)).replace(second=0, microsecond=0)
    dun = (yerel - timedelta(days=1)).date()
    surum = next(
        v
        for t in istemci.get("/api/v1/templates").json()
        for v in t["versions"]
        if v["status"] == "published"
    )
    plan = istemci.post(
        "/api/v1/plans",
        json={
            "name": "Gece yarısını aşan (test)",
            "template_version_id": surum["id"],
            "branch_ids": [sube["id"]],
            "schedule": {
                "repeat": "daily",
                "starts_on": dun.isoformat(),
                "start_mode": "fixed",
                "start_time": basla.strftime("%H:%M"),
                "duration_minutes": 300,
                "tolerance_minutes": 60,
            },
        },
    )
    assert plan.status_code in (200, 201), plan.text
    istemci.post("/api/v1/scheduler/tick")

    acik = [k for k in istemci.get("/api/v1/runs").json() if k["plan_name"].startswith("Gece")]
    simdi = datetime.now(UTC)
    hala_acik = [k for k in acik if datetime.fromisoformat(k["tolerance_end"]) > simdi]

    assert hala_acik, "açık pencere gün verilmeden çağrılan listede yok"


def test_gun_acikca_verilince_yalnizca_o_gun_doner(istemci: TestClient) -> None:
    """Pano ve raporlar tam bir iş günü soruyor: anlam değişmemeli."""
    bugun = datetime.now(ZoneInfo("Europe/Istanbul")).date()

    liste = istemci.get(f"/api/v1/runs?business_day={bugun.isoformat()}").json()

    assert all(k["business_day"] == bugun.isoformat() for k in liste)


# --- kilit: üstlenme, bırakma, müdür devralması (BR-26) ---------------


def test_kilit_catismasinda_isim_gorunuyor(istemci: TestClient) -> None:
    """ "Kilit sahibi: 73a8e2ba-…" kullanıcıya bir şey anlatmıyordu.

    BR-26 "diğerleri **X yapıyor** görür" diyor; ham kimlik bunu
    karşılamıyor (7 Kasım canlı turunda çıktı).
    """
    # Kadıköy şube müdürüyle hazırlanıyor: personel /branches
    # çağıramıyor (Müdür kapısı) ve yöneticiyle hazırlamak başka bir
    # şubenin çalıştırmasını seçip personele 403 verdiriyordu.
    run = _acik_calistirma(oturum_ac(istemci, "branch_manager"))
    oturum_ac(istemci, "staff")
    istemci.post(f"/api/v1/runs/{run['id']}/claim")

    ikinci = oturum_ac(istemci, "staff2")
    yanit = ikinci.post(f"/api/v1/runs/{run['id']}/claim")

    assert yanit.status_code == 409
    govde = yanit.json()
    assert govde["holder_name"] == "Emre Personel"
    assert "Emre Personel" in govde["detail"]


def test_gorunum_kilit_sahibinin_adini_tasiyor(istemci: TestClient) -> None:
    # Kadıköy şube müdürüyle hazırlanıyor: personel /branches
    # çağıramıyor (Müdür kapısı) ve yöneticiyle hazırlamak başka bir
    # şubenin çalıştırmasını seçip personele 403 verdiriyordu.
    run = _acik_calistirma(oturum_ac(istemci, "branch_manager"))
    oturum_ac(istemci, "staff")

    govde = istemci.post(f"/api/v1/runs/{run['id']}/claim").json()

    assert govde["locked_by_name"] == "Emre Personel"


def test_sahibi_kilidi_birakinca_serbest_kaliyor(istemci: TestClient) -> None:
    # Kadıköy şube müdürüyle hazırlanıyor: personel /branches
    # çağıramıyor (Müdür kapısı) ve yöneticiyle hazırlamak başka bir
    # şubenin çalıştırmasını seçip personele 403 verdiriyordu.
    run = _acik_calistirma(oturum_ac(istemci, "branch_manager"))
    oturum_ac(istemci, "staff")
    istemci.post(f"/api/v1/runs/{run['id']}/claim")

    birak = istemci.post(f"/api/v1/runs/{run['id']}/release")

    assert birak.status_code == 200
    assert birak.json()["locked_by"] is None
    ikinci = oturum_ac(istemci, "staff2")
    assert ikinci.post(f"/api/v1/runs/{run['id']}/claim").status_code == 200


def test_personel_baskasinin_kilidini_kaldiramaz(istemci: TestClient) -> None:
    # Kadıköy şube müdürüyle hazırlanıyor: personel /branches
    # çağıramıyor (Müdür kapısı) ve yöneticiyle hazırlamak başka bir
    # şubenin çalıştırmasını seçip personele 403 verdiriyordu.
    run = _acik_calistirma(oturum_ac(istemci, "branch_manager"))
    oturum_ac(istemci, "staff")
    istemci.post(f"/api/v1/runs/{run['id']}/claim")

    ikinci = oturum_ac(istemci, "staff2")
    yanit = ikinci.post(f"/api/v1/runs/{run['id']}/release")

    assert yanit.status_code == 409
    assert yanit.json()["type"].endswith("calistirma-kilitli")


def test_mudur_kilidi_kaldirabiliyor(istemci: TestClient) -> None:
    """Tek çıkış yolu 30 dakika beklemekti: personel eve gidince
    müdür listeyi kurtaramıyordu (BR-26)."""
    # Kadıköy şube müdürüyle hazırlanıyor: personel /branches
    # çağıramıyor (Müdür kapısı) ve yöneticiyle hazırlamak başka bir
    # şubenin çalıştırmasını seçip personele 403 verdiriyordu.
    run = _acik_calistirma(oturum_ac(istemci, "branch_manager"))
    oturum_ac(istemci, "staff")
    istemci.post(f"/api/v1/runs/{run['id']}/claim")

    mudur = oturum_ac(istemci, "admin")
    yanit = mudur.post(f"/api/v1/runs/{run['id']}/release")

    assert yanit.status_code == 200
    assert yanit.json()["locked_by"] is None


def test_kilit_olaylari_gunluge_yaziliyor(istemci: TestClient) -> None:
    """BR-26 son cümle: "kilit olayları logda"."""
    from talimatname.api import bagimliliklar

    depo = bagimliliklar._izi_deposu()
    # Kadıköy şube müdürüyle hazırlanıyor: personel /branches
    # çağıramıyor (Müdür kapısı) ve yöneticiyle hazırlamak başka bir
    # şubenin çalıştırmasını seçip personele 403 verdiriyordu.
    run = _acik_calistirma(oturum_ac(istemci, "branch_manager"))
    oturum_ac(istemci, "staff")
    once = len(depo.events(limit=2000))

    istemci.post(f"/api/v1/runs/{run['id']}/claim")
    oturum_ac(istemci, "admin").post(f"/api/v1/runs/{run['id']}/release")

    turler = [o.event_type for o in depo.events(limit=2000)[once:]]
    assert "calistirma.kilit_alindi" in turler
    assert "calistirma.kilit_kaldirildi" in turler
