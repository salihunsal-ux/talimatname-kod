"""Kurulum sihirbazı alanı (CAP-14; FR-1401, FR-0105, FR-0106; UC-01).

Sihirbazın amacı tek cümle: **yeni bir zincir bir saat içinde ilk
listesini çalıştırabilsin.** Panelde her şey zaten ayrı ayrı var; burada
olan şey sıra, doğrulama ve "nerede kalmıştım".

İki karar bu dosyada:

* **İlerleme saklanmaz, veriden türetilir.** "Kullanıcı 3. adımda" diye
  bir sayaç tutmuyoruz; şube varsa 2. adım bitmiştir, yayınlanmış
  şablon varsa 3. adım bitmiştir. Sayaç tutsaydık, panelden elle şube
  ekleyen bir yöneticide sayaç ile gerçek ayrışırdı ve sihirbaz
  kullanıcıya yalan söylerdi. Kaldığı yerden devam (TC-004) böylece
  kendiliğinden çalışır.
* **Toplu yüklemede kısmi kabul var ama sınırı var** (FR-0106).
  Satırların beşte birinden fazlası hatalıysa dosya bütün olarak
  reddedilir: o noktada sorun satırlarda değil dosyadadır (yanlış
  şablon, kaymış sütunlar), ve yarısını almak zarar verir.

Saf: dosya okumaz, saat okumaz. Excel ayrıştırma `services/imports`de.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, time
from typing import Literal
from uuid import UUID

from talimatname.domain.organization import BRANCH_CODE, WEEKDAYS, check_timezone
from talimatname.domain.users import normalize_phone
from talimatname.domain.validation import ValidationError, clean_name
from talimatname.domain.window import BusinessHours

SetupStep = Literal["brand", "branches", "template", "plan", "staff", "review"]

#: Sıra bağımlılığın kendisi: plan şablonsuz kurulamaz, şablon şubesiz
#: anlamsızdır. Atlanabilir tek adım personel — liste önce kurulur,
#: davetler sonra gider (UC-01/A2).
STEP_ORDER: tuple[SetupStep, ...] = (
    "brand",
    "branches",
    "template",
    "plan",
    "staff",
    "review",
)

STEP_LABELS: dict[SetupStep, str] = {
    "brand": "Marka",
    "branches": "Şubeler",
    "template": "Şablon",
    "plan": "Plan",
    "staff": "Personel",
    "review": "Özet ve yayın",
}

#: Hatalı satır oranı bunu aşarsa dosya bütün olarak reddedilir (FR-0106).
REJECT_RATIO = 0.20

#: Excel şablonunun sürümü dosyanın içinde yazılı (FR-0105): eski
#: şablonla gelen dosyayı tanıyıp doğru hatayı verebilelim.
TEMPLATE_VERSION = "1"

#: Excel'de haftanın günleri **1–7** (Pazartesi–Pazar); kodun içinde
#: Python'ın 0–6'sı. İnsan tarafında 1 ile başlamak daha az hata üretiyor.
HUMAN_WEEKDAYS = {1: 0, 2: 1, 3: 2, 4: 3, 5: 4, 6: 5, 7: 6}


@dataclass(frozen=True, slots=True)
class AccountSettings:
    """Marka adımının (FR-1401 adım 1) tuttuğu şey.

    `default_hours` şube satırında saat yazılmadığında kullanılır:
    zincirlerin çoğunda şubeler aynı saatlerde açılıyor, her satıra
    aynı saati yazdırmak yükleme hatasını artırmaktan başka işe yaramaz.
    """

    brand_name: str
    timezone: str = "Europe/Istanbul"
    default_hours: dict[int, BusinessHours | None] = field(default_factory=dict)
    logo_url: str | None = None
    completed_at: datetime | None = None

    def validated(self) -> AccountSettings:
        saatler = {gun: self.default_hours.get(gun) for gun in WEEKDAYS}
        for gun, saat in saatler.items():
            if saat is not None and saat.open_time == saat.close_time:
                raise ValidationError(
                    "default_hours", f"{gun}. gün: açılış ve kapanış aynı saat olamaz"
                )
        return replace(
            self,
            brand_name=clean_name(self.brand_name, "brand_name"),
            timezone=check_timezone(self.timezone),
            default_hours=saatler,
        )

    @property
    def open_days(self) -> int:
        return sum(1 for saat in self.default_hours.values() if saat is not None)


@dataclass(frozen=True, slots=True)
class StepState:
    step: SetupStep
    label: str
    done: bool
    detail: str


@dataclass(frozen=True, slots=True)
class SetupProgress:
    """Sihirbazın durumu — tamamı sayılabilir verilerden türetilir."""

    steps: tuple[StepState, ...]
    current: SetupStep
    completed_at: datetime | None = None

    @property
    def publishable(self) -> bool:
        """Yayın için yeten en az şey: şube, şablon ve plan.

        Personel olmadan da yayınlanabilir — liste üretilir, cihaz
        bağlanınca çalışır. Marka adı olmadan da teknik olarak
        yayınlanır ama kullanıcıya hiçbir yerde zincirin adı görünmez;
        o yüzden özet ekranında uyarı olarak duruyor, engel olarak değil.
        """
        gerekli = {"branches", "template", "plan"}
        return all(adim.done for adim in self.steps if adim.step in gerekli)

    @property
    def done_count(self) -> int:
        return sum(1 for adim in self.steps if adim.done)


def progress(
    *,
    settings: AccountSettings | None,
    branch_count: int,
    published_template_count: int,
    active_plan_count: int,
    staff_count: int,
) -> SetupProgress:
    """Adımların durumunu veriden okur (sayaç yok, bkz. modül başlığı)."""
    durumlar = (
        StepState(
            "brand",
            STEP_LABELS["brand"],
            settings is not None,
            settings.brand_name if settings else "Marka adı ve saat dilimi bekleniyor",
        ),
        StepState(
            "branches",
            STEP_LABELS["branches"],
            branch_count > 0,
            f"{branch_count} şube" if branch_count else "Henüz şube yok",
        ),
        StepState(
            "template",
            STEP_LABELS["template"],
            published_template_count > 0,
            f"{published_template_count} yayınlanmış şablon"
            if published_template_count
            else "Kütüphaneden bir şablon seçin",
        ),
        StepState(
            "plan",
            STEP_LABELS["plan"],
            active_plan_count > 0,
            f"{active_plan_count} etkin plan" if active_plan_count else "Henüz plan yok",
        ),
        StepState(
            "staff",
            STEP_LABELS["staff"],
            staff_count > 0,
            f"{staff_count} kullanıcı" if staff_count else "Davet gönderilmedi (atlanabilir)",
        ),
        StepState("review", STEP_LABELS["review"], False, "Özeti gözden geçirip yayınlayın"),
    )
    siradaki: SetupStep = next((d.step for d in durumlar if not d.done), "review")
    return SetupProgress(steps=durumlar, current=siradaki)


# --- toplu yükleme (FR-0105, FR-0106) ---------------------------------


@dataclass(frozen=True, slots=True)
class RowError:
    """Tek satırın tek hatası. Satır numarası **Excel'deki** numaradır."""

    row: int
    field: str
    message: str


