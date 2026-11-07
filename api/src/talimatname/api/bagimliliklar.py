"""Bağımlılıklar: hangi kalıcılık adaptörünün kullanılacağı tek yerde.

`DATABASE_URL` doluysa **PostgreSQL** adaptörleri, boşsa **bellek içi**
adaptörler kullanılır. Servis katmanı ve uç noktalar iki durumda da aynı
kodu çalıştırır (ADR-0014 md.2).

Bellek içi adaptör bir geliştirme kolaylığıdır: veritabanı olmadan panel
açılır, saf alan testleri koşar. Kalıcılık gerektiren her şey — geçmiş,
raporlar, kanıt — PostgreSQL ister.
"""

from __future__ import annotations

from functools import lru_cache

from talimatname.infra.memory import (
    MemoryActionRepository,
    MemoryAnchorRepository,
    MemoryAnswerRepository,
    MemoryAuditRepository,
    MemoryEvidenceRepository,
    MemoryExportJobRepository,
    MemoryNotificationRepository,
    MemoryOrganizationRepository,
    MemoryPlanRepository,
    MemorySessionRepository,
    MemorySettingsRepository,
    MemoryTemplateRepository,
    MemoryUserRepository,
)
from talimatname.services.actions import ActionRepository, ActionService
from talimatname.services.anchors import AnchorRepository, AnchorService, TimestampAuthority
from talimatname.services.audit import AuditRepository, AuditService
from talimatname.services.auth import AuthService
from talimatname.services.dashboard import DashboardService
from talimatname.services.digest import DigestService
from talimatname.services.escalation import EscalationService
from talimatname.services.evidence import EvidenceRepository, EvidenceService
from talimatname.services.execution import AnswerRepository, ExecutionService
from talimatname.services.export_jobs import ExportJobRepository, ExportJobService
from talimatname.services.exports import ExportService
from talimatname.services.notifications import (
    NotificationRepository,
    NotificationService,
)
from talimatname.services.organization import OrganizationRepository, OrganizationService
from talimatname.services.pdf import Brand, brand_for
from talimatname.services.plans import PlanRepository, PlanService
from talimatname.services.reminders import ReminderService
from talimatname.services.reports import ReportService
from talimatname.services.scheduler import SchedulerService
from talimatname.services.sessions import SessionRepository, SessionService
from talimatname.services.setup import SettingsRepository, SetupService
from talimatname.services.storage import LocalObjectStore, ObjectStore, S3ObjectStore
from talimatname.services.sync import SyncService
from talimatname.services.templates import TemplateRepository, TemplateService
from talimatname.services.users import UserRepository, UserService
from talimatname.services.verification import DEFAULT_TIMEZONE, VerificationService
from talimatname.settings import Settings, get_settings

# --- ayarlar ----------------------------------------------------------

_ayarlar: Settings | None = None


def ayarlari_kullan(yeni: Settings) -> None:
    """`create_app`in aldığı ayarları süreç geneline bağlar.

    Buradaki depolar ve servisler süreç başına tek örnek olduğundan
    ayarın da tek kaynağı olmalı. Bunsuz `create_app(Settings(...))`
    yalnızca uç noktaları etkiliyor, servisler ortam değişkenlerini
    okumaya devam ediyordu — testte bir kez ısırdı.
    """
    global _ayarlar
    _ayarlar = yeni
    sifirla()


def ayarlar() -> Settings:
    """Bağlanmış ayar yoksa ortamdan okunan ayar."""
    return _ayarlar if _ayarlar is not None else get_settings()


def sql_modu() -> bool:
    """Kalıcı mod mu? Tek karar noktası."""
    return ayarlar().database_url is not None


def _kiraci() -> object:
    from talimatname.seed import DEV_TENANT

    return DEV_TENANT


# --- depolar (süreç başına tek örnek) ---------------------------------


@lru_cache
def _org_deposu() -> OrganizationRepository:
    if sql_modu():
        from talimatname.infra.db.adapters import SqlOrganizationRepository

        return SqlOrganizationRepository(_kiraci())  # type: ignore[arg-type]
    return MemoryOrganizationRepository()


@lru_cache
def _kullanici_deposu() -> UserRepository:
    if sql_modu():
        from talimatname.infra.db.adapters import SqlUserRepository

        return SqlUserRepository(_kiraci())  # type: ignore[arg-type]
    return MemoryUserRepository()


@lru_cache
def _oturum_deposu() -> SessionRepository:
    if sql_modu():
        from talimatname.infra.db.adapters import SqlSessionRepository

        return SqlSessionRepository(_kiraci())  # type: ignore[arg-type]
    return MemorySessionRepository()


