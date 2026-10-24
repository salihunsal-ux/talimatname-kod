"""Görsel işleme: damga ve küçük resim (ST-040; FR-0606, FR-1202, FR-1208).

Ham dosyaya **dokunulmaz** (BR-12). Burada üretilen iki şey de kopyadır:

* **Damgalı kopya** — üzerinde şube · tarih-saat · kullanıcı yazılı
  (FR-0606). Denetçiye, PDF'e, dışarıya giden kopya budur: fotoğrafın
  kendisi bağlamını taşısın, dosya adı ve veritabanı satırı olmadan da
  ne olduğu anlaşılsın.
* **Küçük resim** — panelin ızgarası için (FR-1208). **Damgasız**:
  320 pikselde damga metni okunmaz, okunmayan damga yer kaplar.

İki yan etki kasıtlı:

* **EXIF düşüyor.** Kopyalar yeniden kodlanıyor; telefonun EXIF'indeki
  GPS ve cihaz bilgisi kopyaya geçmiyor. Konum zaten kayıtta duruyor
  ve ölçülü (FR-0615); dışarı giden dosyada ikinci kez taşımak
  gereksiz kişisel veri olurdu (KVKK).
* **Yön düzeltiliyor.** Telefon fotoğrafı EXIF yönüyle kaydediyor;
  düzeltmeden damga yan yazılırdı.

Yazı tipi dışarıdan gelir ve **Türkçe harfler sınanır**: Pillow'un
gömülü yazı tipinde ş, ğ, İ yok — "Kadıköy" kutu kutu çıkardı. Denetim
kopyasına bozuk bir şube adı basmak, damgayı hiç basmamaktan kötü.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path

import structlog
from PIL import Image, ImageDraw, ImageFont, ImageOps

log = structlog.get_logger(__name__)

#: Damga bandının yüksekliği (resmin yüzdesi) ve alt/üst sınırı.
BAND_RATIO = 0.07
BAND_MIN_PX = 26
BAND_MAX_PX = 90

#: Band içindeki yazı yüksekliği ve en küçük okunabilir boy.
TEXT_RATIO = 0.52
TEXT_MIN_PX = 11

#: Satır aralığı ve en çok kaç satır. Üç satırlık bir damga fotoğrafı
#: değil kendini gösterir.
LINE_SPACING = 1.3
MAX_LINES = 2

#: Bandın koyuluğu: altındaki fotoğraf seçilsin, yazı okunsun.
BAND_ALPHA = 165

#: Küçük resmin uzun kenarı.
THUMBNAIL_MAX_EDGE = 320
THUMBNAIL_QUALITY = 78
STAMP_QUALITY = 88

#: Yazı tipi adayları. Sıra önemli: ilk bulunan ve **Türkçe harfleri
#: olan** kullanılır. Üretim imajında yazı tipi yoksa `STAMP_FONT_PATH`
#: ayarıyla gösterilir.
FONT_CANDIDATES: tuple[str, ...] = (
    "C:/Windows/Fonts/segoeui.ttf",
    "C:/Windows/Fonts/arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
    "/usr/share/fonts/TTF/DejaVuSans.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
)

#: Damgada geçebilen ve Latin-1'de **olmayan** harfler. Yazı tipi bu
#: harfleri çizemiyorsa damga basılmaz.
TURKISH_PROBE = "şŞğĞİı"


class FontMissing(Exception):
    """Türkçe harfleri çizebilen yazı tipi yok. Altyapı durumu, alan hatası değil."""


@dataclass(frozen=True, slots=True)
class FontChoice:
    """Seçilen yazı tipi ve nereden geldiği (günlüğe yazılır)."""

    path: str
    size: int


def _glyph_exists(font: ImageFont.FreeTypeFont, character: str) -> bool:
    """Harfin glifi var mı?

    Eksik glif her kod noktası için **aynı** `.notdef` kutusunu çizer;
    bilinmeyen bir kod noktasıyla karşılaştırmak bu yüzden yeterli ve
    ek bir kütüphane istemiyor.
    """

    def ciz(metin: str) -> bytes:
        tuval = Image.new("L", (72, 72), 0)
        ImageDraw.Draw(tuval).text((4, 4), metin, font=font, fill=255)
        return tuval.tobytes()

    return ciz(character) != ciz("\uffff")


def find_font(size: int, *, preferred: str | None = None) -> tuple[ImageFont.FreeTypeFont, str]:
    """Türkçe yazabilen bir yazı tipi bulur; yoksa `FontMissing`.

    `preferred` ayarla verilen yol (STAMP_FONT_PATH): bulunamazsa ya da
    Türkçe harfleri yoksa uyarı yazılır ve adaylara geçilir — yanlış
    ayar yüzünden damgasız kalmak gerekmiyor.
    """
    adaylar = ([preferred] if preferred else []) + list(FONT_CANDIDATES)
    for yol in adaylar:
        if not Path(yol).is_file():
            continue
        try:
            font = ImageFont.truetype(yol, size)
        except OSError:  # pragma: no cover - bozuk dosya
            log.warning("damga.yazi_tipi_acilamadi", yol=yol)
            continue
        eksik = [h for h in TURKISH_PROBE if not _glyph_exists(font, h)]
        if eksik:
            log.warning("damga.yazi_tipi_turkce_degil", yol=yol, eksik="".join(eksik))
            continue
        return font, yol
    raise FontMissing(
        "Türkçe harfleri çizebilen yazı tipi bulunamadı; "
        "STAMP_FONT_PATH ayarlayın ya da sunucuya yazı tipi kurun "
        f"(denenenler: {', '.join(adaylar)})"
    )


def _load(data: bytes) -> Image.Image:
    """Baytları açar ve EXIF yönünü düzeltir."""
    resim = Image.open(io.BytesIO(data))
    resim.load()
    return ImageOps.exif_transpose(resim) or resim


def _save(resim: Image.Image, content_type: str, *, quality: int) -> bytes:
    tampon = io.BytesIO()
    if content_type == "image/png":
        resim.save(tampon, format="PNG", optimize=True)
    else:
        resim.convert("RGB").save(tampon, format="JPEG", quality=quality, optimize=True)
    return tampon.getvalue()


def _fitting_font(
    text: str,
    width: int,
    band: int,
    *,
    preferred: str | None,
) -> tuple[ImageFont.FreeTypeFont, str]:
    """Banda sığan en büyük yazı tipi.

    Şube adı uzun olabilir; sığmayan metni kırpmak yerine küçültüyoruz.
    En küçük boyda da sığmıyorsa `_wrap` ikinci satıra taşır.
    """
    boy = max(TEXT_MIN_PX, int(band * TEXT_RATIO))
    font, yol = find_font(boy, preferred=preferred)
    kullanilabilir = width - 2 * _padding(band)
    while boy > TEXT_MIN_PX and font.getbbox(text)[2] > kullanilabilir:
        boy -= 1
        font = ImageFont.truetype(yol, boy)
    return font, yol


def _kirp(metin: str, font: ImageFont.FreeTypeFont, width: int) -> str:
    """Son çare: sığmayan metni "…" ile kısaltır.

    Buraya ancak tek bir parça (ör. çok uzun bir şube adı) en küçük
    boyda bile sığmazsa gelinir. Kırpma **sondan**: damganın ilk
    bilgisi şube adıdır, en son kaybedilecek şey odur.
    """
    if font.getbbox(metin)[2] <= width:
        return metin
    kesik = metin
    while kesik and font.getbbox(kesik + "…")[2] > width:
        kesik = kesik[:-1]
    return (kesik + "…") if kesik else metin


def _wrap(text: str, font: ImageFont.FreeTypeFont, width: int) -> list[str]:
    """Metni " · " sınırlarında en çok iki satıra böler.

    Neden bölüyoruz: DejaVu, Segoe UI'dan geniş. Aynı metin bir yazı
    tipinde sığarken diğerinde taşıyor; taşan metin sessizce kenardan
    kesilir ve damga yalan söylemeye başlar. CI bunu ilk koşuda yakaladı.
    """
    if font.getbbox(text)[2] <= width:
        return [text]

    satirlar: list[str] = []
    simdiki = ""
    for parca in text.split(" · "):
        aday = f"{simdiki} · {parca}" if simdiki else parca
        if simdiki and font.getbbox(aday)[2] > width:
            satirlar.append(simdiki)
            simdiki = parca
        else:
            simdiki = aday
    satirlar.append(simdiki)

    if len(satirlar) > MAX_LINES:
        # İki satırdan fazlası damgayı fotoğrafa çevirir: kalanı
        # son satırda birleştirip gerekirse kırpıyoruz.
        satirlar = [satirlar[0], " · ".join(satirlar[1:])]
    return [_kirp(satir, font, width) for satir in satirlar]


@dataclass(frozen=True, slots=True)
class StampLayout:
    """Damganın yerleşimi: hangi yazı tipi, hangi satırlar, ne kadar bant."""

    font: ImageFont.FreeTypeFont
    lines: tuple[str, ...]
    band: int
    padding: int


def layout(
    text: str,
    size: tuple[int, int],
    *,
    font_path: str | None = None,
) -> StampLayout:
    """Damga yerleşimini hesaplar (çizmeden; test de bunu ölçüyor)."""
    genislik, yukseklik = size
    taban = band_height(yukseklik)
    bosluk = _padding(taban)
    kullanilabilir = genislik - 2 * bosluk
    font, _ = _fitting_font(text, genislik, taban, preferred=font_path)
    satirlar = _wrap(text, font, kullanilabilir)
    satir_yuksekligi = int(font.size * LINE_SPACING)
    band = max(taban, len(satirlar) * satir_yuksekligi + bosluk)
    return StampLayout(font=font, lines=tuple(satirlar), band=band, padding=bosluk)


def _padding(band: int) -> int:
    return max(6, band // 4)


def band_height(height: int) -> int:
    return max(BAND_MIN_PX, min(BAND_MAX_PX, int(height * BAND_RATIO)))


def stamp(data: bytes, *, text: str, content_type: str, font_path: str | None = None) -> bytes:
    """Görünür damgalı kopya üretir (FR-0606).

    Damga **alt kenarda**, yarı saydam koyu bir bandın üzerinde. Yarı
    saydam, çünkü damga fotoğrafın bir parçasını gizlememeli: kanıtın
    kendisi hâlâ kanıt olmalı.
    """
    resim = _load(data).convert("RGBA")
    genislik, yukseklik = resim.size
    yerlesim = layout(text, resim.size, font_path=font_path)

    katman = Image.new("RGBA", resim.size, (0, 0, 0, 0))
    cizim = ImageDraw.Draw(katman)
    cizim.rectangle(
        [(0, yukseklik - yerlesim.band), (genislik, yukseklik)],
        fill=(0, 0, 0, BAND_ALPHA),
    )
    satir_yuksekligi = yerlesim.band / len(yerlesim.lines)
    for sira, satir in enumerate(yerlesim.lines):
        cizim.text(
            (yerlesim.padding, yukseklik - yerlesim.band + satir_yuksekligi * (sira + 0.5)),
            satir,
            font=yerlesim.font,
            fill=(255, 255, 255, 255),
            anchor="lm",
        )
    return _save(Image.alpha_composite(resim, katman), content_type, quality=STAMP_QUALITY)


def thumbnail(
    data: bytes,
    *,
    content_type: str,
    max_edge: int = THUMBNAIL_MAX_EDGE,
) -> bytes:
    """Izgara için küçük resim (FR-1208). Oran korunur, damga yoktur."""
    resim = _load(data)
    if resim.mode not in ("RGB", "RGBA", "L"):
        resim = resim.convert("RGB")
    resim.thumbnail((max_edge, max_edge), Image.Resampling.LANCZOS)
    return _save(resim, content_type, quality=THUMBNAIL_QUALITY)