@dataclass(frozen=True, slots=True)
class BranchRow:
    """Doğrulanmış şube satırı. Henüz kayıt değil: id servis katmanında."""

    row: int
    code: str
    name: str
    timezone: str
    region: str | None = None
    address: str | None = None
    hours: dict[int, BusinessHours | None] = field(default_factory=dict)
    latitude: float | None = None
    longitude: float | None = None


@dataclass(frozen=True, slots=True)
class ImportReport:
    """Yükleme sonucu: kabul edilenler, hatalar ve dosya reddedildi mi."""

    rows: tuple[BranchRow, ...]
    errors: tuple[RowError, ...]
    total: int
    created: int = 0
    updated: int = 0

    @property
    def rejected(self) -> bool:
        """Hata oranı eşiği aştıysa dosya bütün olarak reddedilir."""
        if self.total == 0:
            return True
        hatali = len({hata.row for hata in self.errors})
        return hatali / self.total > REJECT_RATIO

    @property
    def error_rows(self) -> int:
        return len({hata.row for hata in self.errors})


@dataclass(frozen=True, slots=True)
class StaffReport:
    """Personel yüklemesinin sonucu (FR-0106 ile aynı kabul sınırı)."""

    rows: tuple[StaffRow, ...]
    errors: tuple[RowError, ...]
    total: int
    created: int = 0
    updated: int = 0

    @property
    def rejected(self) -> bool:
        if self.total == 0:
            return True
        return len({hata.row for hata in self.errors}) / self.total > REJECT_RATIO

    @property
    def error_rows(self) -> int:
        return len({hata.row for hata in self.errors})


