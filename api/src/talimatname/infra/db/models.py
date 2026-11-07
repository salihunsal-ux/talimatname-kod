"""Fiziksel şema (SQLAlchemy 2.0) — ADR-0014 md.4 ve md.11.

Kurallar:

* Her kiracı tablosunda `tenant_id`; satır düzeyi güvenlik (RLS) politikası
  bunun üzerine kurulur. Uygulama rolü `BYPASSRLS` **almaz**.
* Birincil anahtar `uuid`: cevap gibi kayıtların kimliği **cihazda**
  üretilebilsin diye (idempotency, ADR-0013).
* Tarihsel tablolar (cevap, aksiyon) yalnızca eklenir; düzeltme yeni
  satırdır. Güncelleme yalnızca durum alanlarında olur.
* Sağlayıcıya özel uzantı yok: `uuid` üretimi uygulamada, JSON alanları
  standart `jsonb`.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

#: RLS politikası olan tablolar — göç bunları gezip politika kurar.
#: Dikkat: yetkiler tablo tablo veriliyor, hepsi aynı değil —
#: `audit_event` ekle-yalnız (yalnızca SELECT, INSERT; göç 0006).
TENANT_TABLES: tuple[str, ...] = (
    "account_settings",
    "region",
    "branch",
    "station",
    "app_user",
    "role_assignment",
    "template",
    "template_version",
    "section",
    "item",
    "plan",
    "run",
    "answer",
    "action",
    "notification",
    "evidence",
    "audit_event",
    "export_job",
    "audit_anchor",
)


class Base(DeclarativeBase):
    pass


def _tenant_column() -> Mapped[UUID]:
    return mapped_column(Uuid, ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False)


class Tenant(Base):
    """Hesap. RLS'in dayandığı kök; kendisi politikasızdır."""

    __tablename__ = "tenant"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    default_timezone: Mapped[str] = mapped_column(String(64), default="Europe/Istanbul")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AccountSettings(Base):
    """Marka ayarları (FR-1401 adım 1).

    `tenant` tablosunda değil: orası RLS'in kökü ve uygulama rolü
    yalnızca okuyabiliyor (hesap açmak/silmek uygulamanın işi değil).
    Marka adı ve çalışma saatleri ise uygulamanın yazdığı veri, bu
    yüzden diğer tablolar gibi kiracıya bağlı ve RLS'li.
    """

    __tablename__ = "account_settings"

    tenant_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("tenant.id", ondelete="CASCADE"), primary_key=True
    )
    brand_name: Mapped[str] = mapped_column(String(120))
    timezone: Mapped[str] = mapped_column(String(64), default="Europe/Istanbul")
    default_hours: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    logo_url: Mapped[str | None] = mapped_column(String(400))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Region(Base):
    __tablename__ = "region"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    tenant_id: Mapped[UUID] = _tenant_column()
    name: Mapped[str] = mapped_column(String(80))
    code: Mapped[str | None] = mapped_column(String(16))


class Branch(Base):
    __tablename__ = "branch"
    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_branch_tenant_code"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    tenant_id: Mapped[UUID] = _tenant_column()
    region_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("region.id", ondelete="SET NULL")
    )
    code: Mapped[str] = mapped_column(String(16))
    name: Mapped[str] = mapped_column(String(80))
    timezone: Mapped[str] = mapped_column(String(64))
    address: Mapped[str | None] = mapped_column(Text)
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(16), default="active")
    #: Haftalık çalışma saatleri: {"0": ["08:00","23:00"], "6": null}
    business_hours: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)


