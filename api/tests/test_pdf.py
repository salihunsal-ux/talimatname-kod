"""Rapor PDF'leri (ST-145, ST-092; FR-1220, FR-1214).

İddia: **kâğıda basılan şey doğru ve okunabilir.** Bu yüzden testler
"bayt üretildi" demiyor, PDF'i geri okuyup içindeki yazıyı sınıyor —
Türkçe harfler dahil. Damgada öğrenildi (ST-040): yazı tipi Türkçe
yazamadığında çıktı sessizce kutu kutu oluyor ve bunu ancak insan
görüyor.
"""

from __future__ import annotations

import io
from datetime import UTC, date, datetime, timedelta
from uuid import UUID

import pytest
from pypdf import PdfReader
from reportlab.lib.enums import TA_RIGHT
from reportlab.platypus import Paragraph

from talimatname.domain.reports import BranchSummary, Counters, Measurement, MonthlySummary
from talimatname.services.pdf import (
    Brand,
    _tablo,
    document_code,
    measurements_pdf,
    monthly_pdf,
)
from talimatname.services.reports import MeasurementSeries

MARKA = Brand(name="Kahve Durağı")
URETIM = datetime(2026, 11, 2, 7, 30, tzinfo=UTC)

KADIKOY = UUID("11111111-1111-5111-8111-111111111111")
BESIKTAS = UUID("22222222-2222-5222-8222-222222222222")
MADDE = UUID("33333333-3333-5333-8333-333333333333")


def _metin(baytlar: bytes) -> str:
    """PDF'in bütün sayfalarının yazısı tek dize."""
    okuyucu = PdfReader(io.BytesIO(baytlar))
    return "\n".join(sayfa.extract_text() or "" for sayfa in okuyucu.pages)


def _ozet(**ek: object) -> MonthlySummary:
    varsayilan: dict[str, object] = {
        "year": 2026,
        "month": 10,
        "first_day": date(2026, 10, 1),
        "last_day": date(2026, 10, 31),
        "counters": Counters(
            total=62, on_time=50, late=6, missed=4, open=2, failed=3, not_done_items=5
        ),
        "branches": (
            BranchSummary(
                branch_id=KADIKOY,
                branch_code="KDK",
                branch_name="Kadıköy",
                counters=Counters(total=31, on_time=28, late=2, missed=1, failed=1),
            ),
            BranchSummary(
                branch_id=BESIKTAS,
                branch_code="BSK",
                branch_name="Beşiktaş",
                counters=Counters(total=31, on_time=22, late=4, missed=3, failed=2),
            ),
        ),
    }
    return MonthlySummary(**(varsayilan | ek))  # type: ignore[arg-type]


def _seri(*degerler: float) -> MeasurementSeries:
    return MeasurementSeries(
        item_id=MADDE,
        item_title="Süt dolabı sıcaklığı",
        unit="°C",
        min_value=0.0,
        max_value=4.0,
        points=tuple(
            Measurement(
                run_id=UUID(int=sira, version=5),
                branch_id=KADIKOY if sira % 2 else BESIKTAS,
                item_id=MADDE,
                item_title="Süt dolabı sıcaklığı",
                measured_at=datetime(2026, 10, 5, 6, 15, tzinfo=UTC) + timedelta(days=sira),
                value=deger,
                unit="°C",
                min_value=0.0,
                max_value=4.0,
            )
            for sira, deger in enumerate(degerler)
        ),
    )


# --- aylık özet (FR-1220) --------------------------------------------


def test_aylik_pdf_uretilir_ve_okunur() -> None:
    baytlar = monthly_pdf(_ozet(), brand=MARKA, generated_at=URETIM, generated_by="Cem Yönetici")

    assert baytlar.startswith(b"%PDF")
    metin = _metin(baytlar)
    assert "Ekim 2026" in metin
    assert "Kahve Durağı" in metin
    assert "Cem Yönetici" in metin


