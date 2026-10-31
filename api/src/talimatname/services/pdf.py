"""Rapor PDF'leri (ST-145, ST-092; FR-1220, FR-1214).

Ürünün satış cümlesi "denetim geldiğinde üç dakika". Bu dosya o
cümlenin somut çıktısı: ekranda duran ayı ve ölçüm günlüğünü
denetçinin eline verilebilecek bir kâğıda çeviriyor.

Üç karar burada yazılı duruyor:

**Neden reportlab, WeasyPrint değil.** WeasyPrint HTML'i CSS ile
dizerdi — ekranla aynı şablonu paylaşmak cazip. Ama cairo ve pango
sistem kütüphanelerini ister: Windows'ta geliştirme, imajda boyut.
Rapor sayısı üç ve hepsi tablo; HTML'in esnekliği bu işi
karşılamıyordu.

**Yazı tipi dışarıdan gelir ve Türkçe harfleri sınanır.** Damgada
öğrenildi (ST-040): gömülü yazı tiplerinde ş, ğ, İ yok ve "Kadıköy"
kutu kutu çıkıyor. Denetçiye bozuk şube adı veren bir PDF, hiç PDF
olmamasından kötü — bu yüzden yazı tipi bulunamazsa rapor
**üretilmez** (`FontMissing`), bozuk üretilmez.

**Belge kodu içeriğin özeti.** Sayfa altındaki kod raporun
**verisinden** türetiliyor (SHA-256, ilk 12 hane): aynı ay iki kez
dökülünce aynı kod çıkar, bir sayı değişince kod değişir. FR-1218'in
istediği **olay günlüğü zincirine bağlama** bu değil; zincir
(FR-1301) kodda henüz yok. Bu yüzden kâğıtta "doğrulama kodu" değil
"belge kodu" yazıyor ve ne olduğu dipnotta duruyor. Zincir gelince
kod ondan türetilecek, kâğıdın biçimi değişmeyecek.
"""

from __future__ import annotations

import hashlib
import io
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

import structlog
from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate,
    Flowable,
    Frame,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

from talimatname.domain.reports import MonthlySummary
from talimatname.services.imaging import FontMissing, find_font
from talimatname.services.reports import MeasurementSeries

log = structlog.get_logger(__name__)

#: Kayıtlı yazı tipi adları (reportlab kendi ad alanında tutuyor).
FONT_NORMAL = "TalimatGovde"
FONT_BOLD = "TalimatGovdeKalin"

#: Kalın yüzün adaylarında aranan ekler. Bulunamazsa normal yüz iki
#: kez kaydedilir: kalınsız bir rapor, yazı tipsiz rapordan iyidir.
BOLD_SUFFIXES: tuple[tuple[str, str], ...] = (
    ("segoeui.ttf", "segoeuib.ttf"),
    ("arial.ttf", "arialbd.ttf"),
    ("DejaVuSans.ttf", "DejaVuSans-Bold.ttf"),
    ("LiberationSans-Regular.ttf", "LiberationSans-Bold.ttf"),
    ("NotoSans-Regular.ttf", "NotoSans-Bold.ttf"),
    ("Arial.ttf", "Arial Bold.ttf"),
)

SAYFA = A4
KENAR = 18 * mm
#: Alt boşluk dipnot ve sayfa numarası için; üst boşluk başlık bandı için.
ALT_BOSLUK = 20 * mm

AY_ADLARI = (
    "Ocak",
    "Şubat",
    "Mart",
    "Nisan",
    "Mayıs",
    "Haziran",
    "Temmuz",
    "Ağustos",
    "Eylül",
    "Ekim",
    "Kasım",
    "Aralık",
)

#: Aralık dışı ölçümün kâğıttaki karşılığı. Simge değil **kelime**:
#: fotokopide ve siyah-beyaz çıktıda renk kayboluyor, kelime kalıyor.
ARALIK_DISI = "aralık dışı"

