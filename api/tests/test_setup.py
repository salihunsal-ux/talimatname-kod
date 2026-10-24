"""Kurulum sihirbazı testleri (ST-008; TC-004, FR-1401, FR-0105, FR-0106).

Sihirbazın iddiası: **yeni bir zincir bir saat içinde ilk listesini
çalıştırabilir.** Buradaki testler o iddianın iki zor yerini tutuyor:
toplu yüklemenin doğruluğu ve "kaldığım yerden devam".
"""

from __future__ import annotations

import io
from datetime import UTC, datetime, time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook, load_workbook

from conftest import oturum_ac
from talimatname.api.app import create_app
from talimatname.domain.setup import (
    REJECT_RATIO,
    AccountSettings,
    branch_row,
    duplicate_codes,
    parse_closed_days,
    parse_time,
    progress,
)
from talimatname.domain.validation import ValidationError
from talimatname.domain.window import BusinessHours
from talimatname.infra.memory import (
    MemoryOrganizationRepository,
    MemoryPlanRepository,
    MemorySettingsRepository,
    MemoryTemplateRepository,
    MemoryUserRepository,
)
from talimatname.services.imports import (
    BRANCH_COLUMNS,
    HEADER_ROW,
    ImportFailed,
    UnreadableFile,
    branch_template,
    parse_branches,
)
from talimatname.services.setup import SetupService
from talimatname.settings import Settings

STANDART = {gun: BusinessHours(time(9, 0), time(23, 30)) for gun in range(7)}


def _dosya(satirlar: list[dict[str, str]], *, basliklar: list[str] | None = None) -> bytes:
    """Şablonla aynı biçimde bir Excel üretir (kullanıcının doldurduğu)."""
    kitap = Workbook()
    sayfa = kitap.active
    assert sayfa is not None
    anahtarlar = list(BRANCH_COLUMNS)
    basliklar = basliklar or [BRANCH_COLUMNS[a] for a in anahtarlar]
    for sutun, baslik in enumerate(basliklar, start=1):
        sayfa.cell(row=HEADER_ROW, column=sutun, value=baslik)
    for sira, satir in enumerate(satirlar, start=HEADER_ROW + 1):
        for sutun, anahtar in enumerate(anahtarlar, start=1):
            sayfa.cell(row=sira, column=sutun, value=satir.get(anahtar, ""))
    tampon = io.BytesIO()
    kitap.save(tampon)
    return tampon.getvalue()


def _sube(kod: str, ad: str, **ek: str) -> dict[str, str]:
    return {"kod": kod, "ad": ad, **ek}


@pytest.fixture
def servis() -> SetupService:
    # Yeni hesap: her şey **boş** başlar — sihirbazın gerçek durumu.
    return SetupService(
        MemorySettingsRepository(),
        MemoryOrganizationRepository(seed=False),
        MemoryTemplateRepository(seed=False),
        MemoryPlanRepository(seed=False),
        MemoryUserRepository(seed=False),
        now=lambda: datetime(2026, 11, 2, 9, 0, tzinfo=UTC),
    )


# --- alan: satır doğrulama (FR-0106) ----------------------------------


def test_saat_bicimleri_okunur() -> None:
    assert parse_time("09:00", "acilis") == time(9, 0)
    assert parse_time("9:5", "acilis") == time(9, 5)
    assert parse_time("0930", "acilis") == time(9, 30)
    assert parse_time("23.30", "kapanis") == time(23, 30)
    with pytest.raises(ValidationError):
        parse_time("yarım", "acilis")
    with pytest.raises(ValidationError):
        parse_time("25:00", "acilis")


def test_kapali_gunler_insan_numarasiyla() -> None:
    """Excel'de 1 Pazartesi … 7 Pazar; kodun içinde 0–6."""
    assert parse_closed_days("7") == {6}
    assert parse_closed_days("6, 7") == {5, 6}
    with pytest.raises(ValidationError):
        parse_closed_days("0")
    with pytest.raises(ValidationError):
        parse_closed_days("pazar")


