"""Kanıt alanı (CAP-06; FR-0604…0606, FR-0614, FR-0615; BR-12…BR-15).

Ürünün iddiası "iş yapıldı" değil, **"iş yapıldığının kanıtı var"**.
Bu yüzden kanıt burada bir dosya değil, bir **kayıt**: kimin, nerede,
ne zaman, hangi cihazla çektiği ve dosyanın özeti birlikte duruyor.

Üç kural bu dosyada ve üçü de güveni taşıyor:

* **Tekillik** (FR-0614). Aynı SHA-256 hesapta ikinci kez kullanılamaz.
  Geçen haftanın fotoğrafını yeniden göndermek, listeyi doldurmanın en
  kolay yolu olurdu; kapatılmazsa ürünün tek iddiası çöker.
* **Bayraklar** (FR-0615). Galeriden gelen, konumu şubeden uzak, saati
  kaymış ya da geç senklenmiş kanıt işaretlenir. **Bayrak suçlama
  değil, incelemeye çağrıdır** — sistem kimseyi suçlamıyor, bakılacak
  yeri gösteriyor.
* **Değişmezlik** (BR-12). Kanıt üzerine yazılmaz, silinmez. Düzeltme
  gerekiyorsa aksiyona not eklenir.

Saf: dosya okumaz, saat okumaz, ağ bilmez. Zaman ve ölçüm dışarıdan.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from math import asin, cos, radians, sin, sqrt
from typing import Literal
from uuid import UUID

from talimatname.domain.sync import QUEUE_HOURS, clock_flagged
from talimatname.domain.validation import ValidationError

EvidenceStatus = Literal["pending", "stored", "stamped"]

#: Dosyanın hangi kopyası isteniyor (FR-0606, FR-1202, FR-1208).
#: `raw` özeti tutulan dosyadır ve doğrulamanın dayanağıdır; `stamped`
#: dışarı giden kopya; `thumbnail` ızgara için.
EvidenceVariant = Literal["raw", "stamped", "thumbnail"]

#: Bayraklar (FR-0615). Sıra önemli: panelde bu sırayla gösterilir.
EvidenceFlag = Literal["gallery", "no_location", "far_location", "clock_skew", "late_sync"]

FLAG_LABELS: dict[EvidenceFlag, str] = {
    "gallery": "Galeriden yüklendi",
    "no_location": "Konum yok",
    "far_location": "Konum şube dışında",
    "clock_skew": "Cihaz saati farklı",
    "late_sync": "Geç senklendi",
}

#: Madde başına fotoğraf (FR-0604). Varsayılan 1, en çok 3.
DEFAULT_PER_ITEM = 1
MAX_PER_ITEM = 3

#: Cihaz ~300 KB'a sıkıştırıyor (FR-0605). Buradaki sınır **üst sınır**:
#: sıkıştırma başarısızsa ya da istemci uymuyorsa sunucu reddetsin.
MAX_BYTES = 3 * 1024 * 1024

ALLOWED_TYPES: frozenset[str] = frozenset({"image/jpeg", "image/png"})

#: Parametre tablosu (03-is-kurallari): uzak konum 500 m.
FAR_LOCATION_METERS = 500

#: "Geç senklendi" eşiği (FR-0706: cihaz kuyruğu 72 saat). Daha kısa
#: bir eşik, uçak modunda geçirilen normal bir hafta sonunu şüpheli
#: gösterirdi; bayrağın anlamı seyrek olmasından geliyor.
LATE_SYNC_HOURS = QUEUE_HOURS

#: İmzalı kanıt bağlantısının ömrü (FR-1305).
URL_TTL = timedelta(minutes=15)

SHA256 = re.compile(r"^[0-9a-f]{64}$")


def check_digest(value: str) -> str:
    """SHA-256 küçük harf onaltılık, 64 karakter. Başka bir şey kabul edilmez."""
    temiz = value.strip().lower()
    if not SHA256.match(temiz):
        raise ValidationError("sha256", "Geçerli bir SHA-256 özeti değil")
    return temiz


def check_content_type(value: str) -> str:
    temiz = value.strip().lower()
    if temiz not in ALLOWED_TYPES:
        raise ValidationError("content_type", f"Desteklenmeyen dosya türü: {value}")
    return temiz


def check_size(value: int) -> int:
    if value <= 0:
        raise ValidationError("size_bytes", "Dosya boyutu sıfır olamaz")
    if value > MAX_BYTES:
        raise ValidationError(
            "size_bytes", f"Dosya çok büyük ({value} bayt); en çok {MAX_BYTES} bayt"
        )
    return value


def distance_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """İki nokta arası yaklaşık mesafe (haversine, metre).

    Küre varsayımı birkaç metre hata verir; 500 m eşiği için fazlasıyla
    yeterli ve bağımlılık gerektirmiyor.
    """
    yaricap = 6_371_000.0
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 2 * yaricap * asin(sqrt(a))


def evidence_flags(
    *,
    from_gallery: bool,
    latitude: float | None,
    longitude: float | None,
    branch_latitude: float | None,
    branch_longitude: float | None,
    clock_skew_minutes: int | None,
    captured_at: datetime | None,
    received_at: datetime,
) -> tuple[EvidenceFlag, ...]:
    """Kanıtın bayrakları (FR-0615, BR-13…BR-15).

    Şubenin konumu tanımlı değilse "uzak" bayrağı **verilmez**: ölçüye
    dayanmayan bir şüphe işareti koymak, bayrağın anlamını boşaltır.
    """
    bayraklar: list[EvidenceFlag] = []
    if from_gallery:
        bayraklar.append("gallery")

    if latitude is None or longitude is None:
        bayraklar.append("no_location")
    elif branch_latitude is not None and branch_longitude is not None:
        uzaklik = distance_meters(latitude, longitude, branch_latitude, branch_longitude)
        if uzaklik > FAR_LOCATION_METERS:
            bayraklar.append("far_location")

    if clock_flagged(clock_skew_minutes):
        bayraklar.append("clock_skew")

    if captured_at is not None and received_at - captured_at > timedelta(hours=LATE_SYNC_HOURS):
        bayraklar.append("late_sync")

    return tuple(bayraklar)


@dataclass(frozen=True, slots=True)
class Evidence:
    """Tek bir kanıt dosyası ve ona bağlı bağlam (FR-0606)."""

    id: UUID
    run_id: UUID
    answer_id: UUID
    item_id: UUID
    branch_id: UUID
    user_id: UUID | None
    sha256: str
    content_type: str
    size_bytes: int
    storage_key: str
    created_at: datetime
    status: EvidenceStatus = "pending"
    captured_at: datetime | None = None
    device_reported_at: datetime | None = None
    clock_skew_minutes: int | None = None
    latitude: float | None = None
    longitude: float | None = None
    distance_meters: int | None = None
    device_id: UUID | None = None
    from_gallery: bool = False
    flags: tuple[EvidenceFlag, ...] = ()
    stored_at: datetime | None = None
    stamped_at: datetime | None = None
    stamped_key: str | None = None
    thumbnail_key: str | None = None

    def validated(self) -> Evidence:
        return replace(
            self,
            sha256=check_digest(self.sha256),
            content_type=check_content_type(self.content_type),
            size_bytes=check_size(self.size_bytes),
        )

    @property
    def suspicious(self) -> bool:
        """Panoda "şüpheli kanıt" süzgecinin ölçütü (FR-0615)."""
        return bool(self.flags)

    def stored(self, at: datetime) -> Evidence:
        return replace(self, status="stored", stored_at=at)

    def with_thumbnail(self, thumbnail_key: str) -> Evidence:
        """Küçük resim hazır; durum değişmiyor.

        Damga ayrı adım: yazı tipi olmayan bir sunucuda küçük resim
        üretilebilir ama damga basılamaz (bkz. services/imaging).
        """
        return replace(self, thumbnail_key=thumbnail_key)

    def key_for(self, variant: EvidenceVariant) -> str:
        """İstenen kopyanın anahtarı; hazır değilse **ham dosya**.

        Geri düşmek kasıtlı: damgalanmamış bir kanıt panelde görünmeli.
        Boş kare göstermek, kanıtın yokluğuyla karışırdı.
        """
        if variant == "stamped":
            return self.stamped_key or self.storage_key
        if variant == "thumbnail":
            return self.thumbnail_key or self.storage_key
        return self.storage_key

    def stamped(self, at: datetime, *, stamped_key: str, thumbnail_key: str) -> Evidence:
        return replace(
            self,
            status="stamped",
            stamped_at=at,
            stamped_key=stamped_key,
            thumbnail_key=thumbnail_key,
        )


def storage_key(run_id: UUID, evidence_id: UUID, content_type: str) -> str:
    """Nesne deposundaki yol. Çalıştırmaya göre öbeklenir: silme ve
    saklama süresi (BR-21) çalıştırma düzeyinde işler."""
    uzanti = "png" if content_type == "image/png" else "jpg"
    return f"evidence/{run_id}/{evidence_id}.{uzanti}"


def derived_key(run_id: UUID, evidence_id: UUID, content_type: str, suffix: str) -> str:
    """Türetilmiş kopyanın anahtarı: ham dosyanın yanında, aynı öbekte.

    Ham dosyayla aynı uzantı: damgalı kopya da aynı türde servis edilir,
    istemci tek bir `content_type` ile çalışır.
    """
    uzanti = "png" if content_type == "image/png" else "jpg"
    return f"evidence/{run_id}/{evidence_id}.{suffix}.{uzanti}"


def stamp_text(branch_name: str, user_name: str | None, at: datetime, zone_label: str) -> str:
    """Damganın görünür metni (FR-0606): şube · tarih-saat · kullanıcı."""
    kisi = user_name or "—"
    return f"{branch_name} · {at.strftime('%d.%m.%Y %H:%M')} {zone_label} · {kisi}"
