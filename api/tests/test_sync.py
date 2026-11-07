"""Senk testleri (ST-054; TC-052, TC-053; FR-0701…FR-0707, BR-13, BR-09).

Bu dosya ADR-0013'ün üçüncü devir sözleşmesini sabitler. Mobil henüz
yok; test, mobilin güvenebileceği davranışın yazılı hali.
"""

from __future__ import annotations

import hashlib
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from conftest import oturum_ac
from talimatname.api import bagimliliklar
from talimatname.api.app import create_app
from talimatname.domain.answers import RunLock
from talimatname.domain.sync import (
    NOT_DONE_REASON_LABELS,
    QUEUE_EVIDENCE_LIMIT,
    QUEUE_HOURS,
    check_not_done_reason,
    clock_offset,
    corrected_time,
    skew_minutes,
)
from talimatname.domain.validation import ValidationError
from talimatname.infra.memory import (
    MemoryAnswerRepository,
    MemoryEvidenceRepository,
    MemoryOrganizationRepository,
    MemoryPlanRepository,
    MemoryTemplateRepository,
    sabit_id,
)
from talimatname.services.evidence import EvidenceService
from talimatname.services.execution import ExecutionService
from talimatname.services.plans import PlanService
from talimatname.services.storage import LocalObjectStore
from talimatname.services.sync import QueuedAnswer, QueuedEvidence, SyncService
from talimatname.settings import Settings

KADIKOY = sabit_id("sube:KDK")
USKUDAR = sabit_id("sube:USK")


def _foto(tohum: bytes = b"sahte-jpeg") -> tuple[bytes, str]:
    return tohum, hashlib.sha256(tohum).hexdigest()


class Dunya:
    """Bellek içi dünya: tohum şube/şablon, üretilmiş çalıştırmalar."""

    def __init__(self, tmp: Path) -> None:
        self.an = datetime.now(UTC)
        self.planlar = MemoryPlanRepository()
        self.org = MemoryOrganizationRepository()
        self.sablonlar = MemoryTemplateRepository()
        self.cevaplar = MemoryAnswerRepository()
        PlanService(self.planlar, self.org, self.sablonlar, now=lambda: self.an).generate_all()

        self.yurutme = ExecutionService(
            self.cevaplar,
            self.planlar,
            self.sablonlar,
            now=lambda: self.an,
        )
        self.kanit = EvidenceService(
            MemoryEvidenceRepository(),
            self.planlar,
            self.org,
            LocalObjectStore(tmp),
            settings=Settings(environment="dev"),
            now=lambda: self.an,
        )
        self.servis = SyncService(
            self.planlar,
            self.org,
            self.sablonlar,
            self.yurutme,
            self.kanit,
            now=lambda: self.an,
        )

        # Çalıştırmanın penceresi **şu anı kapsayacak şekilde** kuruluyor.
        # Eskiden yalnızca "toleransı dolmamış" aranıyordu; penceresi daha
        # açılmamış olanlar da geçiyordu ve `pencere-acilmadi` kuralı
        # gelince test günün saatine göre kırılır oldu. Saati ileri almak
        # çözüm değil: kanıt belirteci `iat`i gelecekte kalıp
        # doğrulanamıyor. O yüzden saat değil pencere oynatılıyor.
        secilen = next(
            r for r in self.planlar.runs() if r.branch_id == KADIKOY and r.status == "scheduled"
        )
        self.run = replace(
            secilen,
            window_start=self.an - timedelta(minutes=5),
            window_end=self.an + timedelta(minutes=60),
            tolerance_end=self.an + timedelta(minutes=90),
        )
        self.planlar.save_run(self.run)
        surum = self.sablonlar.version(self.run.template_version_id)
        assert surum is not None
        self.madde = next(m for m in surum.items if m.scored and not m.critical)
        self.kritik_madde = next((m for m in surum.items if m.critical), None)

    @property
    def kapsam(self) -> set[UUID]:
        return {KADIKOY}

    def cevap(self, **ek: object) -> QueuedAnswer:
        alanlar: dict[str, object] = {
            "answer_id": sabit_id("cevap:senk-1"),
            "run_id": self.run.id,
            "item_id": self.madde.id,
            "state": "passed",
        }
        alanlar.update(ek)
        return QueuedAnswer(**alanlar)  # type: ignore[arg-type]

    def kanit_kaydi(self, icerik: bytes = b"sahte-jpeg", **ek: object) -> QueuedEvidence:
        baytlar, ozet = _foto(icerik)
        alanlar: dict[str, object] = {
            "evidence_id": sabit_id("kanit:senk-1"),
            "run_id": self.run.id,
            "answer_id": sabit_id("cevap:senk-1"),
            "item_id": self.madde.id,
            "sha256": ozet,
            "content_type": "image/jpeg",
            "size_bytes": len(baytlar),
        }
        alanlar.update(ek)
        return QueuedEvidence(**alanlar)  # type: ignore[arg-type]