def test_satirin_tum_hatalari_birden_doner() -> None:
    """Kullanıcı dosyayı bir kez düzeltsin diye ilk hatada durmuyoruz."""
    sonuc = branch_row(
        5,
        {"kod": "k d k", "ad": "", "saat_dilimi": "Mars/Olympus", "enlem": "abc"},
        default_timezone="Europe/Istanbul",
        default_hours=STANDART,
    )

    assert isinstance(sonuc, list)
    assert {hata.field for hata in sonuc} == {"kod", "ad", "saat_dilimi", "enlem"}
    assert all(hata.row == 5 for hata in sonuc)


def test_bos_saat_markanin_varsayilanini_alir() -> None:
    sonuc = branch_row(
        3,
        {"kod": "KDK", "ad": "Kadıköy"},
        default_timezone="Europe/Istanbul",
        default_hours=STANDART,
    )

    assert not isinstance(sonuc, list)
    assert sonuc.hours[0] == BusinessHours(time(9, 0), time(23, 30))
    assert sonuc.timezone == "Europe/Istanbul"


def test_dosya_icindeki_tekrar_eden_kod_hata() -> None:
    satirlar = [
        branch_row(
            sira,
            {"kod": "KDK", "ad": f"Kadıköy {sira}"},
            default_timezone="Europe/Istanbul",
            default_hours=STANDART,
        )
        for sira in (3, 4)
    ]
    hatalar = duplicate_codes([s for s in satirlar if not isinstance(s, list)])

    assert len(hatalar) == 1
    assert hatalar[0].row == 4
    assert "3. satırda" in hatalar[0].message


# --- Excel okuma (FR-0105) --------------------------------------------


def test_sablon_basliklari_ve_surumu_tasir() -> None:
    kitap = load_workbook(
        io.BytesIO(branch_template(brand_name="Kahve Durağı", default_timezone="Europe/Istanbul"))
    )
    sayfa = kitap.active
    assert sayfa is not None

    basliklar = [sayfa.cell(row=HEADER_ROW, column=s).value for s in range(1, 11)]
    assert basliklar[0] == BRANCH_COLUMNS["kod"]
    assert "şablon sürümü" in str(sayfa.cell(row=1, column=3).value)
    assert "Kahve Durağı" in str(sayfa.cell(row=1, column=1).value)


def test_ornek_satir_silinmemisse_yok_sayilir() -> None:
    """Şablondaki gri örnek satır kullanıcının verisi değildir."""
    veri = branch_template(brand_name="Kahve Durağı", default_timezone="Europe/Istanbul")

    rapor = parse_branches(veri, default_timezone="Europe/Istanbul", default_hours=STANDART)

    assert rapor.total == 0


def test_sutun_sirasi_degisse_de_okunur() -> None:
    """Kullanıcılar sütun taşır; sıraya değil başlığa bakıyoruz."""
    ters = [BRANCH_COLUMNS[a] for a in reversed(list(BRANCH_COLUMNS))]
    kitap = Workbook()
    sayfa = kitap.active
    assert sayfa is not None
    for sutun, baslik in enumerate(ters, start=1):
        sayfa.cell(row=HEADER_ROW, column=sutun, value=baslik)
    for sutun, anahtar in enumerate(reversed(list(BRANCH_COLUMNS)), start=1):
        sayfa.cell(
            row=HEADER_ROW + 1, column=sutun, value={"kod": "KDK", "ad": "Kadıköy"}.get(anahtar, "")
        )
    tampon = io.BytesIO()
    kitap.save(tampon)

    rapor = parse_branches(
        tampon.getvalue(), default_timezone="Europe/Istanbul", default_hours=STANDART
    )

    assert [s.code for s in rapor.rows] == ["KDK"]