def parse_time(value: str, field_name: str) -> time:
    """ "09:00", "9:00", "0900" → time. Excel'den metin olarak gelir."""
    temiz = value.strip().replace(".", ":")
    if ":" not in temiz and len(temiz) == 4 and temiz.isdigit():
        temiz = f"{temiz[:2]}:{temiz[2:]}"
    try:
        saat, dakika = (int(parca) for parca in temiz.split(":", 1))
    except ValueError as hata:
        raise ValidationError(field_name, f"Saat okunamadı: {value}") from hata
    if not (0 <= saat <= 23 and 0 <= dakika <= 59):
        raise ValidationError(field_name, f"Geçersiz saat: {value}")
    return time(saat, dakika)


def parse_closed_days(value: str) -> set[int]:
    """ "7" ya da "6,7" → kapalı gün numaraları (Python 0–6)."""
    gunler: set[int] = set()
    for parca in value.replace(";", ",").split(","):
        temiz = parca.strip()
        if not temiz:
            continue
        if not temiz.isdigit() or int(temiz) not in HUMAN_WEEKDAYS:
            raise ValidationError("kapali_gunler", f"1–7 arası gün numarası bekleniyor: {temiz}")
        gunler.add(HUMAN_WEEKDAYS[int(temiz)])
    return gunler


def branch_row(
    row: int,
    values: dict[str, str],
    *,
    default_timezone: str,
    default_hours: dict[int, BusinessHours | None],
) -> BranchRow | list[RowError]:
    """Bir satırı doğrular. Dönen ya kayıt ya **o satırın bütün hataları**.

    İlk hatada durmuyoruz: kullanıcı dosyayı bir kez düzeltsin diye
    satırın tüm sorunlarını birden veriyoruz.
    """
    hatalar: list[RowError] = []

    kod = values.get("kod", "").strip().upper()
    if not kod:
        hatalar.append(RowError(row, "kod", "Şube kodu zorunlu"))
    elif not BRANCH_CODE.match(kod):
        hatalar.append(RowError(row, "kod", "2–16 karakter; büyük harf, rakam ve tire kullanın"))

    ad = values.get("ad", "").strip()
    if not ad:
        hatalar.append(RowError(row, "ad", "Şube adı zorunlu"))

    dilim = values.get("saat_dilimi", "").strip() or default_timezone
    try:
        dilim = check_timezone(dilim)
    except ValidationError as hata:
        hatalar.append(RowError(row, "saat_dilimi", hata.message))

    saatler = dict(default_hours)
    acilis, kapanis = values.get("acilis", "").strip(), values.get("kapanis", "").strip()
    if acilis or kapanis:
        if not (acilis and kapanis):
            hatalar.append(RowError(row, "acilis", "Açılış ve kapanış birlikte yazılır"))
        else:
            try:
                ac, kapa = parse_time(acilis, "acilis"), parse_time(kapanis, "kapanis")
                if ac == kapa:
                    hatalar.append(RowError(row, "acilis", "Açılış ve kapanış aynı saat olamaz"))
                else:
                    saatler = {gun: BusinessHours(ac, kapa) for gun in WEEKDAYS}
            except ValidationError as hata:
                hatalar.append(RowError(row, hata.field_name, hata.message))

    if not any(saatler.values()):
        # Ne satırda saat var ne markada varsayılan: şube hiç açılmaz ve
        # hiç çalıştırma üretilmez. Sessizce kabul etmek, kullanıcıyı
        # "neden hiçbir liste gelmiyor" sorusuyla baş başa bırakırdı.
        hatalar.append(
            RowError(
                row,
                "acilis",
                "Açılış ve kapanış yazın (markanın varsayılan çalışma saati tanımlı değil)",
            )
        )

    kapali = values.get("kapali_gunler", "").strip()
    if kapali:
        try:
            for gun in parse_closed_days(kapali):
                saatler[gun] = None
        except ValidationError as hata:
            hatalar.append(RowError(row, "kapali_gunler", hata.message))

    konum: list[float | None] = []
    for alan, aralik in (("enlem", 90.0), ("boylam", 180.0)):
        ham = values.get(alan, "").strip().replace(",", ".")
        if not ham:
            konum.append(None)
            continue
        try:
            sayi = float(ham)
        except ValueError:
            hatalar.append(RowError(row, alan, f"Sayı bekleniyor: {ham}"))
            konum.append(None)
            continue
        if abs(sayi) > aralik:
            hatalar.append(RowError(row, alan, f"{-aralik}–{aralik} arası olmalı"))
            konum.append(None)
        else:
            konum.append(sayi)

    if hatalar:
        return hatalar
    return BranchRow(
        row=row,
        code=kod,
        name=ad,
        timezone=dilim,
        region=values.get("bolge", "").strip() or None,
        address=values.get("adres", "").strip() or None,
        hours=saatler,
        latitude=konum[0],
        longitude=konum[1],
    )