RENK_BASLIK = colors.HexColor("#1f2937")
RENK_SATIR = colors.HexColor("#f3f4f6")
RENK_CIZGI = colors.HexColor("#d1d5db")
RENK_UYARI = colors.HexColor("#b91c1c")
RENK_SOLUK = colors.HexColor("#6b7280")


@dataclass(frozen=True, slots=True)
class Brand:
    """Kâğıdın üstünde görünen hesap: marka adı ve saat dilimi.

    Saat dilimi biçimlendirme için şart: kayıtlar UTC duruyor, denetçi
    yerel saati okuyor (FR-0905).
    """

    name: str
    timezone: str = "Europe/Istanbul"

    @property
    def zone(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)


def _kalin_aday(normal: str) -> str | None:
    for ek, kalin in BOLD_SUFFIXES:
        if normal.endswith(ek):
            aday = Path(normal[: -len(ek)] + kalin)
            if aday.is_file():
                return str(aday)
    return None


@lru_cache
def register_fonts(preferred: str | None = None) -> tuple[str, str]:
    """Türkçe yazabilen yazı tipini reportlab'a kaydeder; yoksa `FontMissing`.

    Damgayla **aynı** arama ve aynı Türkçe sınaması kullanılıyor
    (`services.imaging.find_font`): iki çıktının aynı yazı tipinde
    buluşması bir yan etki değil, istenen şey.
    """
    _, yol = find_font(12, preferred=preferred)
    pdfmetrics.registerFont(TTFont(FONT_NORMAL, yol))

    kalin = _kalin_aday(yol)
    pdfmetrics.registerFont(TTFont(FONT_BOLD, kalin or yol))
    if kalin is None:
        log.warning("pdf.kalin_yazi_tipi_yok", yol=yol)
    log.info("pdf.yazi_tipi", normal=yol, kalin=kalin)
    return yol, kalin or yol


def document_code(parts: Iterable[object]) -> str:
    """İçerikten türetilen belge kodu: `XXXX-XXXX-XXXX`.

    Üretim zamanı **girmiyor**: kod dosyayı değil içeriği adlandırıyor,
    aynı ay iki kez dökülünce aynı kod çıkıyor.
    """
    ham = "\u001f".join(str(p) for p in parts)
    ozet = hashlib.sha256(ham.encode("utf-8")).hexdigest()[:12].upper()
    return f"{ozet[:4]}-{ozet[4:8]}-{ozet[8:]}"


def _stiller() -> dict[str, ParagraphStyle]:
    register_fonts()
    return {
        "baslik": ParagraphStyle(
            "baslik", fontName=FONT_BOLD, fontSize=16, leading=20, textColor=RENK_BASLIK
        ),
        "alt": ParagraphStyle(
            "alt", fontName=FONT_NORMAL, fontSize=9.5, leading=13, textColor=RENK_SOLUK
        ),
        "bolum": ParagraphStyle(
            "bolum",
            fontName=FONT_BOLD,
            fontSize=11,
            leading=15,
            textColor=RENK_BASLIK,
            spaceBefore=8,
            spaceAfter=4,
        ),
        "govde": ParagraphStyle("govde", fontName=FONT_NORMAL, fontSize=9.5, leading=13),
        "dipnot": ParagraphStyle(
            "dipnot", fontName=FONT_NORMAL, fontSize=7.5, leading=10, textColor=RENK_SOLUK
        ),
        "sag": ParagraphStyle(
            "sag", fontName=FONT_NORMAL, fontSize=9.5, leading=13, alignment=TA_RIGHT
        ),
    }


def _zaman(an: datetime, zone: ZoneInfo) -> str:
    return an.astimezone(zone).strftime("%d.%m.%Y %H:%M")


def _gun(gun: date) -> str:
    return gun.strftime("%d.%m.%Y")


def _sayi(deger: float) -> str:
    """Ondalık ayırıcı virgül; tam sayı ise ondalık basılmaz."""
    if float(deger).is_integer():
        return str(int(deger))
    return f"{deger:.1f}".replace(".", ",")


def _yuzde(deger: int | None) -> str:
    """Ölçülemeyen yüzde `—`: sıfır yazmak 'hiçbiri zamanında değil' derdi."""
    return "—" if deger is None else f"%{deger}"


