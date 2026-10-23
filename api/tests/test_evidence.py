"""Kanıt testleri (ST-039, ST-049; TC-041…044, FR-0606, FR-0614, FR-0615)."""

from __future__ import annotations

import hashlib
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from conftest import oturum_ac
from talimatname.api.app import create_app
from talimatname.domain.evidence import (
    FAR_LOCATION_METERS,
    MAX_BYTES,
    MAX_PER_ITEM,
    distance_meters,
    evidence_flags,
    storage_key,
)
from talimatname.domain.validation import ValidationError
from talimatname.infra.memory import (
    MemoryEvidenceRepository,
    MemoryOrganizationRepository,
    MemoryPlanRepository,
    MemoryTemplateRepository,
    sabit_id,
)
from talimatname.services.evidence import (
    DigestMismatch,
    DuplicateEvidence,
    EvidenceNotFound,
    EvidenceNotStored,
    EvidenceService,
    TooManyEvidence,
)
from talimatname.services.plans import PlanService
from talimatname.services.storage import LocalObjectStore, digest
from talimatname.services.tokens import TokenInvalid
from talimatname.settings import Settings

KADIKOY = sabit_id("sube:KDK")
# Kadıköy meydanı civarı; şubeye koordinat verdiğimizde ölçü buradan.
SUBE_KONUM = (40.9900, 29.0300)


def _foto(icerik: bytes = b"sahte-jpeg-baytlari") -> tuple[bytes, str]:
    return icerik, hashlib.sha256(icerik).hexdigest()


class Dunya:
    def __init__(self, tmp: Path, an: datetime | None = None) -> None:
        self.an = an or datetime.now(UTC)
        self.planlar = MemoryPlanRepository()
        self.org = MemoryOrganizationRepository()
        PlanService(
            self.planlar, self.org, MemoryTemplateRepository(), now=lambda: self.an
        ).generate_all()
        sube = self.org.branch(KADIKOY)
        assert sube is not None
        self.org.save_branch(replace(sube, latitude=SUBE_KONUM[0], longitude=SUBE_KONUM[1]))
        self.depo = LocalObjectStore(tmp)
        self.servis = EvidenceService(
            MemoryEvidenceRepository(),
            self.planlar,
            self.org,
            self.depo,
            settings=Settings(environment="dev"),
            now=lambda: self.an,
        )
        self.run_id = next(r for r in self.planlar.runs() if r.branch_id == KADIKOY).id

    def yukle(self, icerik: bytes = b"sahte-jpeg-baytlari", **ek: object) -> object:
        baytlar, ozet = _foto(icerik)
        kanit, belirtec = self.servis.start(
            run_id=ek.pop("run_id", self.run_id),  # type: ignore[arg-type]
            answer_id=ek.pop("answer_id", sabit_id("cevap:1")),  # type: ignore[arg-type]
            item_id=ek.pop("item_id", sabit_id("madde:1")),  # type: ignore[arg-type]
            sha256=ozet,
            content_type="image/jpeg",
            size_bytes=len(baytlar),
            **ek,  # type: ignore[arg-type]
        )
        self.servis.receive(belirtec, baytlar)
        return self.servis.complete(kanit.id)


@pytest.fixture
def dunya(tmp_path: Path) -> Dunya:
    return Dunya(tmp_path)


# --- alan -------------------------------------------------------------


def test_ozet_bicimi_denetlenir(dunya: Dunya) -> None:
    with pytest.raises(ValidationError, match="SHA-256"):
        dunya.servis.start(
            run_id=dunya.run_id,
            answer_id=uuid4(),
            item_id=uuid4(),
            sha256="kisa",
            content_type="image/jpeg",
            size_bytes=100,
        )


def test_buyuk_dosya_reddedilir(dunya: Dunya) -> None:
    _, ozet = _foto(b"x")
    with pytest.raises(ValidationError, match="çok büyük"):
        dunya.servis.start(
            run_id=dunya.run_id,
            answer_id=uuid4(),
            item_id=uuid4(),
            sha256=ozet,
            content_type="image/jpeg",
            size_bytes=MAX_BYTES + 1,
        )