def duplicate_codes(rows: list[BranchRow]) -> list[RowError]:
    """Dosyanın kendi içindeki tekrar eden kodlar (FR-0106).

    Veritabanındaki tekrar ayrı mesele: aynı kod gelirse **güncelleme**
    sayılır. Dosyanın içinde iki kez geçmesi ise kullanıcının hatasıdır,
    hangisinin kazanacağı belirsizdir.
    """
    gorulen: dict[str, int] = {}
    hatalar: list[RowError] = []
    for satir in rows:
        onceki = gorulen.get(satir.code)
        if onceki is not None:
            hatalar.append(
                RowError(satir.row, "kod", f"Bu kod {onceki}. satırda da var: {satir.code}")
            )
        else:
            gorulen[satir.code] = satir.row
    return hatalar


#: Sihirbazdan toplu eklenebilen roller. Yönetici listede yok:
#: kapsamı hesabın tamamı, bir sütunla anlatılacak bir şey değil ve
#: zincirde bir-iki kişidir — panelden eklenir.
#:
#: Bölge müdürü **artık listede**: kapsamı şube kodu değil bölge adı,
#: o da şube dosyasında zaten yazılıyor. Dışarıda bırakmak, 8 bölgeli
#: bir zincirde kurulumu yarıda kesip panele gönderiyordu.
BULK_ROLES: dict[str, str] = {
    "staff": "Personel",
    "branch_manager": "Şube müdürü",
    "region_manager": "Bölge müdürü",
}

#: Kapsamı şube olan roller. Bölge müdürünün kapsamı bölge.
BRANCH_SCOPED_ROLES = frozenset({"staff", "branch_manager"})


@dataclass(frozen=True, slots=True)
class StaffRow:
    """Doğrulanmış personel satırı. Telefon E.164'e çevrilmiş hâliyle.

    Kapsam **iki alandan biri**: şube kodu ya da bölge adı. Hangisi
    olduğunu rol belirliyor; ikisi birden dolu olamaz.
    """

    row: int
    full_name: str
    phone: str
    role: str
    branch_code: str = ""
    region_name: str = ""
    email: str | None = None