def test_bos_satirlar_sayilmaz() -> None:
    """Excel'de aşağı sürüklenmiş boş satırlar dosyayı reddettirmemeli."""
    veri = _dosya([_sube("KDK", "Kadıköy"), {}, {}, _sube("USK", "Üsküdar"), {}])

    rapor = parse_branches(veri, default_timezone="Europe/Istanbul", default_hours=STANDART)

    assert rapor.total == 2
    assert not rapor.rejected


def test_baslik_taninmazsa_acik_hata() -> None:
    veri = _dosya([_sube("KDK", "Kadıköy")], basliklar=["bir", "iki", "üç"])

    with pytest.raises(ImportFailed, match="Başlık satırı"):
        parse_branches(veri, default_timezone="Europe/Istanbul", default_hours=STANDART)


def test_excel_olmayan_dosya_reddedilir() -> None:
    with pytest.raises(UnreadableFile):
        parse_branches(b"bu bir excel degil", default_timezone="Europe/Istanbul", default_hours={})


# --- servis: yükleme ve ilerleme --------------------------------------


def test_yukleme_sube_acar_ve_bolgeyi_olusturur(servis: SetupService) -> None:
    veri = _dosya(
        [
            _sube("KDK", "Kadıköy", bolge="Anadolu", acilis="08:00", kapanis="22:00"),
            _sube("USK", "Üsküdar", bolge="Anadolu", kapali_gunler="7"),
            _sube("BSK", "Beşiktaş", bolge="Avrupa"),
        ]
    )

    rapor = servis.import_branches(veri)

    assert (rapor.created, rapor.updated, rapor.error_rows) == (3, 0, 0)
    org = servis._org
    assert {b.code for b in org.branches()} == {"KDK", "USK", "BSK"}
    assert {b.name for b in org.regions()} == {"Anadolu", "Avrupa"}
    kadikoy = org.branch_by_code("KDK")
    assert kadikoy is not None
    assert kadikoy.business_hours[0] == BusinessHours(time(8, 0), time(22, 0))
    uskudar = org.branch_by_code("USK")
    assert uskudar is not None
    assert uskudar.business_hours[6] is None  # pazar kapalı


def test_ayni_dosya_ikinci_kez_guncelleme_sayilir(servis: SetupService) -> None:
    """Şube kodu zincirin anahtarı: ikinci yükleme kopya açmaz (FR-0103)."""
    veri = _dosya([_sube("KDK", "Kadıköy")])
    servis.import_branches(veri)

    ikinci = servis.import_branches(_dosya([_sube("KDK", "Kadıköy Çarşı")]))

    assert (ikinci.created, ikinci.updated) == (0, 1)
    assert len(servis._org.branches()) == 1
    kadikoy = servis._org.branch_by_code("KDK")
    assert kadikoy is not None
    assert kadikoy.name == "Kadıköy Çarşı"


def test_esikteki_dosya_kabul_edilir(servis: SetupService) -> None:
    """Tam eşikte (beşte bir) kabul; eşiği **aşınca** ret (FR-0106)."""
    esikte = [_sube(f"S{i:02d}", f"Şube {i}") for i in range(4)] + [_sube("", "Kodsuz")]

    rapor = servis.import_branches(_dosya(esikte))

    assert rapor.total == 5
    assert rapor.error_rows / rapor.total == REJECT_RATIO
    assert rapor.rejected is False
    assert rapor.created == 4


def test_esigi_asan_dosya_reddedilir(servis: SetupService) -> None:
    asan = [_sube(f"S{i:02d}", f"Şube {i}") for i in range(3)] + [_sube("", "Kodsuz")]

    with pytest.raises(ImportFailed):
        servis.import_branches(_dosya(asan))

    assert servis._org.branches() == []


def test_esigin_altinda_kalan_hata_kabul_edilir(servis: SetupService) -> None:
    satirlar = [_sube(f"S{i:02d}", f"Şube {i}") for i in range(9)] + [_sube("", "Kodsuz")]

    rapor = servis.import_branches(_dosya(satirlar))

    assert rapor.total == 10
    assert rapor.error_rows == 1
    assert rapor.rejected is False
    assert rapor.created == 9


