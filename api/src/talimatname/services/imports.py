"""Excel şablonu ve toplu yükleme (ST-008; FR-0105, FR-0106).

Zincir yöneticisi şubelerini Excel'de tutuyor. Onları panele tek tek
girmesini istemek, kurulumu bir saatten bir güne çıkarır — sihirbazın
varlık sebebi bu adım.

Üç kural burada:

* **Şablonun sürümü dosyanın içinde** (FR-0105). Kullanıcı altı ay önce
  indirdiği dosyayı doldurup yüklediğinde, sütunlar değişmişse bunu
  "kod sütunu boş" diye değil, açık mesajla söyleyebilelim.
* **Satır bazlı doğrulama, satırın tüm hataları birden** (FR-0106).
  Kullanıcı dosyayı bir kez düzeltsin.
* **Boş satır satır değildir.** Excel'de aşağıya doğru sürüklenmiş boş
  satırlar olur; bunlar hata değil, yok sayılır — yoksa 10 şubelik bir
  dosya "yüzde 90'ı hatalı" diye reddedilirdi.

Ayrıştırma burada, **doğrulama alanda** (`domain/setup`): openpyxl bir
altyapı ayrıntısı, kural değil.
"""

from __future__ import annotations

import io
from typing import Any

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from talimatname.domain.errors import DomainError, ErrorKind
from talimatname.domain.setup import (
    TEMPLATE_VERSION,
    BranchRow,
    ImportReport,
    RowError,
    branch_row,
    duplicate_codes,
)
from talimatname.domain.window import BusinessHours

#: Sütun anahtarı → başlık. Anahtar sözleşme (kod bunları okur),
#: başlık kullanıcıya görünen metin.
BRANCH_COLUMNS: dict[str, str] = {
    "kod": "Şube kodu*",
    "ad": "Şube adı*",
    "bolge": "Bölge",
    "saat_dilimi": "Saat dilimi",
    "acilis": "Açılış",
    "kapanis": "Kapanış",
    "kapali_gunler": "Kapalı günler (1-7)",
    "adres": "Adres",
    "enlem": "Enlem",
    "boylam": "Boylam",
}

BRANCH_HINTS: dict[str, str] = {
    "kod": "KDK",
    "ad": "Kadıköy",
    "bolge": "Anadolu",
    "saat_dilimi": "Europe/Istanbul",
    "acilis": "09:00",
    "kapanis": "23:30",
    "kapali_gunler": "7",
    "adres": "Kadıköy, İstanbul",
    "enlem": "40,9903",
    "boylam": "29,0275",
}

#: Başlık satırı ve ilk veri satırı (1 tabanlı, Excel'deki gibi).
HEADER_ROW = 2
FIRST_DATA_ROW = 4

MAX_UPLOAD_BYTES = 5 * 1024 * 1024
MAX_ROWS = 2_000


class ImportFailed(DomainError):
    code = "yukleme-reddedildi"
    title = "Dosya kabul edilmedi"
    kind: ErrorKind = "invalid"


class UnreadableFile(DomainError):
    code = "dosya-okunamadi"
    title = "Dosya Excel olarak açılamadı"
    kind: ErrorKind = "invalid"