def test_desteklenmeyen_tur_reddedilir(dunya: Dunya) -> None:
    _, ozet = _foto(b"x")
    with pytest.raises(ValidationError, match="Desteklenmeyen"):
        dunya.servis.start(
            run_id=dunya.run_id,
            answer_id=uuid4(),
            item_id=uuid4(),
            sha256=ozet,
            content_type="application/pdf",
            size_bytes=100,
        )


def test_mesafe_hesabi_makul() -> None:
    """Kadıköy–Üsküdar arası ~3,5 km; haversine bu ölçekte yeterli."""
    uzaklik = distance_meters(40.9900, 29.0300, 41.0220, 29.0150)
    assert 3_000 < uzaklik < 4_500


def test_bayraklar_olculere_dayanir() -> None:
    an = datetime(2026, 3, 2, 12, 0, tzinfo=UTC)

    temiz = evidence_flags(
        from_gallery=False,
        latitude=SUBE_KONUM[0],
        longitude=SUBE_KONUM[1],
        branch_latitude=SUBE_KONUM[0],
        branch_longitude=SUBE_KONUM[1],
        clock_skew_minutes=2,
        captured_at=an,
        received_at=an,
    )
    assert temiz == ()

    supheli = evidence_flags(
        from_gallery=True,
        latitude=41.0220,
        longitude=29.0150,
        branch_latitude=SUBE_KONUM[0],
        branch_longitude=SUBE_KONUM[1],
        clock_skew_minutes=45,
        captured_at=an - timedelta(hours=30),
        received_at=an,
    )
    assert set(supheli) == {"gallery", "far_location", "clock_skew", "late_sync"}


def test_konumsuz_kanit_bayraklanir_ama_uzak_denmez() -> None:
    an = datetime(2026, 3, 2, 12, 0, tzinfo=UTC)
    bayraklar = evidence_flags(
        from_gallery=False,
        latitude=None,
        longitude=None,
        branch_latitude=SUBE_KONUM[0],
        branch_longitude=SUBE_KONUM[1],
        clock_skew_minutes=None,
        captured_at=an,
        received_at=an,
    )
    assert bayraklar == ("no_location",)


def test_sube_konumu_yoksa_uzak_bayragi_verilmez() -> None:
    """Ölçüye dayanmayan şüphe işareti, bayrağın anlamını boşaltır."""
    an = datetime(2026, 3, 2, 12, 0, tzinfo=UTC)
    bayraklar = evidence_flags(
        from_gallery=False,
        latitude=0.0,
        longitude=0.0,
        branch_latitude=None,
        branch_longitude=None,
        clock_skew_minutes=None,
        captured_at=an,
        received_at=an,
    )
    assert bayraklar == ()


def test_depolama_anahtari_calistirmaya_gore_obeklenir() -> None:
    run, kanit = uuid4(), uuid4()
    assert storage_key(run, kanit, "image/jpeg") == f"evidence/{run}/{kanit}.jpg"
    assert storage_key(run, kanit, "image/png").endswith(".png")


# --- servis -----------------------------------------------------------


def test_tc043_yukleme_ve_dogrulama(dunya: Dunya) -> None:
    kanit = dunya.yukle()

    assert kanit.status == "stored"  # type: ignore[attr-defined]
    assert dunya.depo.exists(kanit.storage_key)  # type: ignore[attr-defined]


def test_tc120_ayni_fotograf_ikinci_kez_reddedilir(dunya: Dunya) -> None:
    """FR-0614: geçen haftanın fotoğrafını yeniden göndermek kapatılmalı."""
    dunya.yukle(b"ayni-kare")

    with pytest.raises(DuplicateEvidence, match="daha önce"):
        dunya.yukle(b"ayni-kare", answer_id=sabit_id("cevap:2"))


