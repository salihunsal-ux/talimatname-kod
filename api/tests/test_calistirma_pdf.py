"""Çalıştırma PDF'i (ST-091; FR-1213, FR-1218; TC-095).

İddia: **denetçinin eline verilen kâğıt eksiksiz.** TC-095'in istediği
altı şey kâğıtta olmalı — maddeler, cevaplar, küçük resimler, zaman
damgaları, doğrulama kodu ve marka. Testler PDF'i geri okuyup bunları
arıyor; "bayt üretildi" demek bu soruyu cevaplamıyor.
"""

from __future__ import annotations

import hashlib
import io
import itertools
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from pypdf import PdfReader

from conftest import oturum_ac
from talimatname.api import bagimliliklar
from talimatname.api.app import create_app
from talimatname.infra.memory import (
    MemoryAnswerRepository,
    MemoryAuditRepository,
    MemoryEvidenceRepository,
    MemoryOrganizationRepository,
    MemoryPlanRepository,
    MemoryTemplateRepository,
    MemoryUserRepository,
    sabit_id,
)
from talimatname.services.audit import AuditService
from talimatname.services.evidence import EvidenceService
from talimatname.services.execution import ExecutionService
from talimatname.services.exports import ExportService
from talimatname.services.pdf import Brand, run_code, run_pdf
from talimatname.services.plans import PlanService
from talimatname.services.storage import LocalObjectStore
from talimatname.settings import Settings

KADIKOY = sabit_id("sube:KDK")
PERSONEL = "+905321110005"
MARKA = Brand(name="Kahve Durağı")
URETIM = datetime(2026, 11, 3, 8, 0, tzinfo=UTC)


#: Her kanıt farklı bayt olmalı: aynı özet ikinci kez kabul edilmiyor
#: (FR-0614 tekilliği). Sayaçla renk değiştiriyoruz.
_SAYAC = itertools.count()


def _resim(renk: tuple[int, int, int] | None = None) -> tuple[bytes, str]:
    sira = next(_SAYAC)
    tampon = io.BytesIO()
    Image.new("RGB", (320, 240), renk or (40 + sira * 7, 90, 140)).save(tampon, format="JPEG")
    baytlar = tampon.getvalue()
    return baytlar, hashlib.sha256(baytlar).hexdigest()


def _metin(baytlar: bytes) -> str:
    return "\n".join(s.extract_text() or "" for s in PdfReader(io.BytesIO(baytlar)).pages)


class Dunya:
    """Gerçek servislerle kurulu küçük bir dünya: tek şube, tek çalıştırma."""

    def __init__(self, tmp: Path) -> None:
        self.an = datetime.now(UTC)
        self.planlar = MemoryPlanRepository()
        self.org = MemoryOrganizationRepository()
        self.sablonlar = MemoryTemplateRepository()
        self.kullanicilar = MemoryUserRepository()
        PlanService(self.planlar, self.org, self.sablonlar, now=lambda: self.an).generate_all()

        self.izi = AuditService(MemoryAuditRepository(), now=lambda: self.an)
        self.kanit = EvidenceService(
            MemoryEvidenceRepository(),
            self.planlar,
            self.org,
            LocalObjectStore(tmp),
            self.kullanicilar,
            settings=Settings(environment="dev"),
            audit=self.izi,
            now=lambda: self.an,
        )
        self.yurutme = ExecutionService(
            MemoryAnswerRepository(),
            self.planlar,
            self.sablonlar,
            # Gönderim kapısı kanıtı **sayıyor** (FR-0607); üretimdeki
            # bağlantının aynısı, yoksa fotoğraflı madde hep eksik görünür.
            verified_evidence=lambda run_id: self.kanit.verified_counts(run_id),
            audit=self.izi,
            now=lambda: self.an,
        )
        self.disa = ExportService(
            self.yurutme,
            self.kanit,
            self.org,
            self.sablonlar,
            self.kullanicilar,
            self.izi,
            now=lambda: self.an,
        )
        # Penceresi **açık** bir çalıştırma: tohumda kapanmış olanlar
        # da var ve onlara cevap yazılamıyor (testi duvar saatine
        # bağlamamak için durumdan seçiyoruz, sıradan değil).
        self.run = next(
            r
            for r in self.planlar.runs()
            if r.branch_id == KADIKOY
            and r.status in ("scheduled", "in_progress")
            and r.tolerance_end > self.an
        )
        kisi = self.kullanicilar.user_by_phone(PERSONEL)
        assert kisi is not None
        self.kisi = kisi

    @property
    def maddeler(self) -> list[object]:
        surum = self.sablonlar.version(self.run.template_version_id)
        assert surum is not None
        return list(surum.items)

    def cevapla(self, madde_id: UUID, durum: str, **ek: object) -> None:
        self.yurutme.write_answer(
            run_id=self.run.id,
            answer_id=uuid4(),
            item_id=madde_id,
            state=durum,
            user_id=self.kisi.id,
            **ek,  # type: ignore[arg-type]
        )

    def kanit_ekle(self, madde_id: UUID, renk: tuple[int, int, int] | None = None) -> None:
        baytlar, ozet = _resim(renk)
        kanit, belirtec = self.kanit.start(
            run_id=self.run.id,
            answer_id=uuid4(),
            item_id=madde_id,
            sha256=ozet,
            content_type="image/jpeg",
            size_bytes=len(baytlar),
            user_id=self.kisi.id,
        )
        self.kanit.receive(belirtec, baytlar)
        self.kanit.complete(kanit.id)
        self.kanit.stamp_pending()


