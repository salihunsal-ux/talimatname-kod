"""Günlük kökünün dışarıya çıpalanması (ST-103; FR-1302).

Ad notu: `domain/window.Anchor` **pencere** çıpasıdır (açılışa/kapanışa
göre saat). Buradaki `ChainAnchor` zincirin dışa çıpalanmasıdır. İki
ayrı kavram aynı adı taşımasın diye ayrıldılar.

Hash zinciri **tek tek** değişiklikleri görünür kılar: bir kaydı
düzelten, sonraki bütün özetleri bozar. Görünmez kıldığı tek senaryo
şu: veritabanına yazabilen biri zinciri **baştan** hesaplarsa her şey
yine tutar. Zincirin kendi içinde bunu durduracak bir şey yok —
durduran şey, bir günün kökünün **dışarıda** bir yerde tarihlenmiş
olması.

RFC 3161 zaman damgası tam olarak bunu veriyor: bağımsız bir
otorite "bu 32 bayt şu anda vardı" diye imzalıyor. Damga alındıktan
sonra o ana kadarki tarihi yeniden yazan biri, damgayla tutmayan bir
zincir bırakır.

Üç karar burada:

**Çıpalanan şey zincirin başı.** Her olay bir öncekinin özetini
taşıdığı için **son kaydın özeti bütün geçmişi bağlar**. Günün bütün
kayıtlarını ayrı ayrı damgalamak ne gerekli ne de ucuz.

**Damgalanan değer gerçek bir özettir.** `messageImprint` olarak son
olayın zincir özeti (SHA-256) gönderiliyor. Bu, kanonik gösterimin
özeti; yani otoritenin tarihlediği şey uydurma bir sayı değil,
yeniden hesaplanabilir bir belge.

**Başarısızlık kayda geçer.** Damga alınamazsa o gün için **boş
kayıt** yazılıyor: çıpasız bir gün, çıpalı sanılmasın. Sessizce
atlamak, denetimde "o gün neden yok" sorusunu cevapsız bırakırdı.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from talimatname.domain.validation import ValidationError

AnchorState = Literal["ok", "failed"]

ANCHOR_STATE_LABELS: dict[str, str] = {
    "ok": "Damgalandı",
    "failed": "Damga alınamadı",
}

#: Çıpalama saati (yerel). Gün dönünce önceki günün bütün kayıtları
#: yerinde olsun diye gecenin sonunda (FR-1302).
ANCHOR_HOUR = 4

#: Bir günde en çok kaç deneme. Ağ hatası bir sonraki turda düzelebilir;
#: üçüncüden sonra ertesi günü beklemek, zamanlayıcıyı dakikada bir
#: damga sunucusuna yüklenen bir istemciye çevirmemek için.
MAX_DAILY_ATTEMPTS = 3


@dataclass(frozen=True, slots=True)
class ChainAnchor:
    """Bir günün zincir kökü ve onun dış damgası."""

    id: UUID
    created_at: datetime
    sequence: int
    chain_hash: str
    state: AnchorState = "ok"
    token: bytes | None = None
    stamped_at: datetime | None = None
    tsa_name: str | None = None
    serial: str | None = None
    error: str | None = None

    def validated(self) -> ChainAnchor:
        if self.sequence < 1:
            raise ValidationError("sequence", "Sıra 1'den başlar")
        if len(self.chain_hash) != 64:
            raise ValidationError("chain_hash", "Zincir özeti 64 onaltılık basamak olmalı")
        if self.state == "ok" and not self.token:
            raise ValidationError("token", "Başarılı çıpada damga bulunmalı")
        if self.created_at.tzinfo is None:
            raise ValidationError("created_at", "Zaman saat dilimli olmalı")
        return self

    @property
    def state_label(self) -> str:
        return ANCHOR_STATE_LABELS[self.state]

    @property
    def digest(self) -> bytes:
        """Damgaya gönderilen bayt dizisi: zincir özetinin kendisi."""
        return bytes.fromhex(self.chain_hash)


def due(local_now: datetime, attempts_today: int, has_anchor_today: bool) -> bool:
    """Bugünün çıpası şimdi alınmalı mı? (FR-1302)

    Saat **geçmiş olabilir**: zamanlayıcı 04:00'te kapalıysa, açıldığı
    anda alınır. "Tam 04:00'te değilse hiç" demek, sunucunun bir saat
    kapalı kalmasını çıpasız bir güne çevirirdi.
    """
    if has_anchor_today:
        return False
    if attempts_today >= MAX_DAILY_ATTEMPTS:
        return False
    return local_now.hour >= ANCHOR_HOUR


def local_day(moment: datetime, zone: str) -> date:
    """Bir anın **yerel** günü. Kayıtlar UTC, çıpa ise bir günün çıpası.

    Gün yerel takvimde başlıyor: 03:00'te alınan bir damga Türkiye'de
    hâlâ önceki günün işidir, UTC'de ertesi günün.
    """
    return moment.astimezone(ZoneInfo(zone)).date()


__all__ = [
    "ANCHOR_HOUR",
    "ANCHOR_STATE_LABELS",
    "MAX_DAILY_ATTEMPTS",
    "AnchorState",
    "ChainAnchor",
    "due",
    "local_day",
]
