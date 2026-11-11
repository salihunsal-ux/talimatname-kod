"""Aksiyon: açık/kapalı iş kaydı (CAP-09; FR-0901…0915, BR-08, BR-10).

v1'de aksiyon **iki durumludur**: açık ya da kapalı. Durum makinesi,
yorum dizisi ve onaylı kapanış v1.1'dedir (ADR-0008). Bunun yerine üç
şey var ve üçü de zorunlu:

* **Kaynak** — aksiyon kendiliğinden doğmaz: kaçırılan çalıştırma,
  kritik başarısızlık, **takip işaretli başarısız madde**, yapılamadı
  ya da bildirilen sorun.
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
ActionSource = Literal["missed_run", "critical_item", "failed_item", "not_done", "issue", "manual"]

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
    "failed_item": "Başarısız madde",
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


def critical_item_source(run_id: UUID, item_id: UUID) -> UUID:
    """Kritik madde aksiyonunun kaynak kimliği: (çalıştırma, madde).

    Cevabın kimliği **cihazda** üretiliyor ve aynı madde için
    değişebilir; aksiyonun kimliği ondan türetilirse çevrimdışı
    senkte kopya aksiyon doğar. Çalıştırma + madde sabittir.
    """
    return uuid5(ACTION_NAMESPACE, f"kritik:{run_id}:{item_id}")


def from_critical_item(
    *,
    run_id: UUID,
    item_id: UUID,
    branch_id: UUID,
    item_title: str,
    plan_name: str,
    now: datetime,
) -> Action:
    """Başarısız kritik maddeden doğan aksiyon (FR-0405, BR-08).

    Kritik öncelik, 4 saat vade (BR-10). Kritik olmayan başarısız
    madde kanıt ister ama aksiyon açmaz.
    """
    kaynak = critical_item_source(run_id, item_id)
    return Action(
        id=action_id("critical_item", kaynak),
        branch_id=branch_id,
        title=f"Kritik madde başarısız: {item_title}",
        source="critical_item",
        source_id=kaynak,
        priority="critical",
        opened_at=now,
        due_at=due_at("critical", now),
        description=f"{plan_name} listesinde kritik madde geçmedi.",
    ).validated()


def failed_item_source(run_id: UUID, item_id: UUID) -> UUID:
    """Takip işaretli başarısız maddenin kaynak kimliği: (çalıştırma, madde)."""
    return uuid5(ACTION_NAMESPACE, f"basarisiz:{run_id}:{item_id}")


def from_failed_item(
    *,
    run_id: UUID,
    item_id: UUID,
    branch_id: UUID,
    item_title: str,
    plan_name: str,
    priority: Priority,
    now: datetime,
) -> Action:
    """Şablonda takip işaretli, **kritik olmayan** başarısız madde (BR-10).

    Kritik madde kendi kuralıyla zaten aksiyon açıyor. Bu, aradaki
    boşluk içindi: denetimde "ilaçlama belgesinin süresi dolmuş"
    kritik değildir — çalıştırmayı başarısız yapmaz (BR-07) — ama
    takip edilmezse kayda geçip kimseye gitmez. Önceliği **şablon**
    söylüyor, vade ondan türüyor.
    """
    kaynak = failed_item_source(run_id, item_id)
    return Action(
        id=action_id("failed_item", kaynak),
        branch_id=branch_id,
        title=f"Denetim bulgusu: {item_title}",
        source="failed_item",
        source_id=kaynak,
        priority=priority,
        opened_at=now,
        due_at=due_at(priority, now),
        description=f"{plan_name} listesinde bu madde geçmedi; takip işaretli.",
    ).validated()


def not_done_source(run_id: UUID, item_id: UUID) -> UUID:
    """Yapılamadı aksiyonunun kaynak kimliği: (çalıştırma, madde).

    Kritik maddedeki gibi: cevabın kimliği cihazda üretildiği için
    ondan türetilemez, yoksa senkte kopya aksiyon doğar.
    """
    return uuid5(ACTION_NAMESPACE, f"yapilamadi:{run_id}:{item_id}")


def from_not_done(
    *,
    run_id: UUID,
    item_id: UUID,
    branch_id: UUID,
    item_title: str,
    plan_name: str,
    reason_label: str | None,
    now: datetime,
) -> Action:
    """'Yapılamadı' cevabından doğan aksiyon (BR-10: orta, 72 sa).

    Yapılamayan iş kendi kendine yapılmıyor: sebebi (malzeme yok,
    ekipman arızalı) merkezde biri çözmeli. Tetik yazılmamıştı,
    cevap sebebiyle kayda giriyor ama kimseye iş düşmüyordu
    (bağımsız test turu B05).
    """
    kaynak = not_done_source(run_id, item_id)
    sebep = f" Sebep: {reason_label}." if reason_label else ""
    return Action(
        id=action_id("not_done", kaynak),
        branch_id=branch_id,
        title=f"Yapılamadı: {item_title}",
        source="not_done",
        source_id=kaynak,
        priority="normal",
        opened_at=now,
        due_at=due_at("normal", now),
        description=f"{plan_name} listesinde madde yapılamadı.{sebep}",
    ).validated()


def missed_run_source(branch_id: UUID, plan_id: UUID, business_day: object) -> UUID:
    """Kaçırma aksiyonunun kaynak kimliği: (şube, plan, iş günü).

    Eskiden **çalıştırmadan** türüyordu, yani her kaçırılan pencere ayrı
    bir aksiyon açıyordu. Günde iki listede bu katlanılabilirdi; saatlik
    listede değil: bir öğleden sonrayı atlayan şube tek bir ihmal için
    4–6 aksiyon üretiyor ve aksiyon listesi okunamaz hâle geliyor.
    Okunmayan liste, liste değildir.

    Gün bazında grupluyoruz: "bugün 3 kez yapılmadı" bir satır. Sayı
    arttıkça aksiyon çoğalmıyor, başlığı güncelleniyor.
    """
    return uuid5(ACTION_NAMESPACE, f"kacirildi:{branch_id}:{plan_id}:{business_day}")


def from_missed_runs(
    *,
    branch_id: UUID,
    plan_id: UUID,
    plan_name: str,
    business_day: object,
    count: int,
    now: datetime,
) -> Action:
    """Bir şubenin bir gündeki kaçırılan çalıştırmaları (FR-0902, BR-10).

    Öncelik yüksek, vade **ilk** kaçırmadan sayılır: aynı gün ikinci
    kaçırma vadeyi uzatmamalı.
    """
    kaynak = missed_run_source(branch_id, plan_id, business_day)
    baslik = (
        f"{plan_name} yapılmadı ({business_day})"
        if count <= 1
        else f"{plan_name}: {business_day} günü {count} kez yapılmadı"
    )
    return Action(
        id=action_id("missed_run", kaynak),
        branch_id=branch_id,
        title=baslik,
        source="missed_run",
        source_id=kaynak,
        priority="high",
        opened_at=now,
        due_at=due_at("high", now),
        description="Liste penceresi ve tolerans süresi içinde tamamlanmadı.",
    ).validated()
