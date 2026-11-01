"""Şablon kullanım senaryoları (ST-014, ST-016, ST-017).

İki kural burada yaşıyor ve ikisi de ürünün bel kemiği:

* **Yayınlanan sürüm değişmez.** Düzenleme her zaman taslakta olur;
  yayınlanmış bir sürüm düzenlenmek istendiğinde yeni taslak türetilir.
  Çalıştırmalar sürüme bağlandığı için geçmiş böyle korunur (FR-0301).
* **Yayın doğrulaması tüm sorunları birden döner** (FR-0312).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID, uuid4

from talimatname.domain.errors import DomainError, ErrorKind
from talimatname.domain.templates import (
    PublishIssue,
    Section,
    Template,
    TemplateVersion,
    VersionSettings,
)
from talimatname.services.audit import AuditService


class TemplateNotFound(DomainError):
    code = "sablon-bulunamadi"
    title = "Şablon bulunamadı"
    kind: ErrorKind = "not_found"


class VersionNotFound(DomainError):
    code = "surum-bulunamadi"
    title = "Şablon sürümü bulunamadı"
    kind: ErrorKind = "not_found"


class VersionNotDraft(DomainError):
    code = "surum-taslak-degil"
    title = "Yayınlanmış sürüm değiştirilemez"
    kind: ErrorKind = "conflict"


class PublishRejected(DomainError):
    code = "yayin-dogrulanamadi"
    title = "Şablon yayınlanamaz"
    kind: ErrorKind = "invalid"


class TemplateRepository(Protocol):
    def templates(self) -> list[Template]: ...

    def template(self, template_id: UUID) -> Template | None: ...

    def save_template(self, template: Template) -> None: ...

    def versions(self, template_id: UUID) -> list[TemplateVersion]: ...

    def version(self, version_id: UUID) -> TemplateVersion | None: ...

    def save_version(self, version: TemplateVersion) -> None: ...


class TemplateService:
    def __init__(
        self,
        repo: TemplateRepository,
        audit: AuditService | None = None,
        *,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._repo = repo
        self._izi = audit
        self._now = now

    # --- okuma -------------------------------------------------------

    def list_templates(self) -> list[tuple[Template, list[TemplateVersion]]]:
        return [
            (sablon, sorted(self._repo.versions(sablon.id), key=lambda s: -s.version_no))
            for sablon in sorted(self._repo.templates(), key=lambda t: t.name.casefold())
        ]

    def get(self, template_id: UUID) -> Template:
        sablon = self._repo.template(template_id)
        if sablon is None:
            raise TemplateNotFound(f"Şablon id: {template_id}")
        return sablon

    def version(self, version_id: UUID) -> TemplateVersion:
        surum = self._repo.version(version_id)
        if surum is None:
            raise VersionNotFound(f"Sürüm id: {version_id}")
        return surum

    def published(self, template_id: UUID) -> TemplateVersion | None:
        """Planların bağlandığı sürüm: yayında olan (en fazla bir tane)."""
        return next(
            (s for s in self._repo.versions(template_id) if s.status == "published"),
            None,
        )

    # --- yazma -------------------------------------------------------

    def create(self, name: str, category: str | None = None) -> tuple[Template, TemplateVersion]:
        sablon = Template(id=uuid4(), name=name, category=category).validated()
        self._repo.save_template(sablon)
        taslak = TemplateVersion(id=uuid4(), template_id=sablon.id, version_no=1)
        self._repo.save_version(taslak)
        return sablon, taslak

    def save_draft(
        self,
        version_id: UUID,
        sections: tuple[Section, ...],
        settings: VersionSettings | None = None,
    ) -> TemplateVersion:
        surum = self.version(version_id)
        if surum.status != "draft":
            raise VersionNotDraft(f"Sürüm {surum.version_no} yayında ya da arşivde")
        guncel = replace(
            surum,
            sections=sections,
            settings=settings or surum.settings,
        ).validated()
        self._repo.save_version(guncel)
        return guncel

    def new_draft(self, template_id: UUID) -> TemplateVersion:
        """Yayındaki sürümden yeni taslak türetir (FR-0301).

        Yayınlanmış sürüm olduğu gibi kalır: ona bağlı çalıştırmalar ve
        kanıtlar tarihsel olarak doğru kalmalı. Açık taslak varsa yenisi
        üretilmez, var olan döner.
        """
        surumler = self._repo.versions(template_id)
        if not surumler:
            raise TemplateNotFound(f"Şablon id: {template_id}")
        acik = next((s for s in surumler if s.status == "draft"), None)
        if acik is not None:
            return acik
        kaynak = max(surumler, key=lambda s: s.version_no)
        taslak = TemplateVersion(
            id=uuid4(),
            template_id=template_id,
            version_no=max(s.version_no for s in surumler) + 1,
            sections=kaynak.sections,
            settings=kaynak.settings,
        )
        self._repo.save_version(taslak)
        return taslak

    def publish_check(self, version_id: UUID) -> list[PublishIssue]:
        return self.version(version_id).publish_issues()

    def publish(self, version_id: UUID) -> TemplateVersion:
        """Taslağı yayına alır; önceki yayın sürümü arşive düşer (v1: hemen)."""
        surum = self.version(version_id)
        if surum.status != "draft":
            raise VersionNotDraft(f"Sürüm {surum.version_no} zaten {surum.status}")

        sorunlar = surum.publish_issues()
        if sorunlar:
            raise PublishRejected(
                f"{len(sorunlar)} sorun düzeltilmeli",
                issues=[{"where": s.where, "message": s.message} for s in sorunlar],
            )

        onceki = self.published(surum.template_id)
        if onceki is not None:
            self._repo.save_version(replace(onceki, status="archived"))

        yayin = replace(surum, status="published", published_at=self._now())
        self._repo.save_version(yayin)
        if self._izi is not None:
            # Yayın, kontrolün **içeriğinin** değiştiği an: hangi
            # maddelerin sorulduğu buradan sonra farklı. Denetimde
            # "o gün hangi liste yürürlükteydi" sorusunun izi bu.
            sablon = self._repo.template(yayin.template_id)
            self._izi.record(
                "sablon.yayinlandi",
                object_type="sablon",
                object_id=yayin.template_id,
                before={"onceki_surum": str(onceki.version_no) if onceki else "-"},
                after={
                    "ad": sablon.name if sablon else "-",
                    "surum": str(yayin.version_no),
                    "madde": str(len(yayin.items)),
                    "kritik": str(sum(1 for m in yayin.items if m.critical)),
                },
            )
        return yayin