def test_cok_hatali_dosya_butun_olarak_reddedilir(servis: SetupService) -> None:
    """FR-0106: sorun satırlarda değil dosyadadır; yarısını almak zarar verir."""
    satirlar = [_sube("KDK", "Kadıköy")] + [_sube("", f"Kodsuz {i}") for i in range(3)]

    with pytest.raises(ImportFailed, match="kabul edilmedi") as hata:
        servis.import_branches(_dosya(satirlar))

    assert len(hata.value.extra["errors"]) >= 3
    assert servis._org.branches() == []  # hiçbir şey yazılmadı


def test_kuru_calistirma_yazmaz(servis: SetupService) -> None:
    rapor = servis.import_branches(_dosya([_sube("KDK", "Kadıköy")]), apply=False)

    assert len(rapor.rows) == 1
    assert rapor.created == 0
    assert servis._org.branches() == []


# --- ilerleme (TC-004) ------------------------------------------------


def test_ilerleme_veriden_turetilir() -> None:
    bos = progress(
        settings=None,
        branch_count=0,
        published_template_count=0,
        active_plan_count=0,
        staff_count=0,
    )
    assert bos.current == "brand"
    assert bos.publishable is False

    dolu = progress(
        settings=AccountSettings(brand_name="Kahve Durağı").validated(),
        branch_count=8,
        published_template_count=1,
        active_plan_count=1,
        staff_count=0,
    )
    assert dolu.current == "staff"  # personel atlanabilir ama sıradaki o
    assert dolu.publishable is True
    assert dolu.done_count == 4


def test_sihirbaz_kaldigi_yerden_devam_eder(servis: SetupService) -> None:
    """TC-004: 2. adımda bırak, geri gel — 2. adım açılır, 1. adım duruyor."""
    servis.save_brand(brand_name="Kahve Durağı", timezone="Europe/Istanbul")

    assert servis.progress().current == "branches"

    servis.import_branches(_dosya([_sube("KDK", "Kadıköy")]))
    durum = servis.progress()

    assert durum.current == "template"
    assert [a.done for a in durum.steps][:2] == [True, True]
    ayar = servis.settings()
    assert ayar is not None
    assert ayar.brand_name == "Kahve Durağı"


def test_marka_saatleri_sube_satirina_varsayilan_olur(servis: SetupService) -> None:
    servis.save_brand(
        brand_name="Kahve Durağı",
        timezone="Europe/Istanbul",
        open_time=time(7, 30),
        close_time=time(19, 0),
        closed_days=(6,),
    )

    servis.import_branches(_dosya([_sube("KDK", "Kadıköy")]))

    sube = servis._org.branch_by_code("KDK")
    assert sube is not None
    assert sube.business_hours[0] == BusinessHours(time(7, 30), time(19, 0))
    assert sube.business_hours[6] is None


def test_tamamlama_ve_yeniden_acma(servis: SetupService) -> None:
    servis.save_brand(brand_name="Kahve Durağı", timezone="Europe/Istanbul")

    kapali = servis.complete()
    assert kapali.completed_at == datetime(2026, 11, 2, 9, 0, tzinfo=UTC)
    assert servis.progress().completed_at is not None

    servis.reopen()
    assert servis.progress().completed_at is None


# --- uç noktalar ------------------------------------------------------


def _istemci(tmp: Path, rol: str = "admin") -> TestClient:
    return oturum_ac(TestClient(create_app(Settings(evidence_dir=str(tmp)))), rol)