@pytest.fixture
def dunya(tmp_path: Path) -> Dunya:
    return Dunya(tmp_path)


# --- alan: saat düzeltmesi (TC-052, BR-13) ----------------------------


def test_saat_farki_isaretli_olculur() -> None:
    sunucu = datetime(2026, 3, 2, 12, 0, tzinfo=UTC)
    assert skew_minutes(clock_offset(sunucu, sunucu + timedelta(minutes=7))) == 7
    assert skew_minutes(clock_offset(sunucu, sunucu - timedelta(minutes=7))) == -7
    assert clock_offset(sunucu, None) is None


def test_cekim_zamani_farkla_duzeltilir() -> None:
    sunucu = datetime(2026, 3, 2, 12, 0, tzinfo=UTC)
    # Cihaz 7 dk ileri: kuyruktaki çekim zamanından 7 dk düşülür.
    fark = clock_offset(sunucu, sunucu + timedelta(minutes=7))
    cihaz_cekimi = datetime(2026, 3, 2, 9, 30, tzinfo=UTC)
    assert corrected_time(cihaz_cekimi, fark) == datetime(2026, 3, 2, 9, 23, tzinfo=UTC)

    # Fark bilinmiyorsa değer olduğu gibi kalır: uydurma düzeltme yok.
    assert corrected_time(cihaz_cekimi, None) == cihaz_cekimi
    assert corrected_time(None, fark) is None


def test_sebep_kurallari() -> None:
    assert check_not_done_reason("passed", None, None) is None
    assert check_not_done_reason("not_done", "no_material", None) == "no_material"

    with pytest.raises(ValidationError, match="zorunlu"):
        check_not_done_reason("not_done", None, None)
    with pytest.raises(ValidationError, match="Bilinmeyen"):
        check_not_done_reason("not_done", "canim_istemedi", None)
    with pytest.raises(ValidationError, match="not zorunlu"):
        check_not_done_reason("not_done", "other", "kisa")
    with pytest.raises(ValidationError, match="yalnızca"):
        check_not_done_reason("passed", "no_material", None)

    assert check_not_done_reason("not_done", "other", "kapi kilitliydi") == "other"


# --- manifest (FR-0701) -----------------------------------------------


def test_manifest_yalnizca_kapsamdaki_subeyi_tasir(dunya: Dunya) -> None:
    manifest = dunya.servis.manifest(branch_ids=dunya.kapsam)
    assert manifest.runs
    assert {r.branch_id for r in manifest.runs} == {KADIKOY}

    iki_sube = dunya.servis.manifest(branch_ids={KADIKOY, USKUDAR})
    assert {r.branch_id for r in iki_sube.runs} == {KADIKOY, USKUDAR}