class _Belge(BaseDocTemplate):
    """Sayfa altını (marka · zaman · belge kodu · sayfa) kendisi basar."""

    def __init__(self, tampon: io.BytesIO, *, alt_metin: str, kod: str) -> None:
        super().__init__(
            tampon,
            pagesize=SAYFA,
            leftMargin=KENAR,
            rightMargin=KENAR,
            topMargin=KENAR,
            bottomMargin=ALT_BOSLUK,
            title="Talimatname raporu",
            author="Talimatname",
        )
        self._alt_metin = alt_metin
        self._kod = kod
        cerceve = Frame(
            KENAR,
            ALT_BOSLUK,
            SAYFA[0] - 2 * KENAR,
            SAYFA[1] - KENAR - ALT_BOSLUK,
            id="govde",
        )
        self.addPageTemplates([PageTemplate(id="tek", frames=[cerceve], onPage=self._alt_bilgi)])

    def _alt_bilgi(self, tuval: object, _belge: object) -> None:
        from reportlab.pdfgen.canvas import Canvas

        assert isinstance(tuval, Canvas)
        tuval.saveState()
        tuval.setFont(FONT_NORMAL, 7.5)
        tuval.setFillColor(RENK_SOLUK)
        tuval.drawString(KENAR, ALT_BOSLUK - 11 * mm, self._alt_metin)
        tuval.drawString(KENAR, ALT_BOSLUK - 14.5 * mm, f"Belge kodu: {self._kod}")
        tuval.drawRightString(
            SAYFA[0] - KENAR, ALT_BOSLUK - 11 * mm, f"Sayfa {tuval.getPageNumber()}"
        )
        tuval.setStrokeColor(RENK_CIZGI)
        tuval.line(KENAR, ALT_BOSLUK - 8 * mm, SAYFA[0] - KENAR, ALT_BOSLUK - 8 * mm)
        tuval.restoreState()


def _tablo(
    satirlar: Sequence[Sequence[object]],
    *,
    genislikler: Sequence[float],
    vurgulu: Sequence[int] = (),
    saga_yatik: Sequence[int] = (),
) -> Table:
    """Başlık satırı koyu, tek satırlar gri; `vurgulu` satırlar kırmızı."""
    tablo = Table([list(satir) for satir in satirlar], colWidths=list(genislikler), repeatRows=1)
    # reportlab biçim komutları heterojen demetler: tipi kütüphane
    # kendi içinde çözüyor, burada Any kalıyor.
    bicim: list[Any] = [
        ("FONTNAME", (0, 0), (-1, 0), FONT_BOLD),
        ("FONTNAME", (0, 1), (-1, -1), FONT_NORMAL),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("BACKGROUND", (0, 0), (-1, 0), RENK_BASLIK),
        ("GRID", (0, 0), (-1, -1), 0.4, RENK_CIZGI),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]
    for sira in range(1, len(satirlar)):
        if sira % 2 == 0:
            bicim.append(("BACKGROUND", (0, sira), (-1, sira), RENK_SATIR))
    for sira in vurgulu:
        bicim.append(("TEXTCOLOR", (0, sira), (-1, sira), RENK_UYARI))
    for sutun in saga_yatik:
        bicim.append(("ALIGN", (sutun, 0), (sutun, -1), "RIGHT"))
    tablo.setStyle(TableStyle(bicim))
    return tablo


def _baslik_blogu(
    stil: dict[str, ParagraphStyle],
    *,
    brand: Brand,
    baslik: str,
    donem: str,
    generated_at: datetime,
    generated_by: str,
) -> list[Flowable]:
    return [
        Paragraph(brand.name, stil["alt"]),
        Paragraph(baslik, stil["baslik"]),
        Paragraph(
            f"{donem} · {_zaman(generated_at, brand.zone)} tarihinde {generated_by} tarafından "
            f"üretildi · saat dilimi {brand.timezone}",
            stil["alt"],
        ),
        Spacer(1, 8),
    ]