def branch_template(
    *,
    brand_name: str,
    default_timezone: str,
    default_hours: dict[int, BusinessHours | None] | None = None,
) -> bytes:
    """Doldurulacak Excel şablonunu üretir (FR-0105).

    Örnek satır **gri ve açıklamalı**: kullanıcı silmeyi unutursa diye
    doğrulamada da atlanıyor (`_ornek_mi`).
    """
    kitap = Workbook()
    sayfa = kitap.active
    assert sayfa is not None
    sayfa.title = "Şubeler"

    sayfa.cell(row=1, column=1, value=f"{brand_name} · şube listesi")
    sayfa.cell(row=1, column=1).font = Font(bold=True, size=14)
    sayfa.cell(row=1, column=3, value=f"şablon sürümü: {TEMPLATE_VERSION}")

    baslik_dolgu = PatternFill("solid", fgColor="EFE9DD")
    for sutun, (anahtar, baslik) in enumerate(BRANCH_COLUMNS.items(), start=1):
        hucre = sayfa.cell(row=HEADER_ROW, column=sutun, value=baslik)
        hucre.font = Font(bold=True)
        hucre.fill = baslik_dolgu
        hucre.alignment = Alignment(horizontal="left")
        sayfa.column_dimensions[get_column_letter(sutun)].width = max(14, len(baslik) + 4)

        ornek = sayfa.cell(row=HEADER_ROW + 1, column=sutun, value=BRANCH_HINTS[anahtar])
        ornek.font = Font(color="999999", italic=True)

    # Açıklama **ayrı sayfada**: veri sayfasına yazılan yardım metni
    # yükleme sırasında bir satır gibi okunuyor ve "hatalı satır"
    # sayılıyordu (kendi şablonum dosyayı reddettiriyordu).
    aciklama = kitap.create_sheet("Nasıl doldurulur")
    aciklama.column_dimensions["A"].width = 100
    for sira, metin in enumerate(
        (
            "Yıldızlı sütunlar zorunludur: şube kodu ve şube adı.",
            "Şube kodu hesap içinde benzersizdir; aynı kodla yeniden yüklerseniz şube güncellenir.",
            "Saat ve saat dilimi boş bırakılırsa markanın varsayılanı kullanılır "
            f"({default_timezone}).",
            "Kapalı günler: 1 Pazartesi, 2 Salı … 7 Pazar. Birden çoksa virgülle ayırın (6,7).",
            "Enlem ve boylam isteğe bağlıdır; yazarsanız kanıtın konum bayrağı ölçüye dayanır.",
            "Gri yazılmış örnek satırı silebilirsiniz; silmezseniz de yüklemeye katılmaz.",
            f"Şablon sürümü: {TEMPLATE_VERSION}",
        ),
        start=1,
    ):
        aciklama.cell(row=sira, column=1, value=metin)

    tampon = io.BytesIO()
    kitap.save(tampon)
    return tampon.getvalue()


def _metin(deger: Any) -> str:
    """Hücreyi metne çevirir. Excel sayıyı float yapar, saati time yapar."""
    if deger is None:
        return ""
    if isinstance(deger, str):
        return deger.strip()
    if hasattr(deger, "strftime"):
        return str(deger.strftime("%H:%M"))
    if isinstance(deger, float) and deger.is_integer():
        return str(int(deger))
    return str(deger).strip()


def _ornek_mi(degerler: dict[str, str], sira: int) -> bool:
    """Şablondaki örnek satır silinmemişse yok sayılır.

    Hem **yer** hem **içerik** aranıyor: yalnızca başlığın hemen
    altındaki satır ve yalnızca bütün hücreler örnekle birebir aynıysa.
    Sadece koda bakmak, şubesinin kodu gerçekten KDK olan bir zincirin
    ilk satırını sessizce yutardı — testte ilk elde buna takıldım.
    """
    if sira != HEADER_ROW + 1:
        return False
    return all(degerler.get(anahtar, "") == ornek for anahtar, ornek in BRANCH_HINTS.items())