def test_manifest_ufku_pencereyi_daraltir(dunya: Dunya) -> None:
    genis = dunya.servis.manifest(branch_ids=dunya.kapsam, horizon_hours=48)
    dar = dunya.servis.manifest(branch_ids=dunya.kapsam, horizon_hours=1)
    assert len(dar.runs) <= len(genis.runs)
    assert dar.horizon_hours == 1
    # Ufuk üst sınırla kırpılır: istemci 10 yıl isteyemez.
    assert dunya.servis.manifest(branch_ids=dunya.kapsam, horizon_hours=10_000).horizon_hours == 168


def test_manifest_surum_kimliklerini_tekilleyerek_verir(dunya: Dunya) -> None:
    manifest = dunya.servis.manifest(branch_ids={KADIKOY, USKUDAR})
    kimlikler = [s.id for s in manifest.template_versions]
    assert len(kimlikler) == len(set(kimlikler))
    assert {r.template_version_id for r in manifest.runs} <= set(kimlikler)
    assert all(s.item_count > 0 for s in manifest.template_versions)


def test_manifest_sebep_setini_ve_sinirlari_soyler(dunya: Dunya) -> None:
    manifest = dunya.servis.manifest(branch_ids=dunya.kapsam)
    assert dict(manifest.not_done_reasons) == NOT_DONE_REASON_LABELS
    assert manifest.policy.queue_evidence_limit == QUEUE_EVIDENCE_LIMIT
    assert manifest.policy.queue_hours == QUEUE_HOURS
    assert manifest.refresh_after_minutes == 15


def test_manifest_saat_okumasini_dondurur(dunya: Dunya) -> None:
    manifest = dunya.servis.manifest(
        branch_ids=dunya.kapsam,
        device_time=dunya.an + timedelta(minutes=12),
    )
    assert manifest.clock.skew_minutes == 12
    assert manifest.clock.flagged is True

    temiz = dunya.servis.manifest(
        branch_ids=dunya.kapsam,
        device_time=dunya.an + timedelta(minutes=7),
    )
    assert temiz.clock.skew_minutes == 7
    assert temiz.clock.flagged is False


# --- kuyruk: idempotans (TC-053, FR-0707) -----------------------------


def test_ayni_kuyruk_iki_kez_tek_kayit(dunya: Dunya) -> None:
    kuyruk = [dunya.cevap()]
    kisi = uuid4()  # aynı cihaz, aynı kişi: kuyruk iki kez gidiyor
    ilk = dunya.servis.apply_batch(branch_ids=dunya.kapsam, user_id=kisi, answers=kuyruk)
    ikinci = dunya.servis.apply_batch(branch_ids=dunya.kapsam, user_id=kisi, answers=kuyruk)

    assert [c.outcome for c in ilk.answers] == ["accepted"]
    assert [c.outcome for c in ikinci.answers] == ["accepted"]
    assert len(dunya.cevaplar.answers(dunya.run.id)) == 1


def test_yarim_kalan_kanit_kaldigi_yerden_devam_eder(dunya: Dunya) -> None:
    kayit = dunya.kanit_kaydi()
    ilk = dunya.servis.apply_batch(branch_ids=dunya.kapsam, user_id=uuid4(), evidence=[kayit])
    assert ilk.evidence[0].outcome == "accepted"
    assert ilk.evidence[0].upload_token

    # Cihaz yüklemeyi bitirmeden kapandı: aynı kimlikle yeniden gelir.
    ikinci = dunya.servis.apply_batch(branch_ids=dunya.kapsam, user_id=uuid4(), evidence=[kayit])
    assert ikinci.evidence[0].outcome == "resumed"
    assert ikinci.evidence[0].upload_token
    assert len(dunya.kanit.for_run(dunya.run.id)) == 1


def test_dogrulanmis_kanita_yeniden_yazma_izni_verilmez(dunya: Dunya) -> None:
    kayit = dunya.kanit_kaydi()
    sonuc = dunya.servis.apply_batch(branch_ids=dunya.kapsam, user_id=uuid4(), evidence=[kayit])
    belirtec = sonuc.evidence[0].upload_token
    assert belirtec
    baytlar, _ = _foto()
    dunya.kanit.receive(belirtec, baytlar)
    dunya.kanit.complete(kayit.evidence_id)

    # Baytlar depoda ve doğrulandı: ikinci yazma izni değişmezliği bozardı (BR-12).
    tekrar = dunya.servis.apply_batch(branch_ids=dunya.kapsam, user_id=uuid4(), evidence=[kayit])
    assert tekrar.evidence[0].outcome == "resumed"
    assert tekrar.evidence[0].upload_token is None