def _dipnot(stil: dict[str, ParagraphStyle]) -> list[Flowable]:
    return [
        Spacer(1, 10),
        Paragraph(
            "Belge kodu bu raporun verisinden türetilmiştir (SHA-256): aynı veri aynı kodu "
            "verir, tek bir sayı değişirse kod değişir. Kodun olay günlüğü zincirine "
            "bağlanması ve çevrimiçi doğrulama sayfası sonraki sürümde (FR-1218).",
            stil["dipnot"],
        ),
    ]


def monthly_pdf(
    summary: MonthlySummary,
    *,
    brand: Brand,
    generated_at: datetime,
    generated_by: str,
) -> bytes:
    """Aylık tek sayfa özet (FR-1220): toplam sayaçlar + şube kırılımı.

    Şube sıralaması ekranla aynı: zamanındalığı en düşük önce
    (`MonthlySummary.worst_branches`). Denetim konuşması oradan
    başlıyor, kâğıt da oradan başlasın.
    """
    stil = _stiller()
    sayac = summary.counters
    kod = document_code(
        [
            "aylik",
            brand.name,
            summary.year,
            summary.month,
            sayac.total,
            sayac.on_time,
            sayac.late,
            sayac.missed,
            sayac.cancelled,
            sayac.open,
            sayac.failed,
            sayac.not_done_items,
            *[
                (s.branch_code, s.counters.total, s.counters.on_time, s.counters.missed)
                for s in summary.worst_branches
            ],
        ]
    )

    ic: list[Flowable] = _baslik_blogu(
        stil,
        brand=brand,
        baslik=f"{AY_ADLARI[summary.month - 1]} {summary.year} · aylık özet",
        donem=f"{_gun(summary.first_day)} – {_gun(summary.last_day)}",
        generated_at=generated_at,
        generated_by=generated_by,
    )

    genislik = SAYFA[0] - 2 * KENAR
    ic.append(
        _tablo(
            [
                ["Zamanında", "Geç", "Kaçırıldı", "Yapılmayacak", "Açık", "Zamanındalık"],
                [
                    sayac.on_time,
                    sayac.late,
                    sayac.missed,
                    sayac.cancelled,
                    sayac.open,
                    _yuzde(sayac.on_time_percent),
                ],
            ],
            genislikler=[genislik / 6] * 6,
            saga_yatik=range(6),
        )
    )
    ic.append(Spacer(1, 6))
    ic.append(
        Paragraph(
            f"Dönemde {sayac.total} çalıştırma; {sayac.closed} tanesi kapandı. "
            f"Başarısız çalıştırma: {sayac.failed}. "
            f"Yapılamadı işaretli madde: {sayac.not_done_items}. "
            "Açık pencereler yüzdeye girmiyor.",
            stil["govde"],
        )
    )

    ic.append(Paragraph("Şube kırılımı", stil["bolum"]))
    satirlar: list[Sequence[object]] = [
        ["Şube", "Kod", "Toplam", "Zamanında", "Geç", "Kaçırıldı", "Başarısız", "Zamanındalık"]
    ]
    vurgulu: list[int] = []
    for sube in summary.worst_branches:
        s = sube.counters
        satirlar.append(
            [
                sube.branch_name,
                sube.branch_code,
                s.total,
                s.on_time,
                s.late,
                s.missed,
                s.failed,
                _yuzde(s.on_time_percent),
            ]
        )
        if s.missed or s.failed:
            vurgulu.append(len(satirlar) - 1)
    if len(satirlar) == 1:
        ic.append(Paragraph("Bu ayda kapsamınızda şube kaydı yok.", stil["govde"]))
    else:
        oran = [0.26, 0.09, 0.1, 0.12, 0.08, 0.11, 0.11, 0.13]
        ic.append(
            _tablo(
                satirlar,
                genislikler=[genislik * o for o in oran],
                vurgulu=vurgulu,
                saga_yatik=range(2, 8),
            )
        )

    ic.extend(_dipnot(stil))
    return _uret(ic, brand=brand, kod=kod, generated_at=generated_at)


