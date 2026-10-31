"""Puan ve sonuç: FR-0306, FR-0307 ve sabit kuralın (FR-0405) saf karşılığı.

Puan **bilgi amaçlıdır**: çalıştırmanın geçip geçmediğini puan değil
kritik madde belirler. Ağırlık ve eşik v1.1'dedir (FR-0306), bu yüzden
burada ağırlık parametresi yok — v1'de her puanlanan madde eşit.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

Result = Literal["passed", "failed"]
AnswerState = Literal["passed", "failed", "not_done", "not_applicable"]

#: Cevabın Türkçe karşılığı (denetim kâğıdı, FR-1213).
ANSWER_STATE_LABELS: dict[str, str] = {
    "passed": "Yapıldı",
    "failed": "Başarısız",
    "not_done": "Yapılamadı",
    "not_applicable": "Uygun değil",
}


@dataclass(frozen=True, slots=True)
class ItemOutcome:
    """Tek maddenin sonucu.

    `scored=False` olan maddeler puana girmez: talimat satırları ve
    "uygun değil" işaretlenen maddeler (ör. fritözü olmayan şube).
    """

    item_id: str
    state: AnswerState
    critical: bool = False
    scored: bool = True


@dataclass(frozen=True, slots=True)
class Evaluation:
    score_percent: int | None
    result: Result
    failed_critical_items: tuple[str, ...]
    scored_item_count: int
    passed_item_count: int


def evaluate(outcomes: Sequence[ItemOutcome]) -> Evaluation:
    """Çalıştırmanın puanını ve sonucunu hesaplar.

    * Puan = geçen / puanlanan × 100, en yakın tam sayıya yuvarlanır.
      Puanlanan madde yoksa puan `None`'dır (sıfır değil: "hesaplanamaz").
    * `not_done` (yapılamadı) puanlanır ve **başarısız** sayılır: iş
      yapılmadıysa liste tam değildir.
    * `not_applicable` puanlanmaz, puanı aşağı çekmez.
    * Kritik madde `passed` değilse çalıştırma puandan bağımsız
      **failed**'dir (FR-0307).
    """
    scored = [o for o in outcomes if o.scored and o.state != "not_applicable"]
    passed = [o for o in scored if o.state == "passed"]
    failed_critical = tuple(o.item_id for o in outcomes if o.critical and o.state != "passed")

    score = round(len(passed) / len(scored) * 100) if scored else None
    result: Result = "failed" if failed_critical or len(passed) != len(scored) else "passed"

    return Evaluation(
        score_percent=score,
        result=result,
        failed_critical_items=failed_critical,
        scored_item_count=len(scored),
        passed_item_count=len(passed),
    )


def requires_evidence(state: AnswerState, critical: bool) -> bool:
    """Sabit kural (FR-0405, BR-06): başarısız cevapta fotoğraf + not zorunlu.

    Kritik olup olmaması kanıt zorunluluğunu değiştirmez; kritik olan
    ayrıca aksiyon açar (bkz. `opens_action`).
    """
    return state in ("failed", "not_done")


def opens_action(state: AnswerState, critical: bool) -> bool:
    """Otomatik aksiyon açılır mı? (FR-0405, BR-08)

    v1'de yalnızca kritik maddenin başarısızlığı aksiyon açar; kritik
    olmayan başarısız madde kanıt ister ama aksiyon açmaz.
    """
    return critical and state in ("failed", "not_done")