def test_ozet_tutmazsa_kanit_silinir(dunya: Dunya) -> None:
    """İstemcinin beyanına güvenmek kanıtı beyana indirger."""
    baytlar, ozet = _foto(b"dogru-icerik")
    kanit, belirtec = dunya.servis.start(
        run_id=dunya.run_id,
        answer_id=uuid4(),
        item_id=uuid4(),
        sha256=ozet,
        content_type="image/jpeg",
        size_bytes=len(baytlar),
    )
    dunya.servis.receive(belirtec, b"baska-icerik")  # beyanla uyuşmuyor

    with pytest.raises(DigestMismatch):
        dunya.servis.complete(kanit.id)

    with pytest.raises(EvidenceNotFound):
        dunya.servis.get(kanit.id)
    assert not dunya.depo.exists(kanit.storage_key)


def test_yuklenmeden_tamamlama_reddedilir(dunya: Dunya) -> None:
    baytlar, ozet = _foto(b"hic-yuklenmedi")
    kanit, _ = dunya.servis.start(
        run_id=dunya.run_id,
        answer_id=uuid4(),
        item_id=uuid4(),
        sha256=ozet,
        content_type="image/jpeg",
        size_bytes=len(baytlar),
    )

    with pytest.raises(EvidenceNotStored):
        dunya.servis.complete(kanit.id)


def test_fr0604_madde_basina_en_cok_uc_fotograf(dunya: Dunya) -> None:
    madde = sabit_id("madde:buzdolabi")
    for i in range(MAX_PER_ITEM):
        dunya.yukle(f"kare-{i}".encode(), item_id=madde)

    with pytest.raises(TooManyEvidence):
        dunya.yukle(b"dorduncu-kare", item_id=madde)


def test_dogrulanmayan_kanit_silinir_ve_yeniden_denenebilir(dunya: Dunya) -> None:
    """Doğrulanmamış bayt kanıt değildir: kayıt silinir, tekillik kilidi kalmaz.

    Kalsaydı kullanıcı aynı kareyi bir daha yükleyemezdi — bozuk bir
    yükleme, doğru fotoğrafı sonsuza kadar yasaklardı.
    """
    baytlar, ozet = _foto(b"tekrar-denenecek")
    kanit, belirtec = dunya.servis.start(
        run_id=dunya.run_id,
        answer_id=uuid4(),
        item_id=uuid4(),
        sha256=ozet,
        content_type="image/jpeg",
        size_bytes=len(baytlar),
    )
    dunya.servis.receive(belirtec, b"bozuk")
    with pytest.raises(DigestMismatch):
        dunya.servis.complete(kanit.id)

    ikinci = dunya.yukle(b"tekrar-denenecek")
    assert ikinci.status == "stored"  # type: ignore[attr-defined]


def test_gorevli_bayraklari_kanita_yaziliyor(dunya: Dunya) -> None:
    kanit = dunya.yukle(
        b"galeriden-gelen",
        from_gallery=True,
        latitude=41.0220,
        longitude=29.0150,
    )

    assert "gallery" in kanit.flags  # type: ignore[attr-defined]
    assert "far_location" in kanit.flags  # type: ignore[attr-defined]
    assert kanit.distance_meters is not None  # type: ignore[attr-defined]
    assert kanit.distance_meters > FAR_LOCATION_METERS  # type: ignore[attr-defined]
    assert kanit.suspicious  # type: ignore[attr-defined]


def test_fr1305_goruntuleme_belirteci_kapsam_disi_kullanilamaz(dunya: Dunya) -> None:
    """Görüntüleme bağlantısı oturum belirteci yerine geçemez."""
    kanit = dunya.yukle()
    belirtec = dunya.servis.view_token(kanit.id)  # type: ignore[attr-defined]

    okunan, baytlar = dunya.servis.read(belirtec)
    assert okunan.id == kanit.id  # type: ignore[attr-defined]
    assert digest(baytlar) == okunan.sha256

    with pytest.raises(TokenInvalid, match="için değil"):
        dunya.servis.receive(belirtec, b"yukleme-denemesi")