def staff_row(
    row: int,
    values: dict[str, str],
    *,
    branch_codes: set[str],
    region_names: set[str] | None = None,
) -> StaffRow | list[RowError]:
    """Personel satırını doğrular (FR-0105, FR-0106, BR-17).

    Şube kodu ve bölge adı **hesapta var olmalı**: yazım hatası
    yüzünden yanlış şubeye personel bağlamak, yanlış kişiye liste
    göndermek demek. Bölge müdüründe yanlış bölge, bütün bir bölgenin
    raporunu yanlış kişiye açmak demek.
    """
    hatalar: list[RowError] = []

    ad = values.get("ad", "").strip()
    if not ad:
        hatalar.append(RowError(row, "ad", "Ad soyad zorunlu"))

    ham_telefon = values.get("telefon", "").strip()
    telefon = ""
    if not ham_telefon:
        hatalar.append(RowError(row, "telefon", "Telefon zorunlu"))
    else:
        try:
            telefon = normalize_phone(ham_telefon)
        except ValidationError as hata:
            hatalar.append(RowError(row, "telefon", hata.message))

    ham_rol = values.get("rol", "").strip()
    rol = _rol_kodu(ham_rol)
    if rol is None:
        secenekler = " / ".join(BULK_ROLES.values())
        hatalar.append(RowError(row, "rol", f"Rol {secenekler} olmalı"))

    kod = values.get("sube_kodu", "").strip().upper()
    bolge = values.get("bolge", "").strip()
    bolgeler = region_names or set()
    hatalar += _kapsam_hatalari(row, rol, kod, bolge, branch_codes, bolgeler)

    eposta = values.get("eposta", "").strip() or None
    if eposta and "@" not in eposta:
        hatalar.append(RowError(row, "eposta", "Geçerli bir e-posta yazın"))

    if hatalar:
        return hatalar
    assert rol is not None
    return StaffRow(
        row=row,
        full_name=ad,
        phone=telefon,
        role=rol,
        branch_code=kod if rol in BRANCH_SCOPED_ROLES else "",
        region_name="" if rol in BRANCH_SCOPED_ROLES else bolge,
        email=eposta,
    )


def _kapsam_hatalari(
    row: int,
    rol: str | None,
    kod: str,
    bolge: str,
    branch_codes: set[str],
    region_names: set[str],
) -> list[RowError]:
    """Kapsam sütunlarının doğruluğu: hangisi dolu, hangisi boş.

    İkisi birden dolu olduğunda satır **reddedilir**, biri seçilmez:
    hangisinin kazandığını tahmin ettirmek, yanlış kapsamı sessizce
    yazmak demek olurdu.
    """
    if rol is None:  # rol hatası zaten yazıldı; kapsam kuralı rolden türüyor
        return []

    if rol in BRANCH_SCOPED_ROLES:
        if bolge:
            return [RowError(row, "bolge", "Bölge yalnızca bölge müdürü satırında doldurulur")]
        if not kod:
            return [RowError(row, "sube_kodu", "Şube kodu zorunlu")]
        if kod not in branch_codes:
            return [RowError(row, "sube_kodu", f"Bu kodla şube yok: {kod}")]
        return []

    if kod:
        return [RowError(row, "sube_kodu", "Bölge müdürü satırında şube kodu boş bırakılır")]
    if not bolge:
        return [RowError(row, "bolge", "Bölge müdürü için bölge adı zorunlu")]
    if bolge not in region_names:
        return [RowError(row, "bolge", f"Bu adla bölge yok: {bolge}")]
    return []


def _rol_kodu(deger: str) -> str | None:
    """Türkçe etiket ya da kod kabul edilir: "Personel" de "staff" de."""
    temiz = deger.strip().casefold()
    if not temiz:
        return None
    for kod, etiket in BULK_ROLES.items():
        if temiz in (kod.casefold(), etiket.casefold()):
            return kod
    return None


def duplicate_phones(rows: list[StaffRow]) -> list[RowError]:
    """Dosyanın kendi içinde tekrar eden telefon (FR-0106).

    Telefon kişinin kimliği (OTP ile giriyor); aynı numara iki satırda
    olursa hangisinin kazanacağı belirsizdir.
    """
    gorulen: dict[str, int] = {}
    hatalar: list[RowError] = []
    for satir in rows:
        onceki = gorulen.get(satir.phone)
        if onceki is not None:
            hatalar.append(RowError(satir.row, "telefon", f"Bu numara {onceki}. satırda da var"))
        else:
            gorulen[satir.phone] = satir.row
    return hatalar


@dataclass(frozen=True, slots=True)
class PlanProposal:
    """Şube saatlerinden türetilen plan önerisi (UC-01 adım 4).

    Kapanış listesi kapanıştan **önce** başlamalı ve kapanışta bitmeli:
    pencere kapanış saatinden `before_close` kadar önce açılır.
    """

    name: str
    template_version_id: UUID
    branch_ids: tuple[UUID, ...]
    start_time: time
    duration_minutes: int
    recurrence: Literal["daily"] = "daily"