def test_aylik_pdf_turkce_harfleri_basiyor() -> None:
    """Şube adları kâğıtta bozulmadan görünmeli: ş, ğ, İ, ı.

    Gömülü yazı tipiyle "Kadıköy" kutu kutu çıkıyordu; kayıtlı yazı
    tipi Türkçe sınamasından geçiyor (services/imaging).
    """
    metin = _metin(monthly_pdf(_ozet(), brand=MARKA, generated_at=URETIM, generated_by="Ayşe Şube"))

    assert "Kadıköy" in metin
    assert "Beşiktaş" in metin
    assert "Şube kırılımı" in metin
    assert "Ayşe Şube" in metin


def test_aylik_pdf_sayaclari_ve_yuzdeyi_yaziyor() -> None:
    metin = _metin(monthly_pdf(_ozet(), brand=MARKA, generated_at=URETIM, generated_by="Cem"))

    # 50 / (50+6+4) = %83
    assert "%83" in metin
    assert "62 çalıştırma" in metin
    assert "Yapılamadı işaretli madde: 5" in metin


def test_aylik_pdf_olculemeyen_yuzde_tire_basiyor() -> None:
    """Kapanmış çalıştırma yoksa %0 değil `—`: sıfır yanlış okunur."""
    ozet = _ozet(
        counters=Counters(total=3, open=3),
        branches=(
            BranchSummary(
                branch_id=KADIKOY,
                branch_code="KDK",
                branch_name="Kadıköy",
                counters=Counters(total=3, open=3),
            ),
        ),
    )

    metin = _metin(monthly_pdf(ozet, brand=MARKA, generated_at=URETIM, generated_by="Cem"))

    assert "%0" not in metin
    assert "—" in metin


def test_aylik_pdf_sube_yoksa_aciklama_yaziyor() -> None:
    """Boş tablo yerine cümle: kâğıdı okuyan neden boş olduğunu bilsin."""
    metin = _metin(
        monthly_pdf(
            _ozet(counters=Counters(), branches=()),
            brand=MARKA,
            generated_at=URETIM,
            generated_by="Cem",
        )
    )

    assert "şube kaydı yok" in metin


# --- ölçüm günlüğü (FR-1214) -----------------------------------------


def test_olcum_pdf_araliga_gore_isaretliyor() -> None:
    """Aralık dışı ölçüm **kelimeyle** işaretli: fotokopide renk kaybolur."""
    metin = _metin(
        measurements_pdf(
            [_seri(2.0, 7.5, 3.0)],
            brand=MARKA,
            first_day=date(2026, 10, 1),
            last_day=date(2026, 10, 31),
            branch_codes={KADIKOY: "KDK", BESIKTAS: "BSK"},
            generated_at=URETIM,
            generated_by="Deniz Kalite",
        )
    )

    assert "Ölçüm günlüğü" in metin
    assert "Süt dolabı sıcaklığı" in metin
    assert "aralık dışı" in metin
    assert "1 tanesi aralık dışı" in metin
    assert "7,5" in metin  # ondalık ayırıcı virgül
    assert "KDK" in metin


def test_olcum_pdf_bos_donem_aciklamali() -> None:
    metin = _metin(
        measurements_pdf(
            [],
            brand=MARKA,
            first_day=date(2026, 10, 1),
            last_day=date(2026, 10, 31),
            branch_codes={},
            generated_at=URETIM,
            generated_by="Deniz",
        )
    )

    assert "ölçüm kaydı yok" in metin


def test_olcum_pdf_cok_sayfaya_tasiyor() -> None:
    """80 ölçüm bir sayfaya sığmaz: tablo başlığı her sayfada tekrarlar."""
    baytlar = measurements_pdf(
        [_seri(*[2.0 + (sira % 3) for sira in range(80)])],
        brand=MARKA,
        first_day=date(2026, 10, 1),
        last_day=date(2026, 12, 31),
        branch_codes={KADIKOY: "KDK", BESIKTAS: "BSK"},
        generated_at=URETIM,
        generated_by="Deniz",
    )

    okuyucu = PdfReader(io.BytesIO(baytlar))
    assert len(okuyucu.pages) > 1
    for sayfa in okuyucu.pages:
        yazi = sayfa.extract_text() or ""
        assert "Belge kodu" in yazi, "sayfa altı her sayfada olmalı"


