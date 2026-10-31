"""Ekle-yalnız olay günlüğü ve hash zinciri (ST-099; FR-1301, FR-1304).

Denetim izinin iddiası tek cümle: **kayıt sonradan değiştirilmemiştir.**
Bunu söyleyebilmek için her olay bir öncekinin özetini içeriyor; bir
satır değişirse ondan sonraki bütün özetler tutmaz ve kırılma noktası
bulunabilir (FR-1304).

Burada yalnızca **hesap** var: olayın kanonik gösterimi, zincir özeti
ve doğrulama. Saat, veritabanı ve istek bağlamı serviste (ADR-0014).

Üç karar burada yazılı:

**Kanonik gösterim JSON, ayırıcı değil.** Alan değerlerinde Türkçe
metin ve serbest not var; "a|b|c" gibi birleştirme, içinde ayırıcı
geçen bir değerle iki farklı olayı aynı dizeye götürebilirdi. JSON
sıralı anahtarla ve ayırıcısız basılıyor.

**Zincir hesap başına.** Kiracılar birbirinin zincirine karışmaz:
tek zincir olsaydı bir hesabın olay hızı diğerinin doğrulamasını
yavaşlatır, kiracı yalıtımı da (RLS) zinciri okunamaz kılardı.

**Zincirin sınırı açıkça yazılı.** Hash zinciri, kayıtları
*tek tek* değiştirmeyi görünür kılar: değişen kaydın özeti tutmaz.
Veritabanına yazma yetkisi olan birinin bütün zinciri baştan
hesaplaması **engellenmez** — onu ancak dışarıya çıpalanmış bir
günlük kökü durdurur (RFC 3161 zaman damgası, FR-1302, v1.1).
Ürün bu yüzden "değiştirilemez" demiyor, "değişiklik görünür" diyor.

**Özet küçük ve işle ilgili.** `before`/`after` yalnızca değişen
alanların kısa karşılığı; kişisel veri taşımaz (KVKK, BR-21). Adı
değil kimliği yazıyoruz; maskelenen bir kullanıcının günlüğü de
maskelenmiş kalsın.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID

from talimatname.domain.validation import ValidationError

#: Zincirin ilk halkası. Boş dize değil: "özet hesaplanmadı" ile
#: "önceki yok" ayrımı günlüğe bakan insanda da belli olsun.
GENESIS = "0" * 64

#: Olay türleri. Serbest dize değil **liste**: tür adı sözleşmedir,
#: doğrulama sayfası ve denetim izi ekranı buna göre yazılır. Yeni tür
#: eklemek bilinçli bir karar olsun diye burada toplanıyor.
EVENT_TYPES: dict[str, str] = {
    "oturum.acildi": "Oturum açıldı",
    "oturum.reddedildi": "Oturum reddedildi",
    "calistirma.gonderildi": "Çalıştırma gönderildi",
    "calistirma.kacirildi": "Çalıştırma kaçırıldı",
    "kanit.alindi": "Kanıt alındı",
    "kanit.tekrar_denemesi": "Aynı fotoğraf ikinci kez denendi",
    "kanit.supuruldu": "Bekleyen kanıt süpürüldü",
    "aksiyon.eskalasyon": "Aksiyon eskalasyonu",
    "rapor.uretildi": "Rapor üretildi",
    "personel.davet": "Personel davet edildi",
    "personel.guncellendi": "Personel güncellendi",
    "plan.yayinlandi": "Plan yayınlandı",
}


class SequenceTaken(Exception):
    """Sıra numarası başka bir yazma tarafından alınmış.

    Zincirin kuralı: sıra hesap içinde tekil ve boşluksuz. İki istek
    aynı anda yazarsa ikisi de aynı başı okuyup zinciri çatallardı;
    depo bunu reddediyor, servis yeniden deniyor. Yarış durumu, alan
    hatası değil — bu yüzden `DomainError` değil.
    """


#: Özet alanlarının üst sınırı: günlük, verinin kopyası değil izidir.
MAX_SUMMARY_FIELDS = 20
MAX_SUMMARY_LENGTH = 200


@dataclass(frozen=True, slots=True)
class AuditEvent:
    """Tek olay. `hash` hesaplanmış hâliyle taşınır, yeniden üretilebilir."""

    id: UUID
    sequence: int
    event_type: str
    at: datetime
    object_type: str
    object_id: UUID | None = None
    actor_id: UUID | None = None
    ip: str | None = None
    device: str | None = None
    before: dict[str, str] = field(default_factory=dict)
    after: dict[str, str] = field(default_factory=dict)
    prev_hash: str = GENESIS
    hash: str = ""

    def validated(self) -> AuditEvent:
        if self.event_type not in EVENT_TYPES:
            raise ValidationError("event_type", f"Bilinmeyen olay türü: {self.event_type}")
        if self.sequence < 1:
            raise ValidationError("sequence", "Sıra 1'den başlar")
        if self.at.tzinfo is None:
            raise ValidationError("at", "Zaman saat dilimli olmalı (sunucu saati, UTC)")
        for ad, ozet in (("before", self.before), ("after", self.after)):
            if len(ozet) > MAX_SUMMARY_FIELDS:
                raise ValidationError(ad, f"En çok {MAX_SUMMARY_FIELDS} alan özetlenebilir")
            for anahtar, deger in ozet.items():
                if len(deger) > MAX_SUMMARY_LENGTH:
                    raise ValidationError(ad, f"'{anahtar}' özeti çok uzun")
        return self

    @property
    def label(self) -> str:
        return EVENT_TYPES[self.event_type]


def canonical(event: AuditEvent) -> str:
    """Olayın imzalanan gösterimi. Alan eklenirse zincir değişir.

    `hash` **dışarıda**: kendi özetini içeren bir gösterim hesaplanamaz.
    `prev_hash` içeride, zincir oradan doğuyor.
    """
    govde: dict[str, Any] = {
        "id": str(event.id),
        "sequence": event.sequence,
        "event_type": event.event_type,
        "at": event.at.isoformat(),
        "object_type": event.object_type,
        "object_id": str(event.object_id) if event.object_id else None,
        "actor_id": str(event.actor_id) if event.actor_id else None,
        "ip": event.ip,
        "device": event.device,
        "before": event.before,
        "after": event.after,
        "prev_hash": event.prev_hash,
    }
    return json.dumps(govde, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def chain_hash(event: AuditEvent) -> str:
    return hashlib.sha256(canonical(event).encode("utf-8")).hexdigest()


def sealed(event: AuditEvent) -> AuditEvent:
    """Olayı özetiyle mühürler: kayda bu hâli yazılır."""
    from dataclasses import replace

    return replace(event.validated(), hash=chain_hash(event))


@dataclass(frozen=True, slots=True)
class ChainBreak:
    """Zincirin kırıldığı yer (FR-1304). Hangi kayıt, neden."""

    sequence: int
    event_id: UUID
    reason: str


def verify_chain(events: list[AuditEvent], *, expected_start: str = GENESIS) -> list[ChainBreak]:
    """Zinciri baştan hesaplar; kırılmaları **hepsini** döner.

    İlk kırılmada durmuyoruz: bir kaydı değiştiren, sonraki kayıtları
    da düzeltmeye çalışmış olabilir — rapor hepsini göstersin ki
    müdahalenin kapsamı görülsün.

    `expected_start`, aralığın bir ortadan başladığı durumlar için:
    günlüğün tamamı yerine son ayı doğrularken öncekinin özeti verilir.
    """
    kirilmalar: list[ChainBreak] = []
    onceki_ozet = expected_start
    onceki_sira: int | None = None

    for olay in events:
        if onceki_sira is not None and olay.sequence != onceki_sira + 1:
            kirilmalar.append(
                ChainBreak(
                    olay.sequence,
                    olay.id,
                    f"Sıra atlamış: {onceki_sira} sonrası {olay.sequence}",
                )
            )
        elif olay.prev_hash != onceki_ozet:
            kirilmalar.append(ChainBreak(olay.sequence, olay.id, "Önceki kaydın özeti tutmuyor"))
        elif chain_hash(olay) != olay.hash:
            kirilmalar.append(
                ChainBreak(olay.sequence, olay.id, "Kaydın kendi özeti tutmuyor: içerik değişmiş")
            )
        onceki_ozet = olay.hash
        onceki_sira = olay.sequence
    return kirilmalar


def summary_of(
    before: dict[str, Any] | None, after: dict[str, Any] | None
) -> tuple[dict[str, str], dict[str, str]]:
    """Önce/sonra sözlüklerini **yalnızca değişen** alanlara indirger.

    Değişmeyeni yazmak günlüğü şişirir ve okuyanı yorar: denetim
    konuşması "ne değişti" sorusuyla başlıyor.
    """
    onceki = before or {}
    sonraki = after or {}
    anahtarlar = sorted(set(onceki) | set(sonraki))
    once: dict[str, str] = {}
    sonra: dict[str, str] = {}
    for anahtar in anahtarlar:
        a, b = onceki.get(anahtar), sonraki.get(anahtar)
        if a == b:
            continue
        if a is not None:
            once[anahtar] = _kisalt(a)
        if b is not None:
            sonra[anahtar] = _kisalt(b)
    return once, sonra


def _kisalt(deger: Any) -> str:
    metin = str(deger)
    return metin if len(metin) <= MAX_SUMMARY_LENGTH else metin[: MAX_SUMMARY_LENGTH - 1] + "…"
