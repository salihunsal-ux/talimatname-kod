"""Kullanıcı, rol ve kapsam (CAP-02; FR-0107…0110, FR-0205).

Yetki modeli iki parçadır ve ikisi de burada saf olarak durur:

* **Rol** ne yapabileceğini söyler (Yönetici, Bölge müdürü, Şube müdürü,
  Personel).
* **Kapsam** nerede yapabileceğini söyler (hesap, bölge, şube).

`can_access` bu ikisinin birleşimidir ve yetki denetiminin tek kaynağıdır:
uç noktalar bu fonksiyonu çağırır, kendi `if`'ini yazmaz (TC-006, TC-010).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Literal
from uuid import UUID

from talimatname.domain.organization import Branch
from talimatname.domain.validation import ValidationError, clean_name

Role = Literal["admin", "region_manager", "branch_manager", "staff"]
ScopeType = Literal["tenant", "region", "branch"]
UserStatus = Literal["active", "inactive", "masked"]

ROLES: tuple[Role, ...] = ("admin", "region_manager", "branch_manager", "staff")

# Rolün hangi kapsamda anlamlı olduğu. Yönetici hesabın tamamını görür;
# şube müdürü ve personel bir şubeye bağlıdır.
ROLE_SCOPE: dict[Role, ScopeType] = {
    "admin": "tenant",
    "region_manager": "region",
    "branch_manager": "branch",
    "staff": "branch",
}

ROLE_LABELS: dict[Role, str] = {
    "admin": "Yönetici",
    "region_manager": "Bölge müdürü",
    "branch_manager": "Şube müdürü",
    "staff": "Personel",
}

E164 = re.compile(r"^\+[1-9]\d{7,14}$")


def normalize_phone(value: str, *, default_country: str = "+90") -> str:
    """Telefonu E.164'e çevirir: "0532 123 45 67" → "+905321234567".

    Türkiye varsayılan; başında "+" olan numara olduğu gibi kabul edilir
    (zincirlerin yurt dışı şubeleri olabiliyor).
    """
    temiz = re.sub(r"[\s().-]", "", value.strip())
    if temiz.startswith("00"):
        temiz = "+" + temiz[2:]
    elif temiz.startswith("0"):
        temiz = default_country + temiz[1:]
    elif not temiz.startswith("+"):
        temiz = default_country + temiz
    if not E164.match(temiz):
        raise ValidationError("phone", "Geçerli bir telefon numarası girin")
    return temiz


@dataclass(frozen=True, slots=True)
class RoleAssignment:
    """Rol + kapsam. Kapsam türü rolden belirlenir, ayrıca girilmez."""

    role: Role
    scope_id: UUID | None = None

    @property
    def scope_type(self) -> ScopeType:
        return ROLE_SCOPE[self.role]

    def validated(self) -> RoleAssignment:
        if self.role not in ROLE_SCOPE:
            raise ValidationError("role", f"Bilinmeyen rol: {self.role}")
        if self.scope_type == "tenant" and self.scope_id is not None:
            raise ValidationError("scope_id", "Yönetici rolü hesabın tamamını kapsar")
        if self.scope_type != "tenant" and self.scope_id is None:
            raise ValidationError("scope_id", f"{ROLE_LABELS[self.role]} için kapsam seçilmeli")
        return self


@dataclass(frozen=True, slots=True)
class User:
    id: UUID
    full_name: str
    phone: str | None
    assignments: tuple[RoleAssignment, ...] = ()
    email: str | None = None
    status: UserStatus = "active"
    invited_at: datetime | None = None
    masked_at: datetime | None = None
    language: str = "tr"
    pin_set: bool = field(default=False)

    def validated(self) -> User:
        if self.status == "masked":
            return self
        if not self.assignments:
            raise ValidationError("assignments", "En az bir rol verilmeli")
        if self.phone is None:
            raise ValidationError("phone", "Telefon zorunlu")
        if self.email is not None and "@" not in self.email:
            raise ValidationError("email", "Geçerli bir e-posta girin")
        return replace(
            self,
            full_name=clean_name(self.full_name, "full_name"),
            phone=normalize_phone(self.phone),
            email=self.email.strip().lower() if self.email else None,
            assignments=tuple(a.validated() for a in self.assignments),
        )

    @property
    def roles(self) -> tuple[Role, ...]:
        return tuple(dict.fromkeys(a.role for a in self.assignments))

    @property
    def role_labels(self) -> str:
        return ", ".join(ROLE_LABELS[r] for r in self.roles)

    def masked(self, at: datetime, counter: int) -> User:
        """KVKK maskeleme (FR-1310): kişi kimliği gider, iş kaydı kalır.

        Kayıt silinmez; ad takma bir etiketle, telefon ve e-posta boş
        bırakılarak değiştirilir. Cevaplar ve kanıtlar bu kullanıcıya
        bağlı kalmaya devam eder — denetim izinin bütünlüğü için şart.
        """
        return replace(
            self,
            full_name=f"Eski personel #{counter:04d}",
            phone=None,
            email=None,
            status="masked",
            masked_at=at,
            assignments=(),
        )


def can_access(user: User, branch: Branch, *, region_of: UUID | None = None) -> bool:
    """Kullanıcı bu şubeyi görebilir mi? (FR-0205, TC-006, TC-010)

    `region_of` şubenin bölgesidir; `Branch.region_id` ile aynıdır ama
    çağıran farklı bir kaynaktan verebilsin diye ayrı parametre.
    """
    if user.status != "active":
        return False
    bolge = region_of if region_of is not None else branch.region_id
    for atama in user.assignments:
        if atama.role == "admin":
            return True
        if atama.role == "region_manager" and bolge is not None and atama.scope_id == bolge:
            return True
        if atama.role in ("branch_manager", "staff") and atama.scope_id == branch.id:
            return True
    return False


def visible_branches(user: User, branches: list[Branch]) -> list[Branch]:
    """Kullanıcının kapsamındaki şubeler; sıralama çağıranın işi."""
    return [b for b in branches if can_access(user, b)]
