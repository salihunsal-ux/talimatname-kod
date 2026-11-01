"""Belge doğrulama: kâğıttaki koddan kayda (ST-101; FR-1218).

Denetçinin elinde bir kâğıt var ve tek sorusu şu: **bu kâğıdı sistem mi
üretti, sonradan dokunulmuş mu?** Panele giremez (kullanıcı değil),
bu yüzden kodun oturumsuz sorulabildiği bir yol gerekiyor.

Dört karar burada:

**Doğrula, açıklama.** Sayfa, kâğıtta **zaten yazılı olan** alanları
döner: belge türü, dönem, şube kodu, üretim zamanı. Denetçi bunları
elindekiyle karşılaştırıyor. Puan, madde sonuçları, kimin ürettiği, IP
ve cihaz **dönmüyor** — kodu eline geçiren herkese şirketin iç verisini
açmak olurdu (BR-21, KVKK). Kâğıt neyi gösteriyorsa sayfa onu doğruluyor,
fazlasını söylemiyor.

**Yalnızca rapor olayları.** Kod, olay özetinin ilk 12 basamağı; günlükte
oturum ve kanıt olayları da var ve onların özetleri de bu önekle
başlayabilir. Belge kodu olarak yalnızca `rapor.uretildi` kabul ediliyor:
yoksa sayfa, rapor olmayan bir kaydı belge gibi gösterebilirdi.

**Tek kayıt doğrulanıyor, zincirin tamamı değil.** Kaydın kendi özeti ve
önceki halkaya bağı sınanıyor. Her istekte bütün günlüğü okumak hem
pahalı, hem dışarıdan tetiklenebilen bir yük kapısı olurdu. Zincirin
tamamı `izi_dogrula` ile (işletmecinin işi) sınanıyor; sayfa bunu
gizlemiyor, neyi doğruladığını yazıyor.

**Çakışma gizlenmiyor.** 48 bitlik önek iki kayda uyarsa "ilkini"
göstermek, denetçiye yanlış kaydı göstermek olurdu: hata dönüyor.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from talimatname.domain.audit import (
    DOCUMENT_LABELS,
    AuditEvent,
    format_code,
    record_intact,
)
from talimatname.domain.errors import DomainError, ErrorKind
from talimatname.services.audit import AuditService

#: Belge kodu üreten tek olay türü (bkz. modül başlığı).
DOCUMENT_EVENT = "rapor.uretildi"

DEFAULT_TIMEZONE = "Europe/Istanbul"


class DocumentNotFound(DomainError):
    code = "belge-bulunamadi"
    title = "Bu koda ait belge kaydı yok"
    kind: ErrorKind = "not_found"


class AmbiguousCode(DomainError):
    code = "belge-kodu-benzersiz-degil"
    title = "Kod birden fazla kayda uyuyor"
    kind: ErrorKind = "conflict"


@dataclass(frozen=True, slots=True)
class DocumentVerification:
    """Doğrulama sayfasının gösterdiği şey — ve göstermediği.

    Alan listesi bilinçli kısa: her yeni alan, kodu eline geçiren
    herkese açılmış bir veri demek.
    """

    code: str
    document: str
    document_label: str
    issued_at: datetime
    timezone: str
    period: str | None
    branch_code: str | None
    record_intact: bool
    chain_linked: bool

    @property
    def trustworthy(self) -> bool:
        """Kayıt değişmemiş **ve** zincire bağlı."""
        return self.record_intact and self.chain_linked


class VerificationService:
    def __init__(
        self,
        audit: AuditService,
        *,
        timezone: Callable[[], str] = lambda: DEFAULT_TIMEZONE,
    ) -> None:
        self._izi = audit
        self._saat_dilimi = timezone

    def check(self, code: str) -> DocumentVerification:
        """Kodu kayda çevirir. Bulunamazsa `DocumentNotFound`.

        Saat dilimi dönüyor çünkü kâğıtta **yerel** saat yazılı;
        sayfa UTC gösterse denetçi iki farklı saat görür ve kâğıdın
        sahte olduğunu düşünürdü.
        """
        eslesmeler = self._izi.by_code(code)
        belgeler = [o for o in eslesmeler if o.event_type == DOCUMENT_EVENT]
        if not belgeler:
            raise DocumentNotFound(detail="Kod sistemde üretilmiş bir belgeye ait değil")
        if len(belgeler) > 1:
            raise AmbiguousCode(
                detail="Aynı önekle iki kayıt var; belgeyi üreten hesaptan doğrulama isteyin"
            )
        return self._ozet(belgeler[0])

    def _ozet(self, olay: AuditEvent) -> DocumentVerification:
        tur = olay.after.get("tur", "")
        onceki = self._izi.previous(olay)
        return DocumentVerification(
            code=format_code(olay.hash),
            document=tur,
            document_label=DOCUMENT_LABELS.get(tur, "Belge"),
            issued_at=olay.at,
            timezone=self._saat_dilimi(),
            period=olay.after.get("donem"),
            branch_code=olay.after.get("sube"),
            record_intact=record_intact(olay),
            # İlk halkanın öncesi yok: bağsız değil, zincirin başı.
            chain_linked=olay.sequence == 1
            or (onceki is not None and onceki.hash == olay.prev_hash),
        )


__all__ = [
    "AmbiguousCode",
    "DocumentNotFound",
    "DocumentVerification",
    "VerificationService",
]