class Station(Base):
    __tablename__ = "station"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    tenant_id: Mapped[UUID] = _tenant_column()
    branch_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("branch.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(40))
    kind: Mapped[str] = mapped_column(String(16), default="other")


class AppUser(Base):
    """Kullanıcı. `user` ayrılmış sözcüğe yakın olduğu için tablo adı `app_user`."""

    __tablename__ = "app_user"
    __table_args__ = (UniqueConstraint("tenant_id", "phone", name="uq_user_tenant_phone"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    tenant_id: Mapped[UUID] = _tenant_column()
    full_name: Mapped[str] = mapped_column(String(80))
    phone: Mapped[str | None] = mapped_column(String(20))
    email: Mapped[str | None] = mapped_column(String(160))
    status: Mapped[str] = mapped_column(String(16), default="active")
    language: Mapped[str] = mapped_column(String(8), default="tr")
    pin_set: Mapped[bool] = mapped_column(Boolean, default=False)
    invited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    masked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RoleAssignment(Base):
    __tablename__ = "role_assignment"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    tenant_id: Mapped[UUID] = _tenant_column()
    user_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("app_user.id", ondelete="CASCADE"))
    role: Mapped[str] = mapped_column(String(24))
    scope_type: Mapped[str] = mapped_column(String(12))
    scope_id: Mapped[UUID | None] = mapped_column(Uuid)


class UserSession(Base):
    """Yenileme belirteci (FR-0203); sırrın **özeti**, kendisi değil.

    Olay günlüğünün aksine güncellenebilir: iptal, son kullanım ve
    döndürme satırı değiştirir (göç 0011).
    """

    __tablename__ = "user_session"
    __table_args__ = (
        UniqueConstraint("token_digest", name="uq_oturum_ozet"),
        Index("ix_oturum_kullanici", "tenant_id", "user_id", "expires_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    tenant_id: Mapped[UUID] = _tenant_column()
    user_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("app_user.id", ondelete="CASCADE"))
    token_digest: Mapped[str] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(8), default="web")
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    device: Mapped[str | None] = mapped_column(String(120))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_reason: Mapped[str | None] = mapped_column(String(24))
    replaced_by: Mapped[UUID | None] = mapped_column(Uuid)


class Template(Base):
    __tablename__ = "template"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    tenant_id: Mapped[UUID] = _tenant_column()
    name: Mapped[str] = mapped_column(String(80))
    category: Mapped[str | None] = mapped_column(String(40))


class TemplateVersion(Base):
    __tablename__ = "template_version"
    __table_args__ = (UniqueConstraint("template_id", "version_no", name="uq_version_template_no"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    tenant_id: Mapped[UUID] = _tenant_column()
    template_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("template.id", ondelete="CASCADE"))
    version_no: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default="draft")
    camera_only: Mapped[bool] = mapped_column(Boolean, default=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Section(Base):
    __tablename__ = "section"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    tenant_id: Mapped[UUID] = _tenant_column()
    version_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("template_version.id", ondelete="CASCADE")
    )
    position: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(80))


class Item(Base):
    __tablename__ = "item"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    tenant_id: Mapped[UUID] = _tenant_column()
    section_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("section.id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column(Integer)
    type: Mapped[str] = mapped_column(String(16))
    title: Mapped[str] = mapped_column(String(160))
    hint: Mapped[str | None] = mapped_column(Text)
    required: Mapped[bool] = mapped_column(Boolean, default=True)
    photo_required: Mapped[bool] = mapped_column(Boolean, default=False)
    critical: Mapped[bool] = mapped_column(Boolean, default=False)
    options: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    min_value: Mapped[float | None] = mapped_column(Float)
    max_value: Mapped[float | None] = mapped_column(Float)
    unit: Mapped[str | None] = mapped_column(String(16))


class Plan(Base):
    __tablename__ = "plan"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    tenant_id: Mapped[UUID] = _tenant_column()
    version_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("template_version.id"))
    name: Mapped[str] = mapped_column(String(80))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    #: Kapsam: şube kimlikleri (v1'de grup yok)
    branch_ids: Mapped[list[str]] = mapped_column(JSONB, default=list)
    recurrence: Mapped[str] = mapped_column(String(200))
    starts_on: Mapped[date] = mapped_column(Date)
    start_time: Mapped[str | None] = mapped_column(String(8))
    anchor_reference: Mapped[str | None] = mapped_column(String(8))
    anchor_offset_minutes: Mapped[int] = mapped_column(Integer, default=0)
    duration_minutes: Mapped[int] = mapped_column(Integer)
    tolerance_minutes: Mapped[int] = mapped_column(Integer, default=0)
    assignment_kind: Mapped[str] = mapped_column(String(12), default="anyone")
    assignment_role: Mapped[str | None] = mapped_column(String(24))
    assignment_user_id: Mapped[UUID | None] = mapped_column(Uuid)


class Run(Base):
    __tablename__ = "run"
    __table_args__ = (
        Index("ix_run_day", "tenant_id", "business_day"),
        Index("ix_run_plan_branch", "plan_id", "branch_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    tenant_id: Mapped[UUID] = _tenant_column()
    plan_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("plan.id", ondelete="CASCADE"))
    version_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("template_version.id"))
    branch_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("branch.id", ondelete="CASCADE"))
    business_day: Mapped[date] = mapped_column(Date)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    tolerance_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(16), default="scheduled")
    result: Mapped[str | None] = mapped_column(String(10))
    score_percent: Mapped[int | None] = mapped_column(Integer)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    locked_by: Mapped[UUID | None] = mapped_column(Uuid)
    lock_renewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_reason: Mapped[str | None] = mapped_column(String(200))