@lru_cache
def _sablon_deposu() -> TemplateRepository:
    if sql_modu():
        from talimatname.infra.db.adapters import SqlTemplateRepository

        return SqlTemplateRepository(_kiraci())  # type: ignore[arg-type]
    return MemoryTemplateRepository()


@lru_cache
def _plan_deposu() -> PlanRepository:
    if sql_modu():
        from talimatname.infra.db.adapters import SqlPlanRepository

        return SqlPlanRepository(_kiraci())  # type: ignore[arg-type]
    return MemoryPlanRepository()


@lru_cache
def _cevap_deposu() -> AnswerRepository:
    if sql_modu():
        from talimatname.infra.db.adapters import SqlAnswerRepository

        return SqlAnswerRepository(_kiraci())  # type: ignore[arg-type]
    return MemoryAnswerRepository()


@lru_cache
def _aksiyon_deposu() -> ActionRepository:
    if sql_modu():
        from talimatname.infra.db.adapters import SqlActionRepository

        return SqlActionRepository(_kiraci())  # type: ignore[arg-type]
    return MemoryActionRepository()


@lru_cache
def _bildirim_deposu() -> NotificationRepository:
    if sql_modu():
        from talimatname.infra.db.adapters import SqlNotificationRepository

        return SqlNotificationRepository(_kiraci())  # type: ignore[arg-type]
    return MemoryNotificationRepository()


@lru_cache
def _kanit_deposu() -> EvidenceRepository:
    if sql_modu():
        from talimatname.infra.db.adapters import SqlEvidenceRepository

        return SqlEvidenceRepository(_kiraci())  # type: ignore[arg-type,return-value]
    return MemoryEvidenceRepository()  # type: ignore[return-value]


@lru_cache
def _cikti_deposu() -> ExportJobRepository:
    if sql_modu():
        from talimatname.infra.db.adapters import SqlExportJobRepository

        return SqlExportJobRepository(_kiraci())  # type: ignore[arg-type]
    return MemoryExportJobRepository()


def cikti_servisi() -> ExportJobService:
    """Arka planda üretilen çıktılar (FR-1217).

    Kendi okuma yolunu kurmuyor: rapor servisi, organizasyon ve kanıt
    deposu aynı — kâğıt, ekranın gördüğü veriyle aynı yerden besleniyor.
    Olay günlüğü de bağlı: arka planda üretilen rapor da doğrulama
    sayfasından sorulabilsin (FR-1218).
    """
    return ExportJobService(
        _cikti_deposu(),
        rapor_servisi(),
        organizasyon_servisi(),
        _kullanici_deposu(),
        _nesne_deposu(),
        brand=marka,
        audit=izi_servisi(),
        notifications=bildirim_servisi(),
    )


@lru_cache
def _izi_deposu() -> AuditRepository:
    if sql_modu():
        from talimatname.infra.db.adapters import SqlAuditRepository

        return SqlAuditRepository(_kiraci())  # type: ignore[arg-type,return-value]
    return MemoryAuditRepository()  # type: ignore[return-value]


@lru_cache
def izi_servisi() -> AuditService:
    """Olay günlüğü (FR-1301). Tek örnek: zincirin başı tek yerden okunur."""
    return AuditService(_izi_deposu())


@lru_cache
def _ayar_deposu() -> SettingsRepository:
    if sql_modu():
        from talimatname.infra.db.adapters import SqlSettingsRepository

        return SqlSettingsRepository(_kiraci())  # type: ignore[arg-type]
    return MemorySettingsRepository()


@lru_cache
def _nesne_deposu() -> ObjectStore:
    """S3 ayarlıysa kova, değilse yerel dizin (ADR-0012 md.4).

    Seçim tek yerde ve **yarım yapılandırma yok**: ayarlar sınıfı
    uç nokta verilip anahtar verilmediğinde açılışta hata veriyor,
    böylece kanıtın nerede durduğu hiçbir zaman belirsiz kalmıyor.
    """
    ayar = ayarlar()
    if ayar.object_store_configured:
        assert ayar.object_store_endpoint
        assert ayar.object_store_bucket
        assert ayar.object_store_access_key
        assert ayar.object_store_secret_key
        kova = S3ObjectStore(
            endpoint=ayar.object_store_endpoint,
            bucket=ayar.object_store_bucket,
            access_key=ayar.object_store_access_key,
            secret_key=ayar.object_store_secret_key,
            region=ayar.object_store_region,
        )
        kova.ensure_bucket()
        return kova
    return LocalObjectStore(ayar.evidence_dir)


# --- servisler --------------------------------------------------------


@lru_cache
def _kimlik_servisi() -> AuthService:
    """Tek örnek: OTP durumu süreç içinde tutuluyor (kısa ömürlü)."""
    return AuthService(_kullanici_deposu(), settings=ayarlar())


def kimlik_servisi() -> AuthService:
    return _kimlik_servisi()