def test_ayni_fotograf_baska_kimlikle_tekrar_sayilir(dunya: Dunya) -> None:
    dunya.servis.apply_batch(
        branch_ids=dunya.kapsam, user_id=uuid4(), evidence=[dunya.kanit_kaydi()]
    )
    tekrar = dunya.servis.apply_batch(
        branch_ids=dunya.kapsam,
        user_id=uuid4(),
        evidence=[dunya.kanit_kaydi(evidence_id=uuid4())],
    )
    assert tekrar.evidence[0].outcome == "duplicate"
    assert tekrar.evidence[0].error is not None
    assert tekrar.evidence[0].error.code == "kanit-tekrari"
    assert tekrar.evidence[0].error.retryable is False


# --- kuyruk: kısmi başarı (FR-0703) -----------------------------------


def test_bozuk_kayit_kuyrugun_kalanini_bloke_etmez(dunya: Dunya) -> None:
    sonuc = dunya.servis.apply_batch(
        branch_ids=dunya.kapsam,
        user_id=uuid4(),
        answers=[
            dunya.cevap(answer_id=uuid4(), item_id=uuid4()),  # şablonda olmayan madde
            dunya.cevap(answer_id=uuid4()),  # sağlam kayıt
        ],
    )
    assert [c.outcome for c in sonuc.answers] == ["rejected", "accepted"]
    assert sonuc.answers[0].error is not None
    assert sonuc.answers[0].error.code == "madde-bulunamadi"
    assert sonuc.accepted == 1
    assert sonuc.rejected == 1


def test_kapsam_disi_calistirma_senk_yoluyla_da_yazilamaz(dunya: Dunya) -> None:
    yabanci = next(r for r in dunya.planlar.runs() if r.branch_id == USKUDAR)
    sonuc = dunya.servis.apply_batch(
        branch_ids=dunya.kapsam,
        user_id=uuid4(),
        answers=[dunya.cevap(run_id=yabanci.id)],
    )
    assert sonuc.answers[0].outcome == "rejected"
    assert sonuc.answers[0].error is not None
    assert sonuc.answers[0].error.code == "calistirma-kapsam-disi"


def test_kilit_hatasi_yeniden_denenebilir_isaretlenir(dunya: Dunya) -> None:
    baskasi = uuid4()
    dunya.cevaplar.save_lock(
        dunya.run.id, RunLock(user_id=baskasi, acquired_at=dunya.an, renewed_at=dunya.an)
    )
    sonuc = dunya.servis.apply_batch(
        branch_ids=dunya.kapsam, user_id=uuid4(), answers=[dunya.cevap()]
    )
    assert sonuc.answers[0].outcome == "rejected"
    assert sonuc.answers[0].error is not None
    # Kilit 30 dakikada düşer: cihaz bunu bırakmasın, sonra denesin.
    assert sonuc.answers[0].error.retryable is True


def test_gecersiz_sebep_kaydi_reddedilir_kuyruk_devam_eder(dunya: Dunya) -> None:
    sonuc = dunya.servis.apply_batch(
        branch_ids=dunya.kapsam,
        user_id=uuid4(),
        answers=[dunya.cevap(answer_id=uuid4(), state="not_done")],  # sebep yok
    )
    assert sonuc.answers[0].outcome == "rejected"
    assert sonuc.answers[0].error is not None
    assert sonuc.answers[0].error.code == "gecersiz-istek"