def parse_branches(
    data: bytes,
    *,
    default_timezone: str,
    default_hours: dict[int, BusinessHours | None],
) -> ImportReport:
    """Yüklenen dosyayı okur ve doğrular; **yazmaz**.

    Dönen rapor servis katmanında uygulanır: ayrı tutmak, "önce göster
    sonra uygula" akışını (kuru çalıştırma) mümkün kılıyor.
    """
    if len(data) > MAX_UPLOAD_BYTES:
        raise ImportFailed(f"Dosya {MAX_UPLOAD_BYTES // 1024 // 1024} MB'tan büyük")
    try:
        kitap = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except Exception as hata:  # openpyxl çeşitli hatalar atar
        raise UnreadableFile(str(hata)[:200]) from hata

    sayfa = kitap.worksheets[0]
    # Salt-okunur sayfada akış **bir kez** okunur: iki ayrı
    # `iter_rows` çağrısı ikinci seferde boş döner (openpyxl tuzağı,
    # testte ilk elde yakalandı). Satırları bir kerede alıyoruz.
    tum_satirlar = list(sayfa.iter_rows(values_only=True))
    if len(tum_satirlar) < HEADER_ROW:
        raise ImportFailed("Dosyada başlık satırı yok")
    basliklar = [_metin(h) for h in tum_satirlar[HEADER_ROW - 1]]
    anahtarlar = _anahtarlar(basliklar)
    if "kod" not in anahtarlar.values() or "ad" not in anahtarlar.values():
        raise ImportFailed(
            "Başlık satırı tanınmadı. Şablonu panelden yeniden indirip "
            f"doldurun (beklenen sürüm: {TEMPLATE_VERSION})."
        )

    satirlar: list[BranchRow] = []
    hatalar: list[RowError] = []
    toplam = 0
    for sira, ham in enumerate(tum_satirlar[HEADER_ROW:], start=HEADER_ROW + 1):
        degerler = {anahtarlar[i]: _metin(h) for i, h in enumerate(ham) if i in anahtarlar}
        if not any(degerler.values()):
            continue  # boş satır satır değildir
        if _ornek_mi(degerler, sira):
            continue
        toplam += 1
        if toplam > MAX_ROWS:
            raise ImportFailed(f"En çok {MAX_ROWS} satır yüklenebilir")
        sonuc = branch_row(
            sira,
            degerler,
            default_timezone=default_timezone,
            default_hours=default_hours,
        )
        if isinstance(sonuc, BranchRow):
            satirlar.append(sonuc)
        else:
            hatalar.extend(sonuc)

    tekrar = duplicate_codes(satirlar)
    if tekrar:
        tekrar_satirlari = {hata.row for hata in tekrar}
        satirlar = [s for s in satirlar if s.row not in tekrar_satirlari]
        hatalar.extend(tekrar)

    return ImportReport(rows=tuple(satirlar), errors=tuple(hatalar), total=toplam)


def _anahtarlar(basliklar: list[str]) -> dict[int, str]:
    """Başlık metninden sütun anahtarına. Sütun sırası değişebilir.

    Kullanıcılar sütun taşır, gizler, araya sütun ekler. Sıraya
    güvenmek yerine başlığa bakmak, "kaymış sütun" hatalarının
    çoğunu baştan siler.
    """
    ters = {
        baslik.lower().rstrip("*").strip(): anahtar for anahtar, baslik in BRANCH_COLUMNS.items()
    }
    eslesme: dict[int, str] = {}
    for sira, baslik in enumerate(basliklar):
        temiz = baslik.lower().rstrip("*").strip()
        anahtar = ters.get(temiz)
        if anahtar is None and temiz.startswith("kapalı günler"):
            anahtar = "kapali_gunler"
        if anahtar is not None:
            eslesme[sira] = anahtar
    return eslesme


def error_report(report: ImportReport) -> bytes:
    """Hatalı satırların indirilebilir raporu (FR-0106, UC-01/E2)."""
    kitap = Workbook()
    sayfa = kitap.active
    assert sayfa is not None
    sayfa.title = "Hatalı satırlar"
    for sutun, baslik in enumerate(("Satır", "Sütun", "Sorun"), start=1):
        hucre = sayfa.cell(row=1, column=sutun, value=baslik)
        hucre.font = Font(bold=True)
        sayfa.column_dimensions[get_column_letter(sutun)].width = 24 if sutun == 3 else 14
    for sira, hata in enumerate(report.errors, start=2):
        sayfa.cell(row=sira, column=1, value=hata.row)
        sayfa.cell(row=sira, column=2, value=BRANCH_COLUMNS.get(hata.field, hata.field))
        sayfa.cell(row=sira, column=3, value=hata.message)
    sayfa.column_dimensions["C"].width = 60
    tampon = io.BytesIO()
    kitap.save(tampon)
    return tampon.getvalue()