class Answer(Base):
    """Cevap. `id` cihazda üretilir; ikinci yazma aynı satırı günceller."""

    __tablename__ = "answer"
    __table_args__ = (Index("ix_answer_run", "run_id"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    tenant_id: Mapped[UUID] = _tenant_column()
    run_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("run.id", ondelete="CASCADE"))
    item_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("item.id"))
    state: Mapped[str] = mapped_column(String(16))
    value: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    note: Mapped[str | None] = mapped_column(Text)
    user_id: Mapped[UUID | None] = mapped_column(Uuid)
    device_id: Mapped[UUID | None] = mapped_column(Uuid)
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    device_reported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    clock_skew_minutes: Mapped[int | None] = mapped_column(Integer)
    evidence_count: Mapped[int] = mapped_column(Integer, default=0)
    #: Yapılamadı sebebi (BR-09). Kod saklanır, etiket değil: etiket
    #: değişince geçmiş raporun kırılmaması için (FR-0805).
    not_done_reason: Mapped[str | None] = mapped_column(String(20))


class Action(Base):
    __tablename__ = "action"
    __table_args__ = (Index("ix_action_open", "tenant_id", "status", "due_at"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    tenant_id: Mapped[UUID] = _tenant_column()
    branch_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("branch.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(160))
    description: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(16))
    source_id: Mapped[UUID | None] = mapped_column(Uuid)
    priority: Mapped[str] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(10), default="open")
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    assignee_user_id: Mapped[UUID | None] = mapped_column(Uuid)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_by: Mapped[UUID | None] = mapped_column(Uuid)
    close_note: Mapped[str | None] = mapped_column(Text)


class Notification(Base):
    """Bildirim kuyruğu ve teslimat izi (FR-1005).

    Kuyruk ve iz **aynı satır**: ayrı tablo tutmak, "ne gönderilecekti"
    ile "ne oldu" sorularını ayırır ve ikisini birleştirmek için her
    seferinde birleştirme gerektirirdi. Satır gönderildikçe güncellenir.
    """

    __tablename__ = "notification"
    __table_args__ = (Index("ix_notification_due", "tenant_id", "status", "send_at"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    tenant_id: Mapped[UUID] = _tenant_column()
    kind: Mapped[str] = mapped_column(String(24))
    channel: Mapped[str] = mapped_column(String(10))
    user_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("app_user.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(160))
    body: Mapped[str] = mapped_column(Text, default="")
    send_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    branch_id: Mapped[UUID | None] = mapped_column(Uuid)
    run_id: Mapped[UUID | None] = mapped_column(Uuid)
    action_id: Mapped[UUID | None] = mapped_column(Uuid)
    deep_link: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(12), default="queued")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(40))
    error_detail: Mapped[str | None] = mapped_column(Text)


class Evidence(Base):
    """Kanıt dosyası ve bağlamı (FR-0606).

    `sha256` üzerinde **kiracı içinde tekil** indeks: aynı fotoğrafın
    ikinci kez kullanılması veritabanı düzeyinde de engellenir. Servis
    katmanındaki denetim yarış durumunda kaçabilir, indeks kaçmaz.
    """

    __tablename__ = "evidence"
    __table_args__ = (
        Index("ux_evidence_digest", "tenant_id", "sha256", unique=True),
        Index("ix_evidence_run", "tenant_id", "run_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    tenant_id: Mapped[UUID] = _tenant_column()
    run_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("run.id", ondelete="CASCADE"))
    answer_id: Mapped[UUID] = mapped_column(Uuid)
    item_id: Mapped[UUID] = mapped_column(Uuid)
    branch_id: Mapped[UUID] = mapped_column(Uuid)
    user_id: Mapped[UUID | None] = mapped_column(Uuid)
    sha256: Mapped[str] = mapped_column(String(64))
    content_type: Mapped[str] = mapped_column(String(40))
    size_bytes: Mapped[int] = mapped_column(Integer)
    storage_key: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(10), default="pending")
    captured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    device_reported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    clock_skew_minutes: Mapped[int | None] = mapped_column(Integer)
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    distance_meters: Mapped[int | None] = mapped_column(Integer)
    device_id: Mapped[UUID | None] = mapped_column(Uuid)
    from_gallery: Mapped[bool] = mapped_column(Boolean, default=False)
    flags: Mapped[Any] = mapped_column(JSONB, default=list)
    stored_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    stamped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    stamped_key: Mapped[str | None] = mapped_column(String(200))
    thumbnail_key: Mapped[str | None] = mapped_column(String(200))


class AuditEvent(Base):
    """Ekle-yalnız olay günlüğü (FR-1301).

    Uygulama rolünün bu tabloda **yalnızca SELECT ve INSERT** yetkisi
    var (bkz. göç 0006): ekle-yalnızlık koda değil veritabanına
    yazılı. Kodda güncelleme/silme yöntemi de yok (TC-100).

    `(tenant_id, sequence)` tekil: iki istek aynı anda yazıp zinciri
    çatallayamaz; ikincisi hata alır ve yeniden dener.
    """

    __tablename__ = "audit_event"
    __table_args__ = (
        UniqueConstraint("tenant_id", "sequence", name="uq_audit_sira"),
        Index("ix_audit_nesne", "tenant_id", "object_id"),
        Index("ix_audit_zaman", "tenant_id", "at"),
        # Belge kodu aramasi (FR-1218): arama ifadesiyle **ayni** ifade.
        # Oturumsuz uc nokta tam tarama yapmasin diye var (goc 0007).
        Index("ix_audit_kod", "tenant_id", text("substr(hash, 1, 12)")),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    tenant_id: Mapped[UUID] = _tenant_column()
    sequence: Mapped[int] = mapped_column(BigInteger)
    event_type: Mapped[str] = mapped_column(String(40))
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    object_type: Mapped[str] = mapped_column(String(30))
    object_id: Mapped[UUID | None] = mapped_column(Uuid)
    actor_id: Mapped[UUID | None] = mapped_column(Uuid)
    ip: Mapped[str | None] = mapped_column(String(45))
    device: Mapped[str | None] = mapped_column(String(120))
    before: Mapped[Any] = mapped_column(JSONB, default=dict)
    after: Mapped[Any] = mapped_column(JSONB, default=dict)
    prev_hash: Mapped[str] = mapped_column(String(64))
    hash: Mapped[str] = mapped_column(String(64))


class ExportJob(Base):
    """Arka planda üretilen çıktının iş kaydı (FR-1217).

    Süreç içi bir kuyruk değil tablo: API ya da zamanlayıcı yeniden
    başladığında kullanıcının beklediği rapor kaybolmasın ve "neden
    gelmedi" sorusunun cevabı burada olsun (göç 0008).
    """

    __tablename__ = "export_job"
    __table_args__ = (
        Index("ix_cikti_kisi", "tenant_id", "requested_by", "requested_at"),
        Index("ix_cikti_durum", "tenant_id", "state", "requested_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    tenant_id: Mapped[UUID] = _tenant_column()
    kind: Mapped[str] = mapped_column(String(30))
    params: Mapped[Any] = mapped_column(JSONB, default=dict)
    requested_by: Mapped[UUID] = mapped_column(Uuid)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    run_count: Mapped[int] = mapped_column(Integer, default=0)
    state: Mapped[str] = mapped_column(String(10), default="queued")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    object_key: Mapped[str | None] = mapped_column(String(200))
    size_bytes: Mapped[int | None] = mapped_column(Integer)
    document_code: Mapped[str | None] = mapped_column(String(20))
    error_code: Mapped[str | None] = mapped_column(String(60))


class AuditAnchor(Base):
    """Günün zincir kökü ve dış damgası (FR-1302).

    Ekle-yalnız, günlüğün kendisi gibi (göç 0009): bir çıpayı
    sonradan düzeltebilmek, çıpanın anlamını ortadan kaldırırdı.
    """

    __tablename__ = "audit_anchor"
    __table_args__ = (Index("ix_cipa_zaman", "tenant_id", "created_at"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    tenant_id: Mapped[UUID] = _tenant_column()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    sequence: Mapped[int] = mapped_column(BigInteger)
    chain_hash: Mapped[str] = mapped_column(String(64))
    state: Mapped[str] = mapped_column(String(10), default="ok")
    token: Mapped[bytes | None] = mapped_column(LargeBinary)
    stamped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    tsa_name: Mapped[str | None] = mapped_column(String(200))
    serial: Mapped[str | None] = mapped_column(String(64))
    error: Mapped[str | None] = mapped_column(String(200))
