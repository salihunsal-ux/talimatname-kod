"""Organizasyon kullanım senaryoları (ST-002, ST-007).

Servis katmanı **kalıcılığı tanımaz**: `OrganizationRepository` arayüzünü
kullanır. Bugün bellek içi adaptörle çalışıyor; veritabanı geldiğinde
(ücretsiz bulut PostgreSQL, ADR-0012 md.2) yalnızca adaptör değişir,
buradaki kurallar ve testler aynen kalır.

Birden çok satıra bakan kurallar burada: kod benzersizliği, bölgenin
varlığı, pasifleştirmenin sonuçları.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Protocol
from uuid import UUID, uuid4

from talimatname.domain.errors import DomainError, ErrorKind
from talimatname.domain.organization import Branch, Region, Station
from talimatname.domain.users import User, can_access


class BranchCodeTaken(DomainError):
    code = "sube-kodu-kullanimda"
    title = "Bu şube kodu zaten var"
    kind: ErrorKind = "conflict"


class BranchNotFound(DomainError):
    code = "sube-bulunamadi"
    title = "Şube bulunamadı"
    kind: ErrorKind = "not_found"


class RegionNotFound(DomainError):
    code = "bolge-bulunamadi"
    title = "Bölge bulunamadı"
    kind: ErrorKind = "not_found"


@dataclass(frozen=True, slots=True)
class RegionNode:
    """Ağacın bir düğümü: bölge ve altındaki şubeler. Bölgesiz şubeler `id=None`."""

    id: UUID | None
    name: str
    branches: list[Branch]


class OrganizationRepository(Protocol):
    """Kalıcılık arayüzü (port). Adaptörler: bellek içi, PostgreSQL."""

    def regions(self) -> list[Region]: ...

    def branches(self) -> list[Branch]: ...

    def branch(self, branch_id: UUID) -> Branch | None: ...

    def branch_by_code(self, code: str) -> Branch | None: ...

    def save_branch(self, branch: Branch) -> None: ...

    def save_region(self, region: Region) -> None: ...

    def stations(self, branch_id: UUID) -> list[Station]: ...


class OrganizationService:
    def __init__(self, repo: OrganizationRepository) -> None:
        self._repo = repo

    # --- okuma -------------------------------------------------------

    def tree(self, *, include_inactive: bool = False) -> list[RegionNode]:
        """Bölge → şube ağacı. Bölgesiz şubeler sonda "Bölgesiz" altında.

        Panel ağacı tek çağrıda alır: 25–100 şubede sayfalama yapmaya
        değmez, ama 1000 şubede değer — o eşik geldiğinde burası değişir.
        """
        branches = [b for b in self._repo.branches() if include_inactive or b.status == "active"]
        by_region: dict[UUID | None, list[Branch]] = {}
        for branch in branches:
            by_region.setdefault(branch.region_id, []).append(branch)

        agac = [
            RegionNode(
                id=region.id,
                name=region.name,
                branches=self._sorted(by_region.get(region.id, [])),
            )
            for region in sorted(self._repo.regions(), key=lambda r: r.name)
        ]
        bolgesiz = by_region.get(None, [])
        if bolgesiz:
            agac.append(RegionNode(id=None, name="Bölgesiz", branches=self._sorted(bolgesiz)))
        return agac

    @staticmethod
    def _sorted(branches: list[Branch]) -> list[Branch]:
        return sorted(branches, key=lambda b: b.name.casefold())

    def by_code(self, code: str) -> Branch | None:
        """Koda göre şube: Excel içe aktarmada eşleştirme anahtarı (FR-0105)."""
        return self._repo.branch_by_code(code.strip().upper())

    def get(self, branch_id: UUID) -> Branch:
        branch = self._repo.branch(branch_id)
        if branch is None:
            raise BranchNotFound(f"Şube id: {branch_id}")
        return branch

    def stations(self, branch_id: UUID) -> list[Station]:
        self.get(branch_id)
        return sorted(self._repo.stations(branch_id), key=lambda s: s.name.casefold())

    # --- yazma -------------------------------------------------------

    def create_branch(self, branch: Branch) -> Branch:
        hazir = branch.validated()
        self._check_region(hazir.region_id)
        if self._repo.branch_by_code(hazir.code) is not None:
            raise BranchCodeTaken(f"Kod: {hazir.code}")
        kayit = replace(hazir, id=hazir.id or uuid4())
        self._repo.save_branch(kayit)
        return kayit

    def update_branch(self, branch_id: UUID, **degisiklik: Any) -> Branch:
        mevcut = self.get(branch_id)
        guncel = replace(mevcut, **degisiklik).validated()
        self._check_region(guncel.region_id)
        if guncel.code != mevcut.code:
            cakisan = self._repo.branch_by_code(guncel.code)
            if cakisan is not None and cakisan.id != branch_id:
                raise BranchCodeTaken(f"Kod: {guncel.code}")
        self._repo.save_branch(guncel)
        return guncel

    def set_status(self, branch_id: UUID, status: str) -> Branch:
        """Pasifleştirme silme değildir: geçmiş çalıştırmalar ve kanıtlar durur.

        Gelecekteki çalıştırmaların üretimi planlama tarafında durur
        (FR-0515); burada yalnızca şubenin durumu değişir.
        """
        if status not in ("active", "inactive"):
            raise DomainError(f"Bilinmeyen durum: {status}")
        return self.update_branch(branch_id, status=status)

    def _check_region(self, region_id: UUID | None) -> None:
        if region_id is None:
            return
        if all(r.id != region_id for r in self._repo.regions()):
            raise RegionNotFound(f"Bölge id: {region_id}")


def erisilebilir_sube_idleri(kullanici: User, org: OrganizationService) -> set[UUID]:
    """Kullanıcının kapsamındaki şube kimlikleri — liste süzgeçlerinin temeli.

    Sunum katmanındaydı; arka planda rapor üreten işçi de aynı kuralı
    uygulamak zorunda olduğu için buraya taşındı (FR-1217). İki ayrı
    kapsam hesabı, arka plandaki çıktının kullanıcının göremeyeceği
    şubeleri taşıması demek olurdu.
    """
    return {
        sube.id
        for dugum in org.tree(include_inactive=True)
        for sube in dugum.branches
        if can_access(kullanici, sube)
    }


def sube_kodlari(org: OrganizationService) -> dict[UUID, str]:
    """Şube kimliği → kod. Kâğıtta yer dar, kod yazılıyor.

    Kapalı şubeler de alınıyor: geçmiş dönemin ölçümü kapanmış bir
    şubeye ait olabilir ve kod yerine tire basmak kaydı okunamaz kılar.
    """
    return {
        sube.id: sube.code for dugum in org.tree(include_inactive=True) for sube in dugum.branches
    }