@lru_cache
def _oturum_servisi() -> SessionService:
    return SessionService(_oturum_deposu())


def oturum_servisi() -> SessionService:
    return _oturum_servisi()


def organizasyon_servisi() -> OrganizationService:
    return OrganizationService(_org_deposu())


def kullanici_servisi() -> UserService:
    return UserService(_kullanici_deposu(), _org_deposu(), izi_servisi())


def sablon_servisi() -> TemplateService:
    return TemplateService(_sablon_deposu(), izi_servisi())


def aksiyon_servisi() -> ActionService:
    return ActionService(_aksiyon_deposu(), _org_deposu(), _plan_deposu())


def bildirim_servisi() -> NotificationService:
    """Sürücü listesi boş: push (ST-046) ve SMS (ST-067) henüz bağlı değil.

    Sürücüsüz gönderim denemesi kuyruğa `surucu-yok` hatasıyla
    yazılır — eksik olan şeyin listesi böyle görünür hale gelir.
    """
    return NotificationService(_bildirim_deposu(), _kullanici_deposu())


def hatirlatma_servisi() -> ReminderService:
    return ReminderService(_plan_deposu(), _org_deposu(), _kullanici_deposu(), bildirim_servisi())


def eskalasyon_servisi() -> EscalationService:
    return EscalationService(
        _plan_deposu(),
        _org_deposu(),
        _kullanici_deposu(),
        _aksiyon_deposu(),
        bildirim_servisi(),
        izi_servisi(),
    )


def ozet_servisi() -> DigestService:
    return DigestService(
        _plan_deposu(),
        _org_deposu(),
        _kullanici_deposu(),
        _aksiyon_deposu(),
        bildirim_servisi(),
    )


def zamanlayici_servisi() -> SchedulerService:
    return SchedulerService(
        _plan_deposu(),
        _org_deposu(),
        _sablon_deposu(),
        ActionService(_aksiyon_deposu(), _org_deposu(), _plan_deposu()),
        hatirlatma_servisi(),
        bildirim_servisi(),
        eskalasyon_servisi(),
        ozet_servisi(),
        kanit_servisi(),
        cikti_servisi(),
        izi_servisi(),
        cipa_servisi(),
    )


def plan_servisi() -> PlanService:
    _ilk_tur()
    return PlanService(_plan_deposu(), _org_deposu(), _sablon_deposu(), izi_servisi())


def yurutme_servisi() -> ExecutionService:
    """Gönderim kapısı kanıtı **sayar**, beyana bakmaz (FR-0607).

    Kanıt servisini buradan geçiriyoruz ki gönderim "fotoğraf var mı"
    sorusunu depoya sorsun; cihazın gönderdiği sayıya güvenmek
    çevrimdışı yolda fotoğrafsız gönderime kapı açardı (ST-054).
    """
    _ilk_tur()
    return ExecutionService(
        _cevap_deposu(),
        _plan_deposu(),
        _sablon_deposu(),
        _aksiyon_deposu(),
        verified_evidence=lambda run_id: kanit_servisi().verified_counts(run_id),
        # Kilit çakışmasında "X yapıyor" diyebilmek için (BR-26).
        user_name=lambda user_id: kullanici_servisi().name(user_id),
        audit=izi_servisi(),
        prep_minutes=ayarlar().run_prep_minutes,
    )


def kanit_servisi() -> EvidenceService:
    """Kullanıcı deposu damga metni için: damgada kişinin adı yazılı (FR-0606)."""
    return EvidenceService(
        _kanit_deposu(),
        _plan_deposu(),
        _org_deposu(),
        _nesne_deposu(),
        _kullanici_deposu(),
        settings=ayarlar(),
        audit=izi_servisi(),
    )


def disa_aktarim_servisi() -> ExportService:
    """Çalıştırma PDF'ini derleyen servis (FR-1213).

    Kendi okuma yolunu kurmuyor: yürütme görünümünü, kanıt servisini
    ve olay günlüğünü kullanıyor — kâğıt, ekranın gördüğü veriyle
    aynı yerden besleniyor.
    """
    return ExportService(
        yurutme_servisi(),
        kanit_servisi(),
        _org_deposu(),
        _sablon_deposu(),
        _kullanici_deposu(),
        izi_servisi(),
    )


def senk_servisi() -> SyncService:
    """Senk, yazma için kendi yolunu kurmaz: yürütme ve kanıt servislerini
    kullanır (ST-054). Böylece çevrimdışı gelen cevap, panelden gelenle
    aynı kuralları geçer."""
    _ilk_tur()
    return SyncService(
        _plan_deposu(),
        _org_deposu(),
        _sablon_deposu(),
        yurutme_servisi(),
        kanit_servisi(),
    )


