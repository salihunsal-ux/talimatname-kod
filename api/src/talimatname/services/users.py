"""Personel kullanım senaryoları (ST-011, ST-013).

Davet, rol değişikliği, pasifleştirme ve KVKK maskelemesi burada; kanal
(SMS) burada değil — bildirim adaptörü yazılınca (ST-044) servise
enjekte edilir. Bugün davet **kuyruğa alınır**, "gönderildi" denmez.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID, uuid4

from talimatname.domain.errors import DomainError, ErrorKind
from talimatname.domain.organization import Branch
from talimatname.domain.users import Role, User, can_access
from talimatname.services.organization import OrganizationRepository


class PhoneTaken(DomainError):
    code = "telefon-kullanimda"
    title = "Bu telefon numarası zaten kayıtlı"
    kind: ErrorKind = "conflict"


class UserNotFound(DomainError):
    code = "kullanici-bulunamadi"
    title = "Kullanıcı bulunamadı"
    kind: ErrorKind = "not_found"


class ScopeNotFound(DomainError):
    code = "kapsam-bulunamadi"
    title = "Seçilen bölge ya da şube bulunamadı"
    kind: ErrorKind = "not_found"


class MaskedUserImmutable(DomainError):
    code = "maskeli-kullanici"
    title = "Maskelenmiş kullanıcı değiştirilemez"
    kind: ErrorKind = "conflict"


class UserRepository(Protocol):
    def users(self) -> list[User]: ...

    def user(self, user_id: UUID) -> User | None: ...

    def user_by_phone(self, phone: str) -> User | None: ...

    def save_user(self, user: User) -> None: ...

    def next_mask_counter(self) -> int: ...


class UserService:
    def __init__(
        self,
        repo: UserRepository,
        org: OrganizationRepository,
        *,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._repo = repo
        self._org = org
        self._now = now

    # --- okuma -------------------------------------------------------

    def list(
        self,
        *,
        branch_id: UUID | None = None,
        role: Role | None = None,
        include_inactive: bool = False,
    ) -> list[User]:
        sonuc = self._repo.users()
        if not include_inactive:
            sonuc = [k for k in sonuc if k.status == "active"]
        if role is not None:
            sonuc = [k for k in sonuc if role in k.roles]
        if branch_id is not None:
            sube = self._branch(branch_id)
            sonuc = [k for k in sonuc if can_access(k, sube)]
        return sorted(sonuc, key=lambda k: k.full_name.casefold())

    def get(self, user_id: UUID) -> User:
        kullanici = self._repo.user(user_id)
        if kullanici is None:
            raise UserNotFound(f"Kullanıcı id: {user_id}")
        return kullanici

    # --- yazma -------------------------------------------------------

    def invite(self, user: User) -> User:
        """Yeni kullanıcı: doğrula, kapsamı kontrol et, daveti kuyruğa al.

        Dönen kullanıcıda `invited_at` doludur; **SMS gönderilmemiştir**
        (sağlayıcı bağlı değil). Bunu kullanıcıya söylemek sunum
        katmanının işi.
        """
        hazir = user.validated()
        self._check_scopes(hazir)
        assert hazir.phone is not None
        if self._repo.user_by_phone(hazir.phone) is not None:
            raise PhoneTaken(f"Telefon: {hazir.phone}")
        kayit = replace(hazir, id=hazir.id or uuid4(), invited_at=self._now())
        self._repo.save_user(kayit)
        return kayit

    def update(self, user_id: UUID, **degisiklik: object) -> User:
        mevcut = self.get(user_id)
        if mevcut.status == "masked":
            raise MaskedUserImmutable(f"Kullanıcı id: {user_id}")
        guncel = replace(mevcut, **degisiklik).validated()  # type: ignore[arg-type]
        self._check_scopes(guncel)
        if guncel.phone != mevcut.phone and guncel.phone is not None:
            cakisan = self._repo.user_by_phone(guncel.phone)
            if cakisan is not None and cakisan.id != user_id:
                raise PhoneTaken(f"Telefon: {guncel.phone}")
        self._repo.save_user(guncel)
        return guncel

    def set_status(self, user_id: UUID, status: str) -> User:
        """Pasifleştirme: giriş kapanır, gelecek atamalar düşer, geçmiş kalır (BR-22)."""
        if status not in ("active", "inactive"):
            raise DomainError(f"Bilinmeyen durum: {status}")
        return self.update(user_id, status=status)

    def mask(self, user_id: UUID) -> User:
        """KVKK silme talebi (FR-1310): kişi kimliği gider, iş kaydı kalır."""
        mevcut = self.get(user_id)
        if mevcut.status == "masked":
            return mevcut
        maskeli = mevcut.masked(self._now(), self._repo.next_mask_counter())
        self._repo.save_user(maskeli)
        return maskeli

    # --- yardımcılar --------------------------------------------------

    def _branch(self, branch_id: UUID) -> Branch:
        sube = self._org.branch(branch_id)
        if sube is None:
            raise ScopeNotFound(f"Şube id: {branch_id}")
        return sube

    def _check_scopes(self, user: User) -> None:
        bolgeler = {b.id for b in self._org.regions()}
        subeler = {b.id for b in self._org.branches()}
        for atama in user.assignments:
            if atama.scope_type == "region" and atama.scope_id not in bolgeler:
                raise ScopeNotFound(f"Bölge id: {atama.scope_id}")
            if atama.scope_type == "branch" and atama.scope_id not in subeler:
                raise ScopeNotFound(f"Şube id: {atama.scope_id}")