def test_yerel_depo_kok_disina_yazmaz(tmp_path: Path) -> None:
    depo = LocalObjectStore(tmp_path)
    with pytest.raises(ValueError, match="kökü dışında"):
        depo.put("../kacak.jpg", b"x")


# --- uç noktalar ------------------------------------------------------


def _istemci(tmp: Path, rol: str = "admin") -> TestClient:
    """Kanıt dizini teste özel: testler depoya değil geçici dizine yazar."""
    ayar = Settings(environment="dev", evidence_dir=str(tmp))
    return oturum_ac(TestClient(create_app(ayar)), rol)


def _bir_calistirma(istemci: TestClient) -> dict[str, object]:
    kosular = istemci.get("/api/v1/runs").json()
    assert kosular
    return kosular[0]  # type: ignore[no-any-return]


def test_uc_nokta_kanit_akisi_uctan_uca(tmp_path: Path) -> None:
    istemci = _istemci(tmp_path)
    run = _bir_calistirma(istemci)
    baytlar, ozet = _foto(b"uc-nokta-karesi")
    cevap_id = str(uuid4())

    izin = istemci.post(
        f"/api/v1/runs/{run['id']}/answers/{cevap_id}/evidence",
        json={
            "item_id": str(UUID(int=7)),
            "sha256": ozet,
            "content_type": "image/jpeg",
            "size_bytes": len(baytlar),
        },
    )
    assert izin.status_code == 201
    govde = izin.json()
    assert govde["evidence"]["status"] == "pending"

    yukleme = istemci.put(govde["upload_url"], content=baytlar)
    assert yukleme.status_code == 200

    tamam = istemci.post(f"/api/v1/evidence/{govde['evidence']['id']}/complete")
    assert tamam.status_code == 200
    assert tamam.json()["status"] == "stored"

    baglanti = istemci.get(f"/api/v1/evidence/{govde['evidence']['id']}/url").json()
    dosya = istemci.get(baglanti["url"])
    assert dosya.status_code == 200
    assert dosya.content == baytlar


def test_uc_nokta_tekrar_eden_fotograf_409(tmp_path: Path) -> None:
    istemci = _istemci(tmp_path)
    run = _bir_calistirma(istemci)
    baytlar, ozet = _foto(b"tekrar-eden-kare")
    govde = {
        "item_id": str(UUID(int=8)),
        "sha256": ozet,
        "content_type": "image/jpeg",
        "size_bytes": len(baytlar),
    }
    ilk = istemci.post(f"/api/v1/runs/{run['id']}/answers/{uuid4()}/evidence", json=govde)
    assert ilk.status_code == 201

    ikinci = istemci.post(f"/api/v1/runs/{run['id']}/answers/{uuid4()}/evidence", json=govde)

    assert ikinci.status_code == 409
    assert ikinci.json()["type"] == "urn:talimatname:kanit-tekrari"
    assert "yeniden çekin" in ikinci.json()["title"]


def test_uc_nokta_kapsam_disi_calistirmaya_kanit_yuklenemez(tmp_path: Path) -> None:
    yonetici = _istemci(tmp_path)
    sube_muduru = _istemci(tmp_path, "branch_manager")
    kadikoy_disi = next(
        r for r in yonetici.get("/api/v1/runs").json() if not r["branch_name"].startswith("Kadıköy")
    )
    baytlar, ozet = _foto(b"kapsam-disi-kare")

    yanit = sube_muduru.post(
        f"/api/v1/runs/{kadikoy_disi['id']}/answers/{uuid4()}/evidence",
        json={
            "item_id": str(UUID(int=9)),
            "sha256": ozet,
            "content_type": "image/jpeg",
            "size_bytes": len(baytlar),
        },
    )

    assert yanit.status_code == 403