def measurements_pdf(
    series: Sequence[MeasurementSeries],
    *,
    brand: Brand,
    first_day: date,
    last_day: date,
    branch_codes: Mapping[UUID, str],
    generated_at: datetime,
    generated_by: str,
) -> bytes:
    """Dönem PDF'i: ölçüm günlüğü biçimi (FR-1214, FR-1207).

    Soğuk zincir denetiminin istediği kâğıt bu: ne, nerede, ne zaman,
    kaç — ve aralıkta mı. Aralık dışı satırlar hem kırmızı hem
    **kelimeyle** işaretli: fotokopide renk kayboluyor.
    """
    stil = _stiller()
    kod = document_code(
        [
            "olcum",
            brand.name,
            first_day,
            last_day,
            *[
                (s.item_id, len(s.points), s.out_of_range_count, *[n.value for n in s.points])
                for s in series
            ],
        ]
    )

    ic: list[Flowable] = _baslik_blogu(
        stil,
        brand=brand,
        baslik="Ölçüm günlüğü",
        donem=f"{_gun(first_day)} – {_gun(last_day)}",
        generated_at=generated_at,
        generated_by=generated_by,
    )

    genislik = SAYFA[0] - 2 * KENAR
    if not series:
        ic.append(
            Paragraph(
                "Bu dönemde kapsamınızda ölçüm kaydı yok. Sıcaklık ve sayı maddeleri "
                "cevaplandıkça günlük kendiliğinden dolar.",
                stil["govde"],
            )
        )
        ic.extend(_dipnot(stil))
        return _uret(ic, brand=brand, kod=kod, generated_at=generated_at)

    for seri in series:
        aralik = _aralik_metni(seri)
        basliklar = [f"{seri.item_title}"]
        if seri.unit:
            basliklar.append(f"birim {seri.unit}")
        if aralik:
            basliklar.append(aralik)
        ic.append(Paragraph(" · ".join(basliklar), stil["bolum"]))
        ic.append(
            Paragraph(
                f"{len(seri.points)} ölçüm, {seri.out_of_range_count} tanesi aralık dışı.",
                stil["govde"],
            )
        )
        satirlar: list[Sequence[object]] = [["Tarih · saat", "Şube", "Değer", "Durum"]]
        vurgulu: list[int] = []
        for nokta in seri.points:
            satirlar.append(
                [
                    _zaman(nokta.measured_at, brand.zone) if nokta.measured_at else "—",
                    branch_codes.get(nokta.branch_id, "—"),
                    _sayi(nokta.value) + (f" {seri.unit}" if seri.unit else ""),
                    ARALIK_DISI if nokta.out_of_range else "uygun",
                ]
            )
            if nokta.out_of_range:
                vurgulu.append(len(satirlar) - 1)
        ic.append(
            _tablo(
                satirlar,
                genislikler=[genislik * o for o in (0.3, 0.22, 0.24, 0.24)],
                vurgulu=vurgulu,
                saga_yatik=(2,),
            )
        )
        ic.append(Spacer(1, 6))

    ic.extend(_dipnot(stil))
    return _uret(ic, brand=brand, kod=kod, generated_at=generated_at)


def _aralik_metni(seri: MeasurementSeries) -> str:
    if seri.min_value is not None and seri.max_value is not None:
        return f"aralık {_sayi(seri.min_value)} – {_sayi(seri.max_value)}"
    if seri.min_value is not None:
        return f"en az {_sayi(seri.min_value)}"
    if seri.max_value is not None:
        return f"en çok {_sayi(seri.max_value)}"
    return ""


def _uret(ic: list[Flowable], *, brand: Brand, kod: str, generated_at: datetime) -> bytes:
    tampon = io.BytesIO()
    belge = _Belge(
        tampon,
        alt_metin=f"{brand.name} · Talimatname · {_zaman(generated_at, brand.zone)}",
        kod=kod,
    )
    belge.build(ic)
    return tampon.getvalue()


__all__ = [
    "Brand",
    "FontMissing",
    "document_code",
    "measurements_pdf",
    "monthly_pdf",
    "register_fonts",
]