def kurulum_servisi() -> SetupService:
    """Sihirbaz kendi yazma yolunu kurmaz: şubeyi org deposuna yazar."""
    return SetupService(
        _ayar_deposu(),
        _org_deposu(),
        _sablon_deposu(),
        _plan_deposu(),
        _kullanici_deposu(),
    )


def _saat_dilimi() -> str:
    """Hesabın saat dilimi; sihirbaz bitmemişse varsayılan.

    İki yer soruyor: belge doğrulama (kâğıttaki yerel saat) ve çıpalama
    (günün 04:00'ü yerel saattir). Tek yerden okunsun.
    """
    ayar = kurulum_servisi().settings()
    return ayar.timezone if ayar else DEFAULT_TIMEZONE


@lru_cache
def _cipa_deposu() -> AnchorRepository:
    if sql_modu():
        from talimatname.infra.db.adapters import SqlAnchorRepository

        return SqlAnchorRepository(_kiraci())  # type: ignore[arg-type]
    return MemoryAnchorRepository()


@lru_cache
def _damga_otoritesi() -> TimestampAuthority | None:
    """RFC 3161 sunucusu ayarlıysa istemci, değilse **None**.

    None çıpalamayı kapatıyor ve bu sessiz bir varsayılan değil:
    `/health` ve doğrulama komutu durumu söylüyor. Kapalıyken
    zincirin sınırı olduğu gibi duruyor (FR-1302).
    """
    ayar = ayarlar()
    if not ayar.timestamping_configured:
        return None
    from talimatname.infra.tsa import Rfc3161Authority

    assert ayar.tsa_url
    return Rfc3161Authority(
        ayar.tsa_url,
        policy_oid=ayar.tsa_policy_oid,
        timeout_seconds=ayar.tsa_timeout_seconds,
    )


def cipa_servisi() -> AnchorService:
    """Zincir kökünün günlük çıpalanması (FR-1302)."""
    return AnchorService(
        _cipa_deposu(),
        _izi_deposu(),
        _damga_otoritesi(),
        timezone=_saat_dilimi,
    )


def marka() -> Brand:
    """Kâğıdın üstündeki hesap: kurulum ayarı + doğrulama adresi.

    Tek yerde: uç noktalar da arka plan işçisi de (FR-1217) aynı
    başlığı basıyor. İki ayrı kuruluş, iki farklı kâğıt demekti.
    """
    return brand_for(kurulum_servisi().settings(), verify_url=ayarlar().verify_url)


def dogrulama_servisi() -> VerificationService:
    """Belge doğrulama (FR-1218). Kendi okuma yolu yok: olay günlüğü.

    Saat dilimi hesabın ayarından geliyor çünkü kâğıtta **yerel** saat
    yazılı; sayfa UTC gösterse denetçi iki farklı saat görür ve
    kâğıdın sahte olduğunu düşünürdü.
    """

    return VerificationService(izi_servisi(), timezone=_saat_dilimi)


def rapor_servisi() -> ReportService:
    """Raporlar kanıt deposunu da görüyor: galeri aynı kayıtlardan."""
    _ilk_tur()
    return ReportService(
        _plan_deposu(),
        _cevap_deposu(),
        _sablon_deposu(),
        _org_deposu(),
        _kanit_deposu(),
    )


def pano_servisi() -> DashboardService:
    _ilk_tur()
    return DashboardService(_plan_deposu(), _org_deposu())


# --- geliştirme kolaylığı ---------------------------------------------

_ilk_tur_kosuldu = False

#: Süreç başına tek örnek tutan her şey. Ayar değişince sıfırlanır.
_ONBELLEKLER = (
    _org_deposu,
    _kullanici_deposu,
    _sablon_deposu,
    _plan_deposu,
    _cevap_deposu,
    _aksiyon_deposu,
    _bildirim_deposu,
    _kanit_deposu,
    _izi_deposu,
    izi_servisi,
    _cikti_deposu,
    _cipa_deposu,
    _damga_otoritesi,
    _ayar_deposu,
    _nesne_deposu,
    _kimlik_servisi,
)


def sifirla() -> None:
    """Depoları ve servisleri bırakır; sonraki istek yenisini kurar."""
    global _ilk_tur_kosuldu
    for onbellek in _ONBELLEKLER:
        onbellek.cache_clear()
    _ilk_tur_kosuldu = False


def _ilk_tur() -> None:
    """Zamanlayıcı süreci açık değilken ilk istekte bir tur atar.

    Üretimde zamanlayıcı ayrı süreçtir (ST-027); bu kanca yalnızca
    geliştiricinin panelde boş pano görmemesi içindir ve idempotenttir.
    """
    global _ilk_tur_kosuldu
    if not _ilk_tur_kosuldu:
        _ilk_tur_kosuldu = True
        zamanlayici_servisi().tick()
