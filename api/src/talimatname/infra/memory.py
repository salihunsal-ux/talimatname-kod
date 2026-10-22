"""Bellek içi kalıcılık adaptörü — **yalnızca geliştirme ve test**.

Veritabanı ücretsiz bulut PostgreSQL'e taşınana kadar (ADR-0012 md.2)
panel bu adaptörle geliştirilir. Taşındığında yalnızca bu dosyanın
PostgreSQL karşılığı yazılır: servis katmanı ve testler değişmez
(`OrganizationRepository` portu).

Tohum veri, test verisi belgesindeki (06-test/03) **Kahve Durağı** örnek
zinciridir. Gerçek kişi ve müşteri verisi yoktur: adlar uydurmadır ve
şube adları semttir (ADR-0003).
"""

from __future__ import annotations

from datetime import time
from uuid import UUID, uuid5

from talimatname.domain.organization import Branch, Region, Station, uniform_hours
from talimatname.domain.users import RoleAssignment, User
from talimatname.domain.window import BusinessHours

# Tohum kimlikleri sabit: her açılışta aynı id'ler gelsin ki panel
# yenilenince bağlantılar kırılmasın (uuid5, sabit ad alanı).
AD_ALANI = UUID("6f1f6e6a-0a3a-4b1f-9a7d-5f4a2c3d1e00")


def sabit_id(ad: str) -> UUID:
    return uuid5(AD_ALANI, ad)


def _tohum_bolgeler() -> list[Region]:
    return [
        Region(id=sabit_id("bolge:avrupa"), name="Avrupa", code="AVR"),
        Region(id=sabit_id("bolge:anadolu"), name="Anadolu", code="ANA"),
        Region(id=sabit_id("bolge:ege"), name="Ege", code="EGE"),
    ]


def _tohum_subeler() -> list[Branch]:
    standart = uniform_hours(time(8, 0), time(23, 0))
    gec_kapanan = uniform_hours(time(8, 0), time(1, 0))
    pazar_kapali = uniform_hours(time(9, 0), time(21, 0), closed=(6,))

    tanim: list[tuple[str, str, str, dict[int, BusinessHours | None]]] = [
        ("KDK", "Kadıköy", "anadolu", standart),
        ("USK", "Üsküdar", "anadolu", standart),
        ("ATS", "Ataşehir", "anadolu", pazar_kapali),
        ("BSK", "Beşiktaş", "avrupa", gec_kapanan),
        ("BKR", "Bakırköy", "avrupa", standart),
        ("SSL", "Şişli", "avrupa", gec_kapanan),
        ("ALS", "Alsancak", "ege", standart),
        ("BRN", "Bornova", "ege", pazar_kapali),
    ]
    return [
        Branch(
            id=sabit_id(f"sube:{kod}"),
            code=kod,
            name=ad,
            timezone="Europe/Istanbul",
            business_hours=saatler,
            region_id=sabit_id(f"bolge:{bolge}"),
            address=f"{ad}, İstanbul" if bolge != "ege" else f"{ad}, İzmir",
        ).validated()
        for kod, ad, bolge, saatler in tanim
    ]


def _tohum_istasyonlar(subeler: list[Branch]) -> list[Station]:
    sablon: list[tuple[str, str]] = [
        ("Mutfak", "kitchen"),
        ("Bar", "bar"),
        ("Salon", "hall"),
        ("Depo", "storage"),
    ]
    return [
        Station(
            id=sabit_id(f"istasyon:{sube.code}:{ad}"),
            branch_id=sube.id,
            name=ad,
            kind=tur,  # type: ignore[arg-type]
        )
        for sube in subeler
        for ad, tur in sablon
    ]


class MemoryOrganizationRepository:
    """`OrganizationRepository` portunun bellek içi karşılığı."""

    def __init__(self, *, seed: bool = True) -> None:
        self._regions: dict[UUID, Region] = {}
        self._branches: dict[UUID, Branch] = {}
        self._stations: dict[UUID, Station] = {}
        if seed:
            self.load_seed()

    def load_seed(self) -> None:
        for bolge in _tohum_bolgeler():
            self._regions[bolge.id] = bolge
        subeler = _tohum_subeler()
        for sube in subeler:
            self._branches[sube.id] = sube
        for istasyon in _tohum_istasyonlar(subeler):
            self._stations[istasyon.id] = istasyon

    # --- port ---------------------------------------------------------

    def regions(self) -> list[Region]:
        return list(self._regions.values())

    def branches(self) -> list[Branch]:
        return list(self._branches.values())

    def branch(self, branch_id: UUID) -> Branch | None:
        return self._branches.get(branch_id)

    def branch_by_code(self, code: str) -> Branch | None:
        return next((b for b in self._branches.values() if b.code == code), None)

    def save_branch(self, branch: Branch) -> None:
        self._branches[branch.id] = branch

    def stations(self, branch_id: UUID) -> list[Station]:
        return [s for s in self._stations.values() if s.branch_id == branch_id]


def _tohum_kullanicilar() -> list[User]:
    """Örnek personel. Adlar **uydurmadır**; gerçek kişi verisi yoktur (ADR-0003)."""
    tanim: list[tuple[str, str, str | None, list[RoleAssignment]]] = [
        (
            "Cem Yönetici",
            "+905321110001",
            "cem@ornek.test",
            [RoleAssignment("admin")],
        ),
        (
            "Murat Bölge",
            "+905321110002",
            "murat@ornek.test",
            [RoleAssignment("region_manager", sabit_id("bolge:anadolu"))],
        ),
        (
            "Ayşe Şube",
            "+905321110003",
            None,
            [RoleAssignment("branch_manager", sabit_id("sube:KDK"))],
        ),
        (
            "Deniz Şube",
            "+905321110004",
            None,
            [RoleAssignment("branch_manager", sabit_id("sube:BSK"))],
        ),
        (
            "Emre Personel",
            "+905321110005",
            None,
            [RoleAssignment("staff", sabit_id("sube:KDK"))],
        ),
        (
            "Zeynep Personel",
            "+905321110006",
            None,
            [RoleAssignment("staff", sabit_id("sube:KDK"))],
        ),
        (
            "Selin Personel",
            "+905321110007",
            None,
            [RoleAssignment("staff", sabit_id("sube:BSK"))],
        ),
    ]
    return [
        User(
            id=sabit_id(f"kullanici:{telefon}"),
            full_name=ad,
            phone=telefon,
            email=eposta,
            assignments=tuple(atamalar),
        ).validated()
        for ad, telefon, eposta, atamalar in tanim
    ]


class MemoryUserRepository:
    """`UserRepository` portunun bellek içi karşılığı."""

    def __init__(self, *, seed: bool = True) -> None:
        self._users: dict[UUID, User] = {}
        self._mask_counter = 4820  # tohum numarası: maskeleme etiketleri sıradan görünsün
        if seed:
            for kullanici in _tohum_kullanicilar():
                self._users[kullanici.id] = kullanici

    def users(self) -> list[User]:
        return list(self._users.values())

    def user(self, user_id: UUID) -> User | None:
        return self._users.get(user_id)

    def user_by_phone(self, phone: str) -> User | None:
        return next((k for k in self._users.values() if k.phone == phone), None)

    def save_user(self, user: User) -> None:
        self._users[user.id] = user

    def next_mask_counter(self) -> int:
        self._mask_counter += 1
        return self._mask_counter
