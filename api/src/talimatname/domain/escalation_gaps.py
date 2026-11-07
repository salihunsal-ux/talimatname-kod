"""Eskalasyon kime gidiyor, kime gitmiyor (BR-11, FR-0915).

Eskalasyon merdiveni şube müdüründen başlıyor, yoksa bölge müdürüne,
o da yoksa yöneticiye çıkıyor. Merdiven çalışıyor ama **atlanan basamak
yalnızca günlüğe yazılıyordu**: kaçırılan bir liste, şubede müdür
olmadığı için bölge müdürüne gidiyor ve kimse bunun böyle olduğunu
bilmiyor.

Bu modül aynı merdiveni **önceden** yürüyor: "bu şubede uyarı kime
gider" sorusunu, bir şey kaçırılmadan önce cevaplıyor. Panoda
görünmesinin sebebi basit — kimsenin görmediği bir uyarı, uyarı
değildir.

En kötü hâl `hicbiri`: zincirde kimse yok. O zaman kaçırılan liste
hiçbir yere gitmiyor ve bugün bunu yalnızca sunucu günlüğü biliyor.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from talimatname.domain.organization import Branch
from talimatname.domain.users import User

#: Uyarının gerçekte ulaştığı basamak. `hicbiri`: kimseye ulaşmıyor.
ReachedStep = Literal["branch_manager", "region_manager", "admin", "hicbiri"]

STEP_LABELS: dict[ReachedStep, str] = {
    "branch_manager": "Şube müdürü",
    "region_manager": "Bölge müdürü",
    "admin": "Yönetici",
    "hicbiri": "Hiç kimse",
}


@dataclass(frozen=True, slots=True)
class EscalationGap:
    """Bir şubenin eskalasyon merdiveninde atlanan basamak."""

    branch_id: UUID
    branch_code: str
    branch_name: str
    #: Olması gereken ama bulunamayan basamak(lar), merdiven sırasıyla.
    missing: tuple[ReachedStep, ...]
    #: Uyarının gerçekte ulaştığı basamak.
    reached: ReachedStep

    @property
    def critical(self) -> bool:
        """Uyarı hiç kimseye ulaşmıyor: sessiz kayıp."""
        return self.reached == "hicbiri"


def _aktif(users: list[User], role: str, scope_id: UUID | None) -> bool:
    return any(
        k.status == "active"
        and any(
            a.role == role and (scope_id is None or a.scope_id == scope_id) for a in k.assignments
        )
        for k in users
    )


def branch_gap(branch: Branch, users: list[User]) -> EscalationGap | None:
    """Şubenin merdivenini yürür; boşluk yoksa None.

    Merdiven `services/escalation.py` ile **aynı** sırayı izliyor:
    şube müdürü → bölge müdürü → yönetici. İki yer ayrışırsa pano
    yalan söyler, o yüzden ikisi birlikte değişmeli.
    """
    if _aktif(users, "branch_manager", branch.id):
        return None

    eksik: list[ReachedStep] = ["branch_manager"]
    if branch.region_id is not None and _aktif(users, "region_manager", branch.region_id):
        return EscalationGap(
            branch_id=branch.id,
            branch_code=branch.code,
            branch_name=branch.name,
            missing=tuple(eksik),
            reached="region_manager",
        )

    eksik.append("region_manager")
    if _aktif(users, "admin", None):
        return EscalationGap(
            branch_id=branch.id,
            branch_code=branch.code,
            branch_name=branch.name,
            missing=tuple(eksik),
            reached="admin",
        )

    eksik.append("admin")
    return EscalationGap(
        branch_id=branch.id,
        branch_code=branch.code,
        branch_name=branch.name,
        missing=tuple(eksik),
        reached="hicbiri",
    )


def escalation_gaps(branches: list[Branch], users: list[User]) -> list[EscalationGap]:
    """Boşluğu olan şubeler: önce kritik olanlar, sonra şube adına göre."""
    bosluklar = [
        bosluk
        for sube in branches
        if sube.status == "active"
        if (bosluk := branch_gap(sube, users)) is not None
    ]
    return sorted(bosluklar, key=lambda b: (not b.critical, b.branch_name.casefold()))


__all__ = [
    "STEP_LABELS",
    "EscalationGap",
    "ReachedStep",
    "branch_gap",
    "escalation_gaps",
]