# --- belge kodu -------------------------------------------------------


def test_belge_kodu_icerikten_turiyor() -> None:
    """Aynı veri aynı kod; tek sayı değişince kod değişir."""
    bir = monthly_pdf(_ozet(), brand=MARKA, generated_at=URETIM, generated_by="Cem")
    iki = monthly_pdf(
        _ozet(),
        brand=MARKA,
        generated_at=datetime(2027, 1, 1, tzinfo=UTC),
        generated_by="Başkası",
    )
    uc = monthly_pdf(
        _ozet(counters=Counters(total=63, on_time=51, late=6, missed=4, open=2)),
        brand=MARKA,
        generated_at=URETIM,
        generated_by="Cem",
    )

    assert _kod(bir) == _kod(iki), "üretim zamanı kodu değiştirmemeli"
    assert _kod(bir) != _kod(uc), "veri değişince kod değişmeli"


def test_belge_kodu_bicimi() -> None:
    kod = document_code(["a", 1])
    assert len(kod) == 14
    assert kod.count("-") == 2
    assert kod.replace("-", "").isalnum()


def _kod(baytlar: bytes) -> str:
    metin = _metin(baytlar)
    satir = next(s for s in metin.splitlines() if "Belge kodu:" in s)
    return satir.split("Belge kodu:")[1].strip()


# --- yazı tipi --------------------------------------------------------


def test_yazi_tipi_yoksa_rapor_uretilmez(monkeypatch: pytest.MonkeyPatch) -> None:
    """Bozuk (kutu kutu) bir denetim raporu, rapor olmamasından kötü."""
    from talimatname.services import imaging, pdf

    pdf.register_fonts.cache_clear()
    monkeypatch.setattr(imaging, "FONT_CANDIDATES", ())

    with pytest.raises(imaging.FontMissing):
        monthly_pdf(_ozet(), brand=MARKA, generated_at=URETIM, generated_by="Cem")

    pdf.register_fonts.cache_clear()


def test_marka_adi_kagitta_iki_kez_yazilmaz() -> None:
    """Kurulum bitmemişken marka, ürünün adına düşüyor (`brand_for`).

    Alt bilgi "zincir · ürün · zaman" yazıyor; ikisi aynı olunca
    kâğıdın tepesinde "Talimatname · Talimatname" görünüyordu.
    """
    from talimatname.services.pdf import URUN_ADI, brand_for

    marka = brand_for(None)

    assert marka.name == URUN_ADI
    alt = " · ".join(dict.fromkeys([marka.name, URUN_ADI, "02.11.2026 19:47"]))
    assert alt.count(URUN_ADI) == 1, alt


def test_zincir_adi_varsa_ikisi_de_yaziliyor() -> None:
    """Ad farklıysa ikisi de görünmeli: kâğıt kimin, hangi ürünle."""
    from talimatname.services.pdf import URUN_ADI

    alt = " · ".join(dict.fromkeys(["Kahve Durağı", URUN_ADI, "02.11.2026 19:47"]))

    assert "Kahve Durağı" in alt
    assert URUN_ADI in alt


def test_b14_tablo_basliklari_sarilabiliyor() -> None:
    """Başlık hücresi Paragraph: düz metin reportlab'da sarılmıyor.

    "Zamanındalık" dar sütuna sığmayıp komşu sütunun sınırına
    dayanıyordu (bağımsız test turu B14). Gövde düz metin kalmalı:
    sayıları Paragraph'a çevirmek hizalamayı bozardı.
    """
    tablo = _tablo(
        [["Şube", "Zamanındalık"], ["Kadıköy", "%91"]],
        genislikler=[100, 40],
        saga_yatik=[1],
    )

    baslik, govde = tablo._cellvalues  # type: ignore[attr-defined]
    assert all(isinstance(h, Paragraph) for h in baslik)
    assert all(isinstance(h, str) for h in govde)
    assert baslik[1].style.alignment == TA_RIGHT