def test_kritik_maddede_yapilamadi_reddedilir(dunya: Dunya) -> None:
    if dunya.kritik_madde is None:  # pragma: no cover - tohuma bağlı
        pytest.skip("tohumda kritik madde yok")
    sonuc = dunya.servis.apply_batch(
        branch_ids=dunya.kapsam,
        user_id=uuid4(),
        answers=[
            dunya.cevap(
                answer_id=uuid4(),
                item_id=dunya.kritik_madde.id,
                state="not_done",
                not_done_reason="no_material",
            )
        ],
    )
    assert sonuc.answers[0].outcome == "rejected"
    assert sonuc.answers[0].error is not None
    assert sonuc.answers[0].error.code == "kritik-maddede-yapilamadi-yok"


# --- kuyruk: saat düzeltmesi uçtan uca (TC-052) -----------------------


def test_cihaz_saati_ileri_olunca_cekim_zamani_duzeltilir(dunya: Dunya) -> None:
    cihaz_saati = dunya.an + timedelta(minutes=7)
    cekim = cihaz_saati - timedelta(hours=2)  # cihazın kendi saatiyle
    sonuc = dunya.servis.apply_batch(
        branch_ids=dunya.kapsam,
        user_id=uuid4(),
        device_time=cihaz_saati,
        evidence=[dunya.kanit_kaydi(captured_at=cekim)],
    )
    assert sonuc.clock.skew_minutes == 7
    assert sonuc.clock.flagged is False

    kanit = dunya.kanit.get(sonuc.evidence[0].evidence_id)
    assert kanit.captured_at == cekim - timedelta(minutes=7)
    assert kanit.device_reported_at == cekim  # ham değer korunuyor (BR-13)
    assert kanit.clock_skew_minutes == 7
    assert "clock_skew" not in kanit.flags


def test_esigi_asan_fark_bayrak_birakir(dunya: Dunya) -> None:
    cihaz_saati = dunya.an + timedelta(minutes=12)
    sonuc = dunya.servis.apply_batch(
        branch_ids=dunya.kapsam,
        user_id=uuid4(),
        device_time=cihaz_saati,
        evidence=[dunya.kanit_kaydi(captured_at=cihaz_saati)],
    )
    assert sonuc.clock.flagged is True
    kanit = dunya.kanit.get(sonuc.evidence[0].evidence_id)
    assert "clock_skew" in kanit.flags


def test_cevabin_olay_zamani_sunucunundur(dunya: Dunya) -> None:
    """Cihaz saatini geri alarak kapanmış pencereye yazamaz (BR-13)."""
    cihaz_saati = dunya.an - timedelta(hours=6)
    sonuc = dunya.servis.apply_batch(
        branch_ids=dunya.kapsam,
        user_id=uuid4(),
        device_time=cihaz_saati,
        answers=[dunya.cevap(answered_at=cihaz_saati)],
    )
    assert sonuc.answers[0].outcome == "accepted"
    cevap = dunya.cevaplar.answers(dunya.run.id)[0]
    assert cevap.answered_at == dunya.an  # sunucu saati
    assert cevap.device_reported_at == cihaz_saati  # ham değer
    assert cevap.clock_skew_minutes == -360


# --- uç noktalar ------------------------------------------------------


def _istemci(tmp: Path) -> TestClient:
    return oturum_ac(
        TestClient(create_app(Settings(environment="dev", evidence_dir=str(tmp)))),
        "staff",
    )


def _pencereyi_simdiye_cek(run_id: str) -> None:
    """Verilen çalıştırmanın penceresini şu anı kapsayacak biçimde yazar.

    Tohumun pencereleri sabit saatlerde; uç nokta testini günün saatine
    bağlamamak gerekiyor. Saati ileri almak çözüm değil — kanıt belirteci
    gerçek saate göre doğrulanıyor ve `iat` gelecekte kalıyor — o yüzden
    saat değil pencere oynatılıyor.
    """
    an = datetime.now(UTC)
    depo = bagimliliklar._plan_deposu()
    kosu = next(r for r in depo.runs() if str(r.id) == run_id)
    depo.save_run(
        replace(
            kosu,
            status="scheduled",
            window_start=an - timedelta(minutes=5),
            window_end=an + timedelta(minutes=60),
            tolerance_end=an + timedelta(minutes=90),
        )
    )