def test_uc_nokta_durum_tohumla_dolu_gelir(tmp_path: Path) -> None:
    """Tohumda şube, şablon ve plan var: sihirbaz bunu görmeli."""
    yanit = _istemci(tmp_path).get("/api/v1/setup")

    assert yanit.status_code == 200
    govde = yanit.json()
    adimlar = {a["step"]: a["done"] for a in govde["steps"]}
    assert adimlar["branches"] is True
    assert adimlar["template"] is True
    assert govde["publishable"] is True
    assert govde["current"] == "brand"  # marka ayarı henüz yok


def test_uc_nokta_marka_kaydedilir(tmp_path: Path) -> None:
    istemci = _istemci(tmp_path)

    yanit = istemci.put(
        "/api/v1/setup/brand",
        json={
            "brand_name": "Kahve Durağı",
            "timezone": "Europe/Istanbul",
            "open_time": "08:00",
            "close_time": "22:30",
            "closed_days": [6],
        },
    )

    assert yanit.status_code == 200
    marka = yanit.json()["brand"]
    assert marka["brand_name"] == "Kahve Durağı"
    assert marka["hours"][0]["open_time"] == "08:00:00"
    assert marka["hours"][6]["open_time"] is None
    assert istemci.get("/api/v1/setup").json()["brand"]["brand_name"] == "Kahve Durağı"


def test_uc_nokta_sablon_indirilir(tmp_path: Path) -> None:
    yanit = _istemci(tmp_path).get("/api/v1/setup/branches/template")

    assert yanit.status_code == 200
    assert "spreadsheetml" in yanit.headers["content-type"]
    assert "subeler.xlsx" in yanit.headers["content-disposition"]
    kitap = load_workbook(io.BytesIO(yanit.content))
    assert kitap.active is not None


def test_uc_nokta_onizleme_yazmaz_import_yazar(tmp_path: Path) -> None:
    istemci = _istemci(tmp_path)
    veri = _dosya([_sube("YNI", "Yeni Şube", bolge="Ege")])
    once = len(istemci.get("/api/v1/branches").json())

    onizleme = istemci.post(
        "/api/v1/setup/branches/preview",
        files={"file": ("subeler.xlsx", veri, "application/vnd.ms-excel")},
    ).json()
    assert onizleme["accepted"] == 1
    assert onizleme["created"] == 0

    yukleme = istemci.post(
        "/api/v1/setup/branches/import",
        files={"file": ("subeler.xlsx", veri, "application/vnd.ms-excel")},
    ).json()
    assert yukleme["created"] == 1
    assert len(istemci.get("/api/v1/branches").json()) >= once


def test_uc_nokta_hatali_dosya_422_ve_satir_listesi(tmp_path: Path) -> None:
    istemci = _istemci(tmp_path)
    veri = _dosya([_sube("", "Kodsuz"), _sube("", "Kodsuz 2")])

    yanit = istemci.post(
        "/api/v1/setup/branches/import",
        files={"file": ("subeler.xlsx", veri, "application/vnd.ms-excel")},
    )

    assert yanit.status_code == 422
    govde = yanit.json()
    assert govde["type"] == "urn:talimatname:yukleme-reddedildi"
    assert govde["errors"][0]["field"] == "kod"


def test_uc_nokta_hata_raporu_excel_doner(tmp_path: Path) -> None:
    istemci = _istemci(tmp_path)
    veri = _dosya([_sube("", "Kodsuz"), _sube("", "Kodsuz 2")])

    yanit = istemci.post(
        "/api/v1/setup/branches/error-report",
        files={"file": ("subeler.xlsx", veri, "application/vnd.ms-excel")},
    )

    assert yanit.status_code == 200
    sayfa = load_workbook(io.BytesIO(yanit.content)).active
    assert sayfa is not None
    assert sayfa.cell(row=1, column=1).value == "Satır"
    assert sayfa.cell(row=2, column=3).value  # en az bir hata satırı


def test_uc_nokta_personel_kurulumu_goremez(tmp_path: Path) -> None:
    """Kurulum hesabın kendisini şekillendiriyor: yönetici işi."""
    assert _istemci(tmp_path, "staff").get("/api/v1/setup").status_code == 403