@pytest.fixture
def dunya(tmp_path: Path) -> Dunya:
    return Dunya(tmp_path)


# --- içerik (TC-095) ---------------------------------------------------


def test_kagitta_maddeler_ve_cevaplar_var(dunya: Dunya) -> None:
    ilk = dunya.maddeler[0]
    dunya.cevapla(ilk.id, "passed")  # type: ignore[attr-defined]

    rapor = dunya.disa.run_report(dunya.run.id)
    metin = _metin(run_pdf(rapor, brand=MARKA, generated_at=URETIM, generated_by="Cem Yönetici"))

    assert ilk.title in metin  # type: ignore[attr-defined]
    assert "Yapıldı" in metin
    assert "Kahve Durağı" in metin  # marka
    assert "Kadıköy" in metin
    assert "Belge kodu:" in metin


def test_cevapsiz_madde_bos_birakilmiyor(dunya: Dunya) -> None:
    """Cevapsız madde kâğıtta **görünmeli**: eksik olan da kayıttır."""
    rapor = dunya.disa.run_report(dunya.run.id)

    metin = _metin(run_pdf(rapor, brand=MARKA, generated_at=URETIM, generated_by="Cem"))

    assert "Cevapsız" in metin


def test_yapilamadi_sebebi_kagida_giriyor(dunya: Dunya) -> None:
    """Yapılmayan iş sebebiyle merkeze düşer (BR-09); kâğıtta da sebebi var."""
    madde = dunya.maddeler[0]
    dunya.cevapla(
        madde.id,  # type: ignore[attr-defined]
        "not_done",
        not_done_reason="no_material",
        note="Deterjan bitti",
    )

    rapor = dunya.disa.run_report(dunya.run.id)
    metin = _metin(run_pdf(rapor, brand=MARKA, generated_at=URETIM, generated_by="Cem"))

    assert "Yapılamadı" in metin
    assert "Malzeme yok" in metin
    assert "Deterjan bitti" in metin


def test_kanit_kucuk_resmi_kagida_basiliyor(dunya: Dunya) -> None:
    """TC-095: küçük resimler kâğıtta. Varlığını dosya boyutundan okuyoruz.

    PDF metninde görsel görünmez; gömülü XObject sayısı bakmanın en
    doğrudan yolu.
    """
    madde = next(m for m in dunya.maddeler if getattr(m, "photo_required", False))
    dunya.cevapla(madde.id, "passed")  # type: ignore[attr-defined]
    dunya.kanit_ekle(madde.id)  # type: ignore[attr-defined]

    rapor = dunya.disa.run_report(dunya.run.id)
    baytlar = run_pdf(rapor, brand=MARKA, generated_at=URETIM, generated_by="Cem")

    assert rapor.lines
    assert any(s.photos for s in rapor.lines), "küçük resim derlenmedi"
    sayfa = PdfReader(io.BytesIO(baytlar)).pages[0]
    assert sayfa.images, "PDF'e gömülü görsel yok"


def test_eksik_kanit_raporu_dusurmez(dunya: Dunya) -> None:
    """Depoda bulunamayan dosya atlanır; kâğıt yine çıkar."""
    madde = next(m for m in dunya.maddeler if getattr(m, "photo_required", False))
    dunya.cevapla(madde.id, "passed")  # type: ignore[attr-defined]
    dunya.kanit_ekle(madde.id)  # type: ignore[attr-defined]
    for kanit in dunya.kanit.for_run(dunya.run.id):
        dunya.kanit._store.delete(kanit.key_for("thumbnail"))
        dunya.kanit._store.delete(kanit.storage_key)

    rapor = dunya.disa.run_report(dunya.run.id)
    baytlar = run_pdf(rapor, brand=MARKA, generated_at=URETIM, generated_by="Cem")

    assert baytlar.startswith(b"%PDF")
    assert all(not s.photos for s in rapor.lines)