def test_manifest_uc_noktasi_personelin_subesini_verir(tmp_path: Path) -> None:
    istemci = _istemci(tmp_path)
    # Cihaz saati başlıkta: sorgu dizesinde ISO zamanın "+00:00" eki
    # boşluğa çözülüyor ve istek 422 dönüyor (denemede yakalandı).
    yanit = istemci.get(
        "/api/v1/sync/manifest",
        headers={"X-Device-Time": datetime.now(UTC).isoformat()},
    )
    assert yanit.status_code == 200
    govde = yanit.json()
    assert govde["clock"]["skew_minutes"] is not None
    assert govde["horizon_hours"] == 48
    assert govde["refresh_after_minutes"] == 15
    assert len(govde["not_done_reasons"]) == 5
    assert govde["policy"]["queue_evidence_limit"] == 500
    assert {r["branch_code"] for r in govde["runs"]} == {"KDK"}


def test_kuyruk_uc_noktasi_gorece_yukleme_adresi_dondurur(tmp_path: Path) -> None:
    istemci = _istemci(tmp_path)
    _pencereyi_simdiye_cek(istemci.get("/api/v1/sync/manifest").json()["runs"][0]["run_id"])
    manifest = istemci.get("/api/v1/sync/manifest").json()
    # Manifest penceresi açılmamış çalıştırmayı da listeliyor (cihaz
    # şablonu önceden indirsin diye); yazma denemesi için **şu an
    # yazılabilir** olanı seçmek gerek.
    simdi = datetime.now(UTC)
    kosu = next(
        k
        for k in manifest["runs"]
        if datetime.fromisoformat(k["writable_from"]) <= simdi
        and datetime.fromisoformat(k["tolerance_end"]) > simdi
    )
    surum = istemci.get(f"/api/v1/template-versions/{kosu['template_version_id']}").json()
    madde = next(
        m
        for b in surum["sections"]
        for m in b["items"]
        if m["type"] not in ("instruction",) and not m["critical"]
    )

    baytlar, ozet = _foto(b"uc-nokta-jpeg")
    cevap_id = str(uuid4())
    kanit_id = str(uuid4())
    yanit = istemci.post(
        "/api/v1/sync/batch",
        json={
            "device_time": datetime.now(UTC).isoformat(),
            "answers": [
                {
                    "answer_id": cevap_id,
                    "run_id": kosu["run_id"],
                    "item_id": madde["id"],
                    "state": "passed",
                }
            ],
            "evidence": [
                {
                    "evidence_id": kanit_id,
                    "run_id": kosu["run_id"],
                    "answer_id": cevap_id,
                    "item_id": madde["id"],
                    "sha256": ozet,
                    "content_type": "image/jpeg",
                    "size_bytes": len(baytlar),
                }
            ],
        },
    )
    assert yanit.status_code == 200
    govde = yanit.json()
    assert govde["accepted"] == 2
    assert govde["rejected"] == 0
    assert govde["answers"][0]["outcome"] == "accepted"

    adres = govde["evidence"][0]["upload_url"]
    # Göreli adres: ters vekil arkasında sunucunun iç adresi sızmasın.
    assert adres.startswith("/api/v1/uploads/")
    assert istemci.put(adres, content=baytlar).status_code == 200
    tamam = istemci.post(f"/api/v1/evidence/{kanit_id}/complete")
    assert tamam.status_code == 200
    assert tamam.json()["status"] == "stored"


def test_kuyruk_oturum_ister(tmp_path: Path) -> None:
    istemci = TestClient(create_app(Settings(environment="dev", evidence_dir=str(tmp_path))))
    assert istemci.post("/api/v1/sync/batch", json={}).status_code == 403
    assert istemci.get("/api/v1/sync/manifest").status_code == 403
