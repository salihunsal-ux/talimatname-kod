"""Şablon kütüphanesi (ST-021; FR-1401 adım 3, Ş-6).

Kaynak: ürün belgesi `02-urun/07-sablon-kutuphanesi.md`. Orada 9 şablon
tanımlı; burada ilk ikisi var (Kapanış, Açılış) — kalanı içerik işi ve
sahada doğrulandıkça eklenecek.

**Kütüphane kodda, veritabanında değil.** Bunlar ürün içeriği, müşteri
verisi değil: her hesapta aynı, sürümü ürünle birlikte ilerliyor.
Kopyalanınca hesabın kendi şablonu oluyor ve bağ kopuyor — zincir
istediği gibi düzenlesin, bizim güncellememiz kimsenin listesini
değiştirmesin. (Kaynak takibi ve güncelleme bandı v1.1, ADR-0010.)

Plan önerileri de burada: belge her şablon için pencereyi şube çalışma
saatine göre tanımlıyor ("kapanıştan 60 dk önce"), bu yüzden öneri
şablonun bir parçası.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from talimatname.domain.templates import (
    ChoiceOption,
    Item,
    ItemType,
    Section,
    Template,
    TemplateVersion,
)
from talimatname.domain.window import Anchor

#: "Evet" her zaman uygun durum (ürün belgesi, tasarım kuralı 2):
#: "Hayır" → fotoğraf + not zorunlu; "Uygun değil" = bu şubede yok.
EVET_HAYIR = (("Evet", True), ("Hayır", False), ("Uygun değil", True))


@dataclass(frozen=True, slots=True)
class PlanDefaults:
    """Şablonun önerdiği pencere (02-urun/07, her şablonun "Tekrar" satırı).

    `anchor` şube saatine bağlar: tek plan, her şubede kendi kapanışına
    göre açılır. Sabit saat yazsaydık 09:00 açılan şube ile 11:00 açılan
    şube aynı planı paylaşamazdı.
    """

    anchor: Anchor
    duration_minutes: int
    tolerance_minutes: int
    #: RRULE (ADR-0005): "günlük" demiyoruz, takvim standardını yazıyoruz.
    recurrence: str = "FREQ=DAILY"


@dataclass(frozen=True, slots=True)
class LibraryTemplate:
    """Kütüphanedeki bir şablon: kimliği sabit, kopyası yeni kimlik alır."""

    key: str
    name: str
    category: str
    summary: str
    plan: PlanDefaults
    sections: tuple[Section, ...]

    @property
    def item_count(self) -> int:
        return sum(1 for bolum in self.sections for madde in bolum.items if madde.scored)

    @property
    def critical_count(self) -> int:
        return sum(1 for bolum in self.sections for madde in bolum.items if madde.critical)

    @property
    def photo_count(self) -> int:
        return sum(
            1
            for bolum in self.sections
            for madde in bolum.items
            if madde.photo_required or madde.type == "photo"
        )

    def copy_for_account(self) -> tuple[Template, TemplateVersion]:
        """Hesaba **yeni kimliklerle** kopyalar ve yayınlanmış sürüm açar.

        Yayınlanmış: sihirbazın amacı bir saat içinde çalışır liste.
        Taslak bırakmak, kullanıcıyı editörde ikinci bir tura sokardı.
        """
        sablon = Template(id=uuid4(), name=self.name, category=self.category).validated()
        surum = TemplateVersion(
            id=uuid4(),
            template_id=sablon.id,
            version_no=1,
            status="draft",
            sections=tuple(_yeni_kimlikler(bolum) for bolum in self.sections),
        ).validated()
        return sablon, surum


def _yeni_kimlikler(bolum: Section) -> Section:
    return Section(
        id=uuid4(),
        order=bolum.order,
        title=bolum.title,
        items=tuple(
            Item(
                id=uuid4(),
                order=madde.order,
                type=madde.type,
                title=madde.title,
                hint=madde.hint,
                required=madde.required,
                photo_required=madde.photo_required,
                critical=madde.critical,
                options=madde.options,
                min_value=madde.min_value,
                max_value=madde.max_value,
                unit=madde.unit,
            )
            for madde in bolum.items
        ),
    )


def _madde(
    sira: int,
    tur: ItemType,
    baslik: str,
    *,
    kritik: bool = False,
    foto: bool = False,
    secenekler: tuple[tuple[str, bool], ...] = (),
    alt: float | None = None,
    ust: float | None = None,
    birim: str | None = None,
    zorunlu: bool = True,
) -> Item:
    return Item(
        id=uuid4(),
        order=sira,
        type=tur,
        title=baslik,
        required=zorunlu,
        critical=kritik,
        photo_required=foto,
        options=tuple(ChoiceOption(etiket, gecer) for etiket, gecer in secenekler),
        min_value=alt,
        max_value=ust,
        unit=birim,
    )


KAPANIS = LibraryTemplate(
    key="kapanis-kafe",
    name="Kapanış (kafe / hızlı servis)",
    category="Kapanış",
    summary="Gün sonunda hijyen, gıda güvenliği ve güvenli kapanış. Hedef süre 6–8 dk.",
    # 02-urun/07: kapanıştan 60 dk önce başlar, kapanış + 90 dk sürer,
    # tolerans 120 dk.
    plan=PlanDefaults(anchor=Anchor("close", -60), duration_minutes=150, tolerance_minutes=120),
    sections=(
        Section(
            id=uuid4(),
            order=1,
            title="Bar ve mutfak",
            items=(
                _madde(
                    1,
                    "confirm",
                    "Espresso makinesi geri yıkama yapıldı; süt hortumları ve buhar "
                    "çubuğu temizlendi",
                ),
                _madde(2, "photo", "Kahve makinesi ve öğütücü temizlendi", foto=True),
                _madde(
                    3, "temperature", "Süt dolabı sıcaklığı", kritik=True, alt=0, ust=4, birim="°C"
                ),
                _madde(
                    4,
                    "temperature",
                    "Mutfak buzdolabı sıcaklığı",
                    kritik=True,
                    alt=0,
                    ust=4,
                    birim="°C",
                ),
                _madde(
                    5,
                    "temperature",
                    "Dondurucu sıcaklığı",
                    kritik=True,
                    alt=-30,
                    ust=-18,
                    birim="°C",
                ),
                _madde(
                    6,
                    "choice",
                    "Açık ürünler etiketlendi (ürün adı, açılış tarihi) ve dolaba kaldırıldı",
                    secenekler=EVET_HAYIR,
                ),
                _madde(
                    7,
                    "choice",
                    "Fritöz kapatıldı, yağ süzüldü, kapağı kapatıldı",
                    secenekler=EVET_HAYIR,
                ),
                _madde(
                    8,
                    "confirm",
                    "Tezgâh, kesme yüzeyleri ve lavabo dezenfekte edildi; bulaşık bitti, "
                    "makine kapağı açık",
                ),
            ),
        ),
        Section(
            id=uuid4(),
            order=2,
            title="Salon ve tuvalet",
            items=(
                _madde(1, "confirm", "Masalar, sandalyeler ve servis istasyonu silindi"),
                _madde(2, "photo", "Zemin süpürüldü ve paspaslandı", foto=True),
                _madde(
                    3,
                    "confirm",
                    "Tuvaletler temizlendi; sabun, kâğıt havlu, tuvalet kâğıdı dolduruldu",
                ),
                _madde(
                    4, "photo", "Çöpler dışarı çıkarıldı, kovalara yeni poşet takıldı", foto=True
                ),
            ),
        ),
        Section(
            id=uuid4(),
            order=3,
            title="Güvenlik ve kapanış",
            items=(
                _madde(1, "instruction", "Kasa kapanışını 'Kasa devri' listesinde tamamlayın"),
                _madde(2, "choice", "Gaz vanası kapatıldı", kritik=True, secenekler=EVET_HAYIR),
                _madde(
                    3,
                    "confirm",
                    "Ocak, fırın, ızgara, tost makinesi kapalı ve fişleri çekili; ışıklar, "
                    "klima, tabela kapalı; su vanası kapalı",
                ),
                _madde(4, "photo", "Kapı ve kepenk kilitlendi, alarm kuruldu", foto=True),
            ),
        ),
    ),
)


ACILIS = LibraryTemplate(
    key="acilis-kafe",
    name="Açılış (kafe / hızlı servis)",
    category="Açılış",
    summary="Güne hazır, güvenli ve temiz açılış; gece yapılamayanların devralınması. 5 dk.",
    # 02-urun/07: açılıştan 45 dk önce, açılış + 30 dk, tolerans 60 dk.
    plan=PlanDefaults(anchor=Anchor("open", -45), duration_minutes=75, tolerance_minutes=60),
    sections=(
        Section(
            id=uuid4(),
            order=1,
            title="Gıda güvenliği",
            items=(
                _madde(
                    1, "temperature", "Süt dolabı sıcaklığı", kritik=True, alt=0, ust=4, birim="°C"
                ),
                _madde(
                    2,
                    "temperature",
                    "Mutfak buzdolabı sıcaklığı",
                    kritik=True,
                    alt=0,
                    ust=4,
                    birim="°C",
                ),
                _madde(
                    3,
                    "choice",
                    "Tarihi geçmiş veya etiketsiz ürün yok (SKT kontrolü yapıldı)",
                    secenekler=EVET_HAYIR,
                ),
            ),
        ),
        Section(
            id=uuid4(),
            order=2,
            title="Hazırlık",
            items=(
                _madde(
                    1, "confirm", "Espresso makinesi açıldı, ısındı, ilk shot atıldı ve döküldü"
                ),
                _madde(2, "confirm", "Su filtresi ve buz makinesi çalışıyor; buz haznesi temiz"),
                _madde(3, "confirm", "Günlük ön hazırlık (şurup, süt, sos, ekmek) tamamlandı"),
                _madde(
                    4, "photo", "Teşhir vitrini yerleştirildi; etiketler ve fiyatlar tam", foto=True
                ),
            ),
        ),
        Section(
            id=uuid4(),
            order=3,
            title="Salon ve açılış",
            items=(
                _madde(1, "confirm", "Salon ve dış oturma alanı temiz, masalar düzenli"),
                _madde(2, "confirm", "Tuvalet açılış kontrolü (temiz, sabun, kâğıt)"),
                _madde(3, "confirm", "Müzik, ışık, klima ve tabela açık", zorunlu=False),
                _madde(
                    4,
                    "choice",
                    "Personel üniformalı, saç ve sakal düzenli, eller yıkandı",
                    secenekler=EVET_HAYIR,
                ),
                # Sayı maddesi yayın doğrulamasında alt/üst sınır istiyor
                # (FR-0312; belgede sınır yalnızca sıcaklığa bağlanmış).
                # Geniş tutuldu: kasa tutarı puanı düşürmemeli, kayıt için.
                _madde(
                    5,
                    "number",
                    "Kasa açılış tutarı (para üstü) sayıldı",
                    birim="₺",
                    alt=0,
                    ust=100_000,
                ),
                _madde(6, "confirm", "Kapı açıldı"),
            ),
        ),
    ),
)


CATALOG: tuple[LibraryTemplate, ...] = (KAPANIS, ACILIS)


def find(key: str) -> LibraryTemplate | None:
    return next((sablon for sablon in CATALOG if sablon.key == key), None)


def find_by_name(name: str) -> LibraryTemplate | None:
    """Kopyanın adından kütüphane kaydına döner.

    Kopya adı **birebir** taşıyor; böylece "hangi şablondan geldi"
    sorusunu cevaplamak için sihirbazın durum tutmasına gerek kalmıyor
    (bkz. domain/setup: ilerleme veriden türetilir).
    """
    return next((sablon for sablon in CATALOG if sablon.name == name), None)


def plan_name(sablon: LibraryTemplate, brand: str | None = None) -> str:
    """Planın adı: "Kapanış · Kahve Durağı" gibi. Marka yoksa yalnız şablon."""
    return f"{sablon.category} · {brand}" if brand else sablon.category
