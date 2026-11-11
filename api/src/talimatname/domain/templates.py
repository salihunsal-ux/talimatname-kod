"""Şablon, sürüm, bölüm ve madde (CAP-03; FR-0301…0312).

v1 bilerek dar: **6 cevaplı madde türü + talimat satırı**, madde başına
**üç ayar** (zorunlu · fotoğraf zorunlu · kritik), sıcaklık aralığı ve
yüzde puan. Koşul editörü, ağırlık ve eşik v1.1'dedir (ADR-0008).

Yayın doğrulaması (FR-0312) burada ve **tüm sorunları birden** döndürür:
kullanıcıya "önce şunu düzelt, sonra şunu" dedirtmek yerine listeyi bir
kerede gösteriyoruz.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Literal
from uuid import UUID

from talimatname.domain.actions import DUE_HOURS, Priority
from talimatname.domain.validation import ValidationError, clean_name

ItemType = Literal[
    "confirm",  # onay kutusu: yapıldı / yapılmadı
    "choice",  # çoktan seçmeli: seçeneklerin geçer/geçmez'i var
    "number",  # sayı (ör. yağ gün sayısı)
    "temperature",  # sıcaklık: aralık dışı = geçmez
    "text",  # serbest metin (puanlanır, boş bırakılamaz)
    "photo",  # yalnızca fotoğraf
    "instruction",  # talimat satırı: cevaplanmaz, puanlanmaz
]

VersionStatus = Literal["draft", "published", "archived"]

ITEM_TYPE_LABELS: dict[ItemType, str] = {
    "confirm": "Onay",
    "choice": "Çoktan seçmeli",
    "number": "Sayı",
    "temperature": "Sıcaklık",
    "text": "Metin",
    "photo": "Fotoğraf",
    "instruction": "Talimat",
}

#: Puanlanmayan tür: talimat satırı bilgi verir, cevap beklemez (FR-0306).
UNSCORED: frozenset[ItemType] = frozenset({"instruction"})

#: Aralık isteyen türler.
RANGED: frozenset[ItemType] = frozenset({"temperature", "number"})


@dataclass(frozen=True, slots=True)
class PublishIssue:
    """Yayına engel olan tek bir sorun. `where` arayüzde satırı işaretler."""

    where: str
    message: str


@dataclass(frozen=True, slots=True)
class ChoiceOption:
    label: str
    passing: bool = True


@dataclass(frozen=True, slots=True)
class Item:
    id: UUID
    order: int
    type: ItemType
    title: str
    hint: str | None = None
    required: bool = True
    photo_required: bool = False
    critical: bool = False
    options: tuple[ChoiceOption, ...] = ()
    min_value: float | None = None
    max_value: float | None = None
    unit: str | None = None
    #: Bu madde başarısız olursa aksiyon açılsın mı, hangi öncelikle
    #: (BR-10). `None`: açılmaz.
    #:
    #: Kritik maddede **kullanılmaz**: kritik kuralı zaten 4 saatlik bir
    #: aksiyon açıyor (BR-06) ve ikisi birden iki kayıt doğururdu.
    #: Bu bayrak kritik olmayan bulgular için: denetimde "ilaçlama
    #: belgesi güncel değil" kritik değildir ama takip edilmelidir —
    #: yoksa kayda geçer, kimseye gitmez.
    action_priority: Priority | None = None

    def validated(self) -> Item:
        if self.type not in ITEM_TYPE_LABELS:
            raise ValidationError("type", f"Bilinmeyen madde türü: {self.type}")
        if self.action_priority is not None and self.action_priority not in DUE_HOURS:
            raise ValidationError("action_priority", f"Bilinmeyen öncelik: {self.action_priority}")
        return replace(self, title=clean_name(self.title, "title", max_length=160))

    @property
    def opens_action_on_fail(self) -> bool:
        """Başarısız cevabı aksiyon doğuruyor mu?

        Kritik madde zaten doğuruyor; bayrak yalnızca kritik olmayanı
        kapsıyor, iki kayıt çıkmasın.
        """
        return not self.critical and self.action_priority is not None

    @property
    def scored(self) -> bool:
        return self.type not in UNSCORED

    def issues(self, konum: str) -> list[PublishIssue]:
        """Bu maddenin yayına engel sorunları."""
        sorunlar: list[PublishIssue] = []
        if self.type == "choice" and len(self.options) < 2:
            sorunlar.append(PublishIssue(konum, "Çoktan seçmeli maddede en az iki seçenek olmalı"))
        if self.type == "choice" and self.options and not any(o.passing for o in self.options):
            sorunlar.append(
                PublishIssue(konum, "Seçeneklerden en az biri 'geçer' olarak işaretlenmeli")
            )
        if self.type in RANGED:
            if self.min_value is None or self.max_value is None:
                sorunlar.append(PublishIssue(konum, "Alt ve üst sınır girilmeli"))
            elif self.min_value >= self.max_value:
                sorunlar.append(PublishIssue(konum, "Alt sınır üst sınırdan küçük olmalı"))
        if self.type == "instruction" and (self.critical or self.photo_required):
            sorunlar.append(
                PublishIssue(konum, "Talimat satırı kritik olamaz ve fotoğraf isteyemez")
            )
        if self.critical and not self.required:
            sorunlar.append(PublishIssue(konum, "Kritik madde zorunlu olmalı"))
        return sorunlar


@dataclass(frozen=True, slots=True)
class Section:
    id: UUID
    order: int
    title: str
    items: tuple[Item, ...] = ()

    def validated(self) -> Section:
        return replace(
            self,
            title=clean_name(self.title, "title", max_length=80),
            items=tuple(i.validated() for i in self.items),
        )


@dataclass(frozen=True, slots=True)
class VersionSettings:
    """Şablon sürümü ayarları (FR-0308).

    `camera_only`: kanıt yalnızca uygulama içi kamerayla alınır, galeriden
    yükleme yoktur (ADR-0004). v1'de varsayılan ve değiştirilebilir tek
    ayar budur; tolerans ve eşik plana ve v1.1'e aittir.
    """

    camera_only: bool = True


@dataclass(frozen=True, slots=True)
class TemplateVersion:
    id: UUID
    template_id: UUID
    version_no: int
    status: VersionStatus = "draft"
    sections: tuple[Section, ...] = ()
    settings: VersionSettings = field(default_factory=VersionSettings)
    published_at: datetime | None = None

    def validated(self) -> TemplateVersion:
        return replace(self, sections=tuple(s.validated() for s in self.sections))

    @property
    def items(self) -> tuple[Item, ...]:
        return tuple(madde for bolum in self.sections for madde in bolum.items)

    @property
    def scored_item_count(self) -> int:
        return sum(1 for madde in self.items if madde.scored)

    @property
    def critical_item_count(self) -> int:
        return sum(1 for madde in self.items if madde.critical)

    @property
    def photo_item_count(self) -> int:
        return sum(1 for madde in self.items if madde.photo_required or madde.type == "photo")

    def publish_issues(self) -> list[PublishIssue]:
        """Yayına engel tüm sorunlar (FR-0312). Boş liste = yayınlanabilir."""
        sorunlar: list[PublishIssue] = []
        if not self.sections:
            sorunlar.append(PublishIssue("template", "En az bir bölüm olmalı"))
        for bolum in self.sections:
            if not bolum.items:
                sorunlar.append(PublishIssue(str(bolum.id), f"'{bolum.title}' bölümü boş"))
            for madde in bolum.items:
                sorunlar.extend(madde.issues(str(madde.id)))
        if self.scored_item_count == 0 and self.sections:
            sorunlar.append(
                PublishIssue("template", "En az bir cevaplanabilir madde olmalı (talimat sayılmaz)")
            )
        return sorunlar


@dataclass(frozen=True, slots=True)
class Template:
    id: UUID
    name: str
    category: str | None = None

    def validated(self) -> Template:
        return replace(self, name=clean_name(self.name, "name"))
