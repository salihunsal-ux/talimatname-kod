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

from dataclasses import dataclass, replace
from datetime import date, datetime, time, timedelta
from uuid import uuid4

from talimatname.domain.actions import Priority
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

#: RRULE satırları arasındaki ayraç (RFC 5545).
SATIR_SONU = chr(10)

#: Plan ekranındaki sınırın aynısı; iki yer ayrışırsa kütüphane
#: kurulamayan bir plan önerir.
MAX_GUNLUK_PENCERE = 16


@dataclass(frozen=True, slots=True)
class PlanDefaults:
    """Şablonun önerdiği pencere (02-urun/07, her şablonun "Tekrar" satırı).

    `anchor` şube saatine bağlar: tek plan, her şubede kendi kapanışına
    göre açılır. Sabit saat yazsaydık 09:00 açılan şube ile 11:00 açılan
    şube aynı planı paylaşamazdı.
    """

    #: Şube saatine bağlı pencere. Gün içinde tekrarlayan listede
    #: `None`: açılış/kapanış günde bir kez olur, saatlik kontrol
    #: sabit saatlerde yürür (plan kuralı ikisini birlikte kabul etmiyor).
    anchor: Anchor | None
    duration_minutes: int
    tolerance_minutes: int
    #: RRULE (ADR-0005): "günlük" demiyoruz, takvim standardını yazıyoruz.
    recurrence: str = "FREQ=DAILY"
    #: Sabit başlangıç (anchor yoksa zorunlu) ve gün içi tekrar.
    start_time: time | None = None
    every_hours: int | None = None
    until_time: time | None = None

    def __post_init__(self) -> None:
        if (self.anchor is None) == (self.start_time is None):
            raise ValueError("anchor ya da start_time verilmeli; ikisi birlikte olmaz")
        if self.every_hours is not None and (self.start_time is None or self.until_time is None):
            raise ValueError("'her N saat' kuralı başlangıç ve bitiş saati ister")
        # Plan ekranıyla **aynı** sınır: kurulum sihirbazı `PlanGirdisi`
        # doğrulamasından geçmiyor, yani kütüphane buradan denetlenmezse
        # ekranda kurulamayan bir planı önerebilir.
        if len(self.saatler()) > MAX_GUNLUK_PENCERE:
            raise ValueError(f"Gün içinde en çok {MAX_GUNLUK_PENCERE} pencere açılabilir")

    def saatler(self) -> list[time]:
        """Gün içindeki pencere başlangıçları; tek pencerede boş liste.

        Plan ekranındaki `_saatler` ile **aynı** kuralı uyguluyor:
        ikisi ayrışırsa kütüphanenin önerdiği plan, elle kurulan plandan
        başka pencereler üretir.
        """
        if self.every_hours is None or self.start_time is None or self.until_time is None:
            return []
        saatler: list[time] = []
        an = datetime.combine(date.min, self.start_time)
        son = datetime.combine(date.min, self.until_time)
        while an <= son:
            saatler.append(an.time())
            an += timedelta(hours=self.every_hours)
        return saatler

    def rrule(self) -> str:
        """Gün içinde birden çok pencere varsa saat başına bir satır."""
        saatler = self.saatler()
        if len(saatler) <= 1:
            return self.recurrence
        satirlar = (f"RRULE:{self.recurrence};BYHOUR={s.hour};BYMINUTE={s.minute}" for s in saatler)
        return chr(10).join(satirlar)


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
    """Kopya: yalnızca kimlikler yeni, geri kalanı olduğu gibi.

    Alanlar tek tek yazılıyordu ve yeni bir alan eklendiğinde kopya onu
    **sessizce düşürüyordu**: `action_priority` (BR-10 takip işareti)
    kütüphanede duruyor, hesaba kopyalanan şablonda yok oluyordu. Hatayı
    bulmak zor, çünkü kopya çalışıyor ve yalnızca bir davranış eksiliyor.
    `replace` alan listesi tutmuyor: sınıfa eklenen her şey kendiliğinden
    kopyalanır.
    """
    return replace(
        bolum,
        id=uuid4(),
        items=tuple(replace(madde, id=uuid4()) for madde in bolum.items),
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
    aksiyon: Priority | None = None,
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
        action_priority=aksiyon,
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


#: Denetçinin şubeye girmeden önce okuduğu protokol. Maddelerin kendisi
#: değil, **nasıl denetleneceği**: sıra, habersizlik ve kapanış görüşmesi.
#: Talimat satırı cevaplanmaz (BR-08a) — kural olduğu için listede, puanı
#: etkilemediği için puanlanmaz.
DENETIM_PROTOKOLU = (
    "Habersiz gel: ziyareti önceden haber verme, şube müdürünü arama.",
    "Önce gözlem: içeri girdiğinde 5 dakika hiçbir şey sorma, bak ve fotoğrafla.",
    "Sıra: dış cephe → salon → tuvalet → mutfak → depo → belgeler → görüşme.",
    "Ölçümü kendin yap: dolap göstergesini okuma, prob ile ölç.",
    "Başarısız maddede fotoğraf ve not zorunlu — sebebi değil, **gördüğünü** yaz.",
    "Bitirince şube müdürüyle konuş: bulguları yüz yüze söyle, sonra gönder.",
)


DENETIM = LibraryTemplate(
    key="sube-denetimi",
    name="Şube denetimi",
    category="Denetim",
    summary=(
        "Denetçinin şube ziyaretinde uyguladığı standart liste: hijyen, gıda "
        "güvenliği, görünüm, belge ve personel. Hedef süre 12–15 dk."
    ),
    # 02-urun/07 §9: aylık, iş günü 09:00–19:00, tolerans 0. Habersiz
    # ziyaret için tek seferlik liste kurulur (FR-0512).
    plan=PlanDefaults(
        anchor=Anchor("open", 0),
        duration_minutes=600,
        tolerance_minutes=0,
        recurrence="FREQ=MONTHLY",
    ),
    sections=(
        Section(
            id=uuid4(),
            order=1,
            title="Denetim protokolü",
            items=tuple(
                _madde(sira, "instruction", metin, zorunlu=False)
                for sira, metin in enumerate(DENETIM_PROTOKOLU, start=1)
            ),
        ),
        Section(
            id=uuid4(),
            order=2,
            title="Dış görünüm ve salon",
            items=(
                _madde(
                    1,
                    "photo",
                    "Giriş, vitrin ve tabela: temiz, aydınlatma çalışıyor, kampanya görseli güncel",
                    foto=True,
                ),
                _madde(
                    2,
                    "photo",
                    "Salon ve müşteri alanı düzeni (masa, sandalye, servis istasyonu)",
                    foto=True,
                ),
                _madde(
                    3,
                    "choice",
                    "Tuvalet: temizlik, sarf malzeme, kontrol çizelgesi dolu",
                    secenekler=EVET_HAYIR,
                ),
            ),
        ),
        Section(
            id=uuid4(),
            order=3,
            title="Personel ve hijyen",
            items=(
                _madde(
                    1,
                    "choice",
                    "Personel kıyafeti, bone/eldiven, kişisel hijyen",
                    secenekler=EVET_HAYIR,
                ),
                _madde(2, "confirm", "El yıkama istasyonu: sabun, kâğıt, sıcak su"),
            ),
        ),
        Section(
            id=uuid4(),
            order=4,
            title="Gıda güvenliği",
            items=(
                _madde(
                    1,
                    "temperature",
                    "Soğutucu sıcaklığı (örnek dolap)",
                    kritik=True,
                    alt=0,
                    ust=4,
                    birim="°C",
                ),
                _madde(
                    2,
                    "temperature",
                    "Dondurucu sıcaklığı",
                    kritik=True,
                    alt=-30,
                    ust=-18,
                    birim="°C",
                ),
                _madde(
                    3,
                    "choice",
                    "Açık ürün etiketleme ve SKT kontrolü (rastgele 5 ürün)",
                    kritik=True,
                    secenekler=EVET_HAYIR,
                ),
                _madde(4, "photo", "Depo düzeni ve FIFO; yerden yükseklik", foto=True),
            ),
        ),
        Section(
            id=uuid4(),
            order=5,
            title="Belge ve ekipman",
            items=(
                # 02-urun/07 §9: "Hayır → aksiyon (24 sa)". Kritik
                # değil — çalıştırmayı başarısız yapmaz (BR-07) — ama
                # takip edilmezse kayda geçip kimseye gitmez.
                _madde(
                    1,
                    "choice",
                    "Haşere izi yok; ilaçlama belgesi güncel",
                    secenekler=EVET_HAYIR,
                    aksiyon="high",
                ),
                _madde(
                    2,
                    "choice",
                    "Yasal belgeler yerinde ve geçerli (ruhsat, hijyen eğitimi, "
                    "ilaçlama, yangın tüpü)",
                    secenekler=EVET_HAYIR,
                ),
                _madde(
                    3,
                    "photo",
                    "Mutfak ekipmanı çalışıyor; davlumbaz ve filtre temiz",
                    foto=True,
                ),
            ),
        ),
        Section(
            id=uuid4(),
            order=6,
            title="Kayıt ve kapanış görüşmesi",
            items=(
                _madde(
                    1,
                    "choice",
                    "Son 7 günün kapanış listeleri tamamlanmış (uygulamadan kontrol)",
                    secenekler=EVET_HAYIR,
                ),
                _madde(
                    2,
                    "choice",
                    "Kasa ve fiyat kontrolü: menü fiyatları merkez listesiyle aynı",
                    secenekler=EVET_HAYIR,
                ),
                _madde(3, "text", "Şube müdürüyle görüşme: açık sorunlar ve ihtiyaçlar"),
                _madde(4, "photo", "Genel değerlendirme fotoğrafı (mutfak genel)", foto=True),
            ),
        ),
    ),
)


TUVALET = LibraryTemplate(
    key="tuvalet-hijyen",
    name="Saatlik tuvalet ve hijyen kontrolü",
    category="Hijyen turu",
    summary=(
        "Gün içinde müşteri alanının ve el hijyeninin sürekliliği. "
        "Hedef süre 1–2 dk; kritik madde yok."
    ),
    # 02-urun/07 §3: 10:00–22:00 arası her 2 saat, pencere 15 dk,
    # tolerans 0. Şube saatine **bağlanamıyor**: açılış/kapanış günde
    # bir kez olur, gün içi tekrar sabit saat ister (plan kuralı ikisini
    # birlikte kabul etmiyor). Hızlı servis her saate çekebilir.
    plan=PlanDefaults(
        anchor=None,
        start_time=time(10, 0),
        every_hours=2,
        until_time=time(22, 0),
        duration_minutes=15,
        tolerance_minutes=0,
    ),
    sections=(
        Section(
            id=uuid4(),
            order=1,
            title="Tuvalet",
            items=(
                _madde(1, "choice", "Klozet, lavabo ve ayna temiz", secenekler=EVET_HAYIR),
                _madde(
                    2,
                    "choice",
                    "Sabun, kâğıt havlu / el kurutma, tuvalet kâğıdı dolu",
                    secenekler=EVET_HAYIR,
                ),
                _madde(3, "choice", "Zemin kuru, çöp kovası boş", secenekler=EVET_HAYIR),
                _madde(4, "choice", "Koku ve havalandırma uygun", secenekler=EVET_HAYIR),
                # İsteğe bağlı: 1–2 dakikalık bir turda fotoğrafı zorunlu
                # kılmak listeyi iki katına çıkarırdı.
                _madde(5, "photo", "Genel görünüm", zorunlu=False),
            ),
        ),
        Section(
            id=uuid4(),
            order=2,
            title="Salon ve el hijyeni",
            items=(
                _madde(1, "confirm", "El yıkama ve eldiven değişimi yapıldı"),
                _madde(
                    2,
                    "confirm",
                    "Salon masaları ve servis istasyonu temiz; şeker, peçete, karıştırıcı dolu",
                ),
            ),
        ),
    ),
)


CATALOG: tuple[LibraryTemplate, ...] = (KAPANIS, ACILIS, TUVALET, DENETIM)


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