def test_denetim_izi_ozeti_kagitta(dunya: Dunya) -> None:
    """FR-1213 'denetim izi özeti': çalıştırmaya dokunan olaylar."""
    for madde in dunya.maddeler:
        dunya.cevapla(madde.id, "passed")  # type: ignore[attr-defined]
        if getattr(madde, "photo_required", False):
            # Gönderim kapısı kanıtı **sayıyor** (FR-0607): fotoğrafı
            # zorunlu madde fotoğrafsız gönderilemez.
            dunya.kanit_ekle(madde.id)  # type: ignore[attr-defined]
    dunya.yurutme.submit(dunya.run.id, user_id=dunya.kisi.id)

    rapor = dunya.disa.run_report(dunya.run.id)
    metin = _metin(run_pdf(rapor, brand=MARKA, generated_at=URETIM, generated_by="Cem"))

    assert "Denetim izi" in metin
    assert "Çalıştırma gönderildi" in metin


def test_gunluk_yoksa_denetim_izi_basligi_basilmiyor(dunya: Dunya) -> None:
    """Boş bir başlık, iz tutulmadığını değil olay olmadığını düşündürürdü."""
    izsiz = ExportService(
        dunya.yurutme, dunya.kanit, dunya.org, dunya.sablonlar, dunya.kullanicilar, None
    )

    rapor = izsiz.run_report(dunya.run.id)
    metin = _metin(run_pdf(rapor, brand=MARKA, generated_at=URETIM, generated_by="Cem"))

    assert rapor.audit == ()
    assert "Denetim izi" not in metin


def test_icerik_kodu_veriden_turuyor(dunya: Dunya) -> None:
    ilk = dunya.disa.run_report(dunya.run.id)
    dunya.cevapla(dunya.maddeler[0].id, "passed")  # type: ignore[attr-defined]
    ikinci = dunya.disa.run_report(dunya.run.id)

    assert run_code(ilk, brand=MARKA) != run_code(ikinci, brand=MARKA)


# --- uç nokta ----------------------------------------------------------


def test_uc_nokta_pdf_doner(tmp_path: Path) -> None:
    istemci = oturum_ac(TestClient(create_app(Settings(evidence_dir=str(tmp_path)))))
    kosular = istemci.get("/api/v1/runs").json()
    assert kosular, "bugün için çalıştırma yok"

    yanit = istemci.get(f"/api/v1/runs/{kosular[0]['id']}/pdf")

    assert yanit.status_code == 200
    assert yanit.headers["content-type"] == "application/pdf"
    assert yanit.content.startswith(b"%PDF")


def test_uc_nokta_kodu_zincire_bagliyor(tmp_path: Path) -> None:
    """FR-1218: kâğıttaki kod, raporu üreten olayın zincir özeti."""
    istemci = oturum_ac(TestClient(create_app(Settings(evidence_dir=str(tmp_path)))))
    kosular = istemci.get("/api/v1/runs").json()

    yanit = istemci.get(f"/api/v1/runs/{kosular[0]['id']}/pdf")

    servis = bagimliliklar.izi_servisi()
    olay = next(
        o
        for o in reversed(servis._repo.events(limit=500))
        if o.event_type == "rapor.uretildi" and o.object_type == "calistirma"
    )
    ozet = olay.hash[:12].upper()
    assert f"Belge kodu: {ozet[:4]}-{ozet[4:8]}-{ozet[8:]}" in _metin(yanit.content)


def test_uc_nokta_kapsam_disinda_reddediyor(tmp_path: Path) -> None:
    """Kâğıt ayrı bir kapı açmamalı: en çok veri taşıyan çıktı en zayıf
    kapıdan geçerse kapsam süzgeci anlamını yitirir."""
    uygulama = create_app(Settings(evidence_dir=str(tmp_path)))
    yonetici = oturum_ac(TestClient(uygulama))
    personel = oturum_ac(TestClient(uygulama), "staff")  # yalnızca KDK

    hepsi = yonetici.get("/api/v1/runs").json()
    baska_sube = next(k for k in hepsi if "Kadıköy" not in k["branch_name"])

    yanit = personel.get(f"/api/v1/runs/{baska_sube['id']}/pdf")

    assert yanit.status_code == 403
