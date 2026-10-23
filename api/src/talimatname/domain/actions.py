"""Aksiyon: açık/kapalı iş kaydı (CAP-09; FR-0901…0915, BR-08, BR-10).

v1'de aksiyon **iki durumludur**: açık ya da kapalı. Durum makinesi,
yorum dizisi ve onaylı kapanış v1.1'dedir (ADR-0008). Bunun yerine üç
şey var ve üçü de zorunlu:

* **Kaynak** — aksiyon kendiliğinden doğmaz: kaçırılan çalıştırma,
  kritik başarısızlık, yapılamadı ya da bildirilen sorun.
* **Vade** — önceliğe göre sabit (BR-10): kritik 4 saat, yüksek 24,
  normal 72. v1'de ayarlanabilir değil.
* **Kapanış notu** — not olmadan kapatılamaz (FR-0904). "Kapattım"
  demek yetmiyor, ne yapıldığı yazılıyor.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import Literal
from uuid import UUID, uuid5

from talimatname.domain.validation import ValidationError, clean_name

Priority = Literal["critical", "high", "normal"]
ActionStatus = Literal["open", "closed"]
ActionSource = Literal["missed_run", "critical_item", "not_done", "issue", "manual"]

#: Önceliğe göre sabit vade (BR-10). Saat cinsinden.
DUE_HOURS: dict[Priority, int] = {"critical": 4, "high": 24, "normal": 72}

PRIORITY_LABELS: dict[Priority, str] = {
    "critical": "Kritik",
    "high": "Yüksek",
    "normal": "Normal",
}

SOURCE_LABELS: dict[ActionSource, str] = {
    "missed_run": "Kaçırılan liste",
    "critical_item": "Kritik madde",
    "not_done": "Yapılamadı",
    "issue": "Sorun bildirimi",
    "manual": "Elle açıldı",
}

#: Kaynaktan doğan aksiyonun kimliği sabittir: aynı kaynak iki aksiyon
#: açmaz (FR-0903 idempotent oluşturma).
ACTION_NAMESPACE = UUID("8b2e4d1a-6c37-4f90-9a52-1d8e3b7c4f22")


def action_id(source: ActionSource, source_id: UUID) -> UUID:
    return uuid5(ACTION_NAMESPACE, f"{source}:{source_id}")


def due_at(priority: Priority, opened_at: datetime) -> datetime:
    return opened_at + timedelta(hours=DUE_HOURS[priority])


@dataclass(frozen=True, slots=True)
class Action:
    id: UUID
    branch_id: UUID
    title: str
    source: ActionSource
    priority: Priority
    opened_at: datetime
    due_at: datetime
    source_id: UUID | None = None
    description: str | None = None
    assignee_user_id: UUID | None = None
    status: ActionStatus = "open"
    closed_at: datetime | None = None
    closed_by: UUID | None = None
    close_note: str | None = None

    def validated(self) -> Action:
        if self.priority not in DUE_HOURS:
            raise ValidationError("priority", f"Bilinmeyen öncelik: {self.priority}")
        if self.source != "manual" and self.source_id is None:
            raise ValidationError("source_id", "Kaynaktan doğan aksiyonun kaynağı belirtilmeli")
        return replace(self, title=clean_name(self.title, "title", max_length=160))

    def overdue(self, now: datetime) -> bool:
        """Vadesi geçti mi? Kapalı aksiyon gecikmiş sayılmaz."""
        return self.status == "open" and now > self.due_at

    def remaining_hours(self, now: datetime) -> float:
        return (self.due_at - now).total_seconds() / 3600

    def close(self, note: str, at: datetime, by: UUID | None = None) -> Action:
        """Kapanış notu zorunlu (FR-0904): ne yapıldığı yazılmadan kapanmaz."""
        temiz = " ".join(note.split())
        if len(temiz) < 3:
            raise ValidationError("close_note", "Kapanış notu yazılmalı")
        return replace(
            self,
            status="closed",
            closed_at=at,
            closed_by=by,
            close_note=temiz,
        )


def from_missed_run(
    *,
    run_id: UUID,
    branch_id: UUID,
    plan_name: str,
    business_day: object,
    now: datetime,
) -> Action:
    """Kaçırılan çalıştırmadan doğan aksiyon (FR-0902, BR-10: yüksek öncelik).

    Kimlik çalıştırmadan türetildiği için zamanlayıcı kaç kez koşarsa
    koşsun tek aksiyon açılır.
    """
    return Action(
        id=action_id("missed_run", run_id),
        branch_id=branch_id,
        title=f"{plan_name} yapılmadı ({business_day})",
        source="missed_run",
        source_id=run_id,
        priority="high",
        opened_at=now,
        due_at=due_at("high", now),
        description="Liste penceresi ve tolerans süresi içinde tamamlanmadı.",
    ).validated()
