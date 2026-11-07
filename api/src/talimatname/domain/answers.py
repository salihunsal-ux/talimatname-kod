"""Cevap ve gönderim (CAP-06; FR-0602, FR-0607, FR-0521, BR-13).

Bu modül **mobilin sunucu tarafıdır** ve ADR-0013'ün birinci devir
sözleşmesini taşır: cevabın kimliği **cihazda** üretilir, yazma
idempotenttir. Çevrimdışı kuyruk aynı cevabı birden çok kez
gönderebilir; ikinci gönderim yeni kayıt açmaz, var olanı günceller.

İki kural daha burada:

* **Cihaz saati kaydedilir, kullanılmaz** (BR-13). "Zamanında mı"
  kararını sunucu kendi saatiyle verir; cihazın saati yalnızca sapma
  olarak saklanır ve kanıt bayrağına dönüşür.
* **Çalıştırma kilidi** (FR-0521): "biri tamamlasın" listelerinde ilk
  açan alır; kilidi olmayan kullanıcı yazamaz.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from math import isfinite
from typing import Any, Literal
from uuid import UUID

from talimatname.domain.errors import RunLocked
from talimatname.domain.scoring import AnswerState, ItemOutcome
from talimatname.domain.sync import NotDoneReason, check_not_done_reason, clock_flagged
from talimatname.domain.templates import RANGED, ChoiceOption, Item, ItemType
from talimatname.domain.validation import ValidationError

#: Kilit bu süre yenilenmezse düşer: cihaz kapanırsa liste kilitli kalmasın.
LOCK_MINUTES = 30


@dataclass(frozen=True, slots=True)
class Answer:
    """Tek maddenin cevabı. `id` **cihazda** üretilir (idempotency anahtarı)."""

    id: UUID
    run_id: UUID
    item_id: UUID
    state: AnswerState
    value: Any = None
    note: str | None = None
    user_id: UUID | None = None
    device_id: UUID | None = None
    answered_at: datetime | None = None
    device_reported_at: datetime | None = None
    clock_skew_minutes: int | None = None
    evidence_count: int = 0
    not_done_reason: NotDoneReason | None = None

    def validated(self) -> Answer:
        if self.state not in ("passed", "failed", "not_done", "not_applicable"):
            raise ValidationError("state", f"Bilinmeyen cevap durumu: {self.state}")
        if self.note is not None and not self.note.strip():
            raise ValidationError("note", "Not boş bırakılamaz")
        not_temiz = " ".join(self.note.split()) if self.note else None
        return replace(
            self,
            note=not_temiz,
            not_done_reason=check_not_done_reason(self.state, self.not_done_reason, not_temiz),
        )

    @property
    def clock_flagged(self) -> bool:
        return clock_flagged(self.clock_skew_minutes)


def clock_skew(server_now: datetime, device_time: datetime | None) -> int | None:
    """Cihaz saati sapması (dakika). Kaydedilir ama karar için kullanılmaz."""
    if device_time is None:
        return None
    return round((device_time - server_now).total_seconds() / 60)


@dataclass(frozen=True, slots=True)
class RunLock:
    """Çalıştırma kilidi: ilk açan alır (FR-0521, BR-26)."""

    user_id: UUID
    acquired_at: datetime
    renewed_at: datetime

    def expired(self, now: datetime) -> bool:
        return now - self.renewed_at > timedelta(minutes=LOCK_MINUTES)

    def held_by(self, user_id: UUID, now: datetime) -> bool:
        return self.user_id == user_id and not self.expired(now)


def ensure_writable(lock: RunLock | None, user_id: UUID | None, now: datetime) -> RunLock | None:
    """Yazma öncesi kilit denetimi; gerekiyorsa kilidi tazeler.

    Kilit yoksa ya da süresi dolmuşsa yazan kullanıcı kilidi alır.
    Kullanıcı bilinmiyorsa (panel/araç) kilit aranmaz.
    """
    if user_id is None:
        return lock
    if lock is None or lock.expired(now):
        return RunLock(user_id=user_id, acquired_at=now, renewed_at=now)
    if lock.user_id != user_id:
        # Alan hatası, doğrulama hatası değil: istemci "istek bozuk" ile
        # "listeyi başkası yapıyor"u ayırt edebilsin (409, kendi kodu).
        raise RunLocked(f"Kilit sahibi: {lock.user_id}", holder=str(lock.user_id))
    return replace(lock, renewed_at=now)


def outcomes(
    answers: list[Answer],
    item_meta: dict[UUID, tuple[bool, bool]],
) -> list[ItemOutcome]:
    """Cevapları puanlama girdisine çevirir.

    `item_meta`: madde id → (kritik mi, puanlanır mı). Şablondan gelir;
    cevapta tutulmaz, çünkü şablon sürümü değişmez ve tek kaynaktır.
    """
    sonuc: list[ItemOutcome] = []
    for cevap in answers:
        kritik, puanlanir = item_meta.get(cevap.item_id, (False, True))
        sonuc.append(
            ItemOutcome(
                item_id=str(cevap.item_id),
                state=cevap.state,
                critical=kritik,
                scored=puanlanir,
            )
        )
    return sonuc


MissingKind = Literal["unanswered", "evidence", "note"]


@dataclass(frozen=True, slots=True)
class Missing:
    """Gönderimi engelleyen eksik (FR-0607, FR-0405)."""

    item_id: UUID
    title: str
    kind: MissingKind


def submission_blockers(
    *,
    items: list[tuple[UUID, str, bool, bool, bool]],
    answers: dict[UUID, Answer],
) -> list[Missing]:
    """Gönderime engel eksikler.

    `items`: (id, başlık, zorunlu, kanıt_zorunlu, puanlanır).

    * Zorunlu madde cevapsız olamaz.
    * Başarısız ve yapılamadı cevaplarında **fotoğraf ve not** zorunlu
      (sabit kural, FR-0405/BR-06) — kanıt zorunlu işaretinden bağımsız.
    """
    eksikler: list[Missing] = []
    for item_id, baslik, zorunlu, kanit_zorunlu, _ in items:
        cevap = answers.get(item_id)
        if cevap is None:
            if zorunlu:
                eksikler.append(Missing(item_id, baslik, "unanswered"))
            continue
        basarisiz = cevap.state in ("failed", "not_done")
        if (kanit_zorunlu or basarisiz) and cevap.evidence_count == 0:
            eksikler.append(Missing(item_id, baslik, "evidence"))
        if basarisiz and not cevap.note:
            eksikler.append(Missing(item_id, baslik, "note"))
    return eksikler


#: Sonucu **sunucunun** hesapladığı türler: ölçüm ve seçim. Kalanlarda
#: (onay, fotoğraf, metin) sonucu kişi beyan eder; beyanı doğrulayacak
#: bir değer yok.
DECIDED: frozenset[ItemType] = RANGED | frozenset({"choice"})


def resolve_answer(item: Item, *, state: str, value: Any) -> tuple[AnswerState, Any]:
    """Cevabın durumunu ve değerini **sunucuda** kesinleştirir (BR-06).

    İstemci sonucu da hesaplayıp gönderiyor — anında geri bildirim
    için gerekli. Ama bu hesabı yapan **tek** yer olamaz: 0–4 °C
    aralıklı maddeye `99` yazıp "geçti" diyen bir istemci (hatalı
    sürüm, eski çevrimdışı kuyruk ya da elle kurulmuş istek) aksi
    halde %100 puanlı bir liste üretir ve denetim izi yalan söyler
    (bağımsız test turu B02). Ölçülebilir maddede sonuç şablon
    sürümünden ve değerden çıkar, istemcinin iddiasından değil.

    Şablon sürümü çalıştırmaya sabitlendiği için bu hesap, cevap
    aylar sonra kuyruktan gelse de o günün sınırlarıyla yapılır.

    `not_done` ve `not_applicable` birer **beyandır**, ölçüm değil:
    oldukları gibi kalır, yanlarındaki ölçüm değeri düşer — "yapamadım"
    diyen cevapta duran bir sıcaklık okuyanı yanıltır. Sebep denetimi
    `check_not_done_reason` içinde.
    """
    if item.type == "instruction":
        # FR-0306: talimat satırı bilgi verir, cevap beklemez.
        raise ValidationError("item_id", "Talimat satırı cevaplanmaz")
    if state == "not_done":
        return "not_done", None
    if state == "not_applicable":
        return "not_applicable", None
    if state not in ("passed", "failed"):
        raise ValidationError("state", f"Bilinmeyen cevap durumu: {state}")
    beyan: AnswerState = "passed" if state == "passed" else "failed"

    if item.type in RANGED:
        sayi = _olcum(value)
        if item.min_value is None or item.max_value is None:
            # Yayın doğrulaması sınırsız aralıklı maddeyi engelliyor
            # (Item.issues). Yine de böyle bir sürüm varsa ölçüm
            # saklanır, sonuç beyandan kalır: uyduracak sınır yok.
            return beyan, sayi
        icinde = item.min_value <= sayi <= item.max_value
        return ("passed" if icinde else "failed"), sayi

    if item.type == "choice":
        secenek = _secenek(value, item)
        return ("passed" if secenek.passing else "failed"), secenek.label

    if item.type == "text":
        return beyan, _metin(value)

    # confirm / photo: değer taşımaz.
    return beyan, None


def _olcum(value: Any) -> float | int:
    """Ölçüm değerini sayıya çevirir; çeviremezse reddeder."""
    if isinstance(value, bool) or value is None:
        raise ValidationError("value", "Ölçüm değeri girilmeli")
    if isinstance(value, int | float):
        sayi = float(value)
    elif isinstance(value, str):
        # Çevrimdışı istemci ondalığı virgülle gönderebilir.
        try:
            sayi = float(value.strip().replace(",", ".", 1))
        except ValueError:
            raise ValidationError("value", "Ölçüm bir sayı olmalı") from None
    else:
        raise ValidationError("value", "Ölçüm bir sayı olmalı")
    if not isfinite(sayi):
        raise ValidationError("value", "Ölçüm sonlu bir sayı olmalı")
    # Tam sayı tam kalsın: "6 °C" okunur, "6.0 °C" uydurma hassasiyet.
    return int(sayi) if sayi.is_integer() else sayi


def _secenek(value: Any, item: Item) -> ChoiceOption:
    """Seçimi şablondaki seçeneğe bağlar; listede yoksa reddeder."""
    if isinstance(value, str):
        aranan = " ".join(value.split())
        for secenek in item.options:
            if secenek.label == aranan:
                return secenek
    raise ValidationError("value", "Seçenek şablonda yok")


def _metin(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError("value", "Metin cevabı boş olamaz")
    return " ".join(value.split())
