"""Senk alanı (CAP-07; FR-0701…FR-0708, BR-13, BR-24).

Mobil çevrimdışı çalışır: liste doldurulurken bağlantı olmayabilir,
fotoğraf çekilirken de. Bu modül o kuyruğun sunucu tarafındaki
**sözleşmesini** taşır (ADR-0013 devir sözleşmesi 3).

Üç karar burada yazılı ve üçü de çevrimdışının zorunlu sonucudur:

* **Saat düzeltmesi** (BR-13, FR-0704). Cihazın saati yanlış olabilir.
  Senk anında cihaz kendi saatini söyler; sunucu farkı hesaplar ve
  **çekim zamanını** düzeltir. Ham cihaz zamanı ve fark saklanır.
  Fark eşiği aşarsa kanıt bayrak alır — reddedilmez, işaretlenir.
* **Olay zamanı sunucunundur.** Düzeltme yalnızca *çekim* zamanına
  uygulanır; "zamanında mı" kararı sunucunun kendi saatiyle verilir.
  Aksi halde saati geri alan bir cihaz geçmiş pencereye yazabilirdi —
  kanıtlı listenin anlamı o noktada biter.
* **Kısmi başarı normaldir.** Bir kayıt reddedilirse kuyruğun kalanı
  yine işlenir; her kayıt kendi sonucunu alır. Tek bozuk kayıt tüm
  kuyruğu kilitlerse cihaz sonsuza kadar aynı isteği tekrarlar.

Saf: ağ bilmez, saat okumaz, depo bilmez. Zaman dışarıdan verilir.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Literal

from talimatname.domain.validation import ValidationError

#: Önbellek ufku (FR-0701): cihaz kaç saat ilerisini indirir.
MANIFEST_HORIZON_HOURS = 48
MANIFEST_HORIZON_MAX_HOURS = 168

#: Manifest kaç dakikada bir tazelenir (FR-0701).
MANIFEST_REFRESH_MINUTES = 15

#: Kuyruk sınırı (FR-0706): cihazda bekleyebilecek en çok kanıt ve süre.
QUEUE_EVIDENCE_LIMIT = 500
QUEUE_HOURS = 72

#: Tek çağrıda kabul edilen kayıt sayısı. Kuyruk büyükse cihaz böler:
#: yarım kalan bir istek, 500 kaydı birden kaybetmekten iyidir.
MAX_BATCH_ANSWERS = 200
MAX_BATCH_EVIDENCE = 50

#: Saat farkı bayrağı eşiği (BR-13, parametre tablosu: 10 dk). Tek
#: kaynak burası: cevap da kanıt da bu eşiği kullanır.
CLOCK_SKEW_FLAG_MINUTES = 10

#: Yapılamadı sebep seti (BR-09, FR-0801). v1'de **sabit**: ayarlardan
#: düzenlenebilir set v1.1'de (FR-0802). Sebep raporlanacağı için kod
#: taşınır, etiket değil — etiket değişince geçmiş rapor bozulmasın.
NotDoneReason = Literal[
    "no_material",
    "equipment_broken",
    "no_time",
    "not_authorized",
    "other",
]

NOT_DONE_REASON_LABELS: dict[NotDoneReason, str] = {
    "no_material": "Malzeme yok",
    "equipment_broken": "Ekipman arızalı",
    "no_time": "Zaman yetmedi",
    "not_authorized": "Yetkim yok",
    "other": "Diğer",
}

#: "Diğer" seçilince not zorunlu ve en az bu kadar karakter (BR-09).
OTHER_NOTE_MIN = 5


def clock_flagged(minutes: int | None) -> bool:
    """Sapma eşiği **aşıyor** mu (BR-13: "10 dk'yı aşıyorsa")."""
    return minutes is not None and abs(minutes) > CLOCK_SKEW_FLAG_MINUTES


def clock_offset(server_now: datetime, device_now: datetime | None) -> timedelta | None:
    """Cihaz saatinin sunucudan sapması. Pozitif = cihaz **ileri**.

    Senk anında ölçülür: cihazın o anki saati ile sunucunun saati
    arasındaki fark. Kuyruktaki kayıtların zamanı bu farkla düzeltilir.
    """
    if device_now is None:
        return None
    return device_now - server_now


def skew_minutes(offset: timedelta | None) -> int | None:
    """Sapmanın dakika cinsinden yuvarlanmış hali (saklanan ve raporlanan)."""
    if offset is None:
        return None
    return round(offset.total_seconds() / 60)


def corrected_time(device_value: datetime | None, offset: timedelta | None) -> datetime | None:
    """Cihaz saatiyle yazılmış bir zamanı sunucu saatine çevirir (BR-13).

    Cihaz 7 dakika ileriyse çekim zamanından 7 dakika düşülür. Fark
    bilinmiyorsa değer **olduğu gibi** bırakılır: uydurma bir düzeltme,
    düzeltmemekten kötüdür.
    """
    if device_value is None or offset is None:
        return device_value
    return device_value - offset


def check_not_done_reason(
    state: str,
    reason: str | None,
    note: str | None,
) -> NotDoneReason | None:
    """Yapılamadı sebebini denetler (BR-09, FR-0801).

    * Yapılamadı ise sebep **zorunlu**.
    * "Diğer" ise not zorunlu ve en az beş karakter.
    * Başka durumlarda sebep taşınamaz: geçmeyen bir maddenin sebebi
      "malzeme yok" olamaz, o başka bir hikâye.
    """
    if state != "not_done":
        if reason is not None:
            raise ValidationError("not_done_reason", "Sebep yalnızca 'yapılamadı' ile gönderilir")
        return None
    if reason is None:
        raise ValidationError("not_done_reason", "Yapılamadı sebebi zorunlu")
    if reason not in NOT_DONE_REASON_LABELS:
        raise ValidationError("not_done_reason", f"Bilinmeyen sebep: {reason}")
    if reason == "other" and len((note or "").strip()) < OTHER_NOTE_MIN:
        raise ValidationError(
            "note",
            f"'Diğer' seçildiğinde not zorunlu (en az {OTHER_NOTE_MIN} karakter)",
        )
    return reason
