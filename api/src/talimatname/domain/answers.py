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
from typing import Any, Literal
from uuid import UUID

from talimatname.domain.errors import RunLocked
from talimatname.domain.scoring import AnswerState, ItemOutcome
from talimatname.domain.sync import NotDoneReason, check_not_done_reason, clock_flagged
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
