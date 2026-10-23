"""PostgreSQL adaptörleri ve kiracı yalıtımı (TC-011, ADR-0014 md.4).

Bu testler **çalışan bir veritabanı ister**: `DATABASE_URL` yoksa sebebi
yazılarak atlanır (sessiz atlama yok). Kendi kiracısını açar, işini
yapar, sonra siler — paylaşılan geliştirme veritabanını kirletmez.
"""

from __future__ import annotations

from datetime import UTC, datetime, time, timedelta
from uuid import UUID, uuid4, uuid5

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from talimatname.domain.evidence import Evidence
from talimatname.domain.notifications import Notification
from talimatname.domain.organization import Branch, uniform_hours
from talimatname.domain.plans import Plan, Run
from talimatname.domain.templates import Template, TemplateVersion
from talimatname.domain.users import RoleAssignment, User
from talimatname.domain.window import WindowRule
from talimatname.settings import get_settings

pytestmark = pytest.mark.db

if get_settings().database_url is None:  # pragma: no cover - ortam bağımlı
    pytest.skip(
        "DATABASE_URL tanımlı değil: veritabanı testleri atlandı "
        "(bkz. infra/veritabani-kurulum.md)",
        allow_module_level=True,
    )

from talimatname.infra.db.adapters import (  # noqa: E402
    SqlEvidenceRepository,
    SqlNotificationRepository,
    SqlOrganizationRepository,
    SqlPlanRepository,
    SqlTemplateRepository,
    SqlUserRepository,
)
from talimatname.infra.db.session import APP_ROLE, create_db_engine  # noqa: E402
from talimatname.seed import DEV_TENANT  # noqa: E402

AD_ALANI = UUID("9f2b7c41-5d6e-4a83-9c17-2e4b8a6d3f55")
A_KIRACI = uuid5(AD_ALANI, "test:kiraci-a")
B_KIRACI = uuid5(AD_ALANI, "test:kiraci-b")


def _kiraci_ac(kiraci: UUID, ad: str) -> None:
    motor = create_db_engine(as_owner=True)
    with motor.begin() as b:
        b.execute(
            text(
                "INSERT INTO tenant (id, name, default_timezone, created_at) "
                "VALUES (:id, :ad, 'Europe/Istanbul', :an) ON CONFLICT (id) DO NOTHING"
            ),
            {"id": kiraci, "ad": ad, "an": datetime.now(UTC)},
        )


def _kiraci_sil(*kiracilar: UUID) -> None:
    motor = create_db_engine(as_owner=True)
    with motor.begin() as b:
        for kiraci in kiracilar:
            b.execute(text("DELETE FROM tenant WHERE id = :id"), {"id": kiraci})


@pytest.fixture
def iki_kiraci() -> object:
    _kiraci_ac(A_KIRACI, "Test A")
    _kiraci_ac(B_KIRACI, "Test B")
    yield
    _kiraci_sil(A_KIRACI, B_KIRACI)


def _sube(kod: str) -> Branch:
    return Branch(
        id=uuid4(),
        code=kod,
        name=f"{kod} şubesi",
        timezone="Europe/Istanbul",
        business_hours=uniform_hours(time(8, 0), time(23, 0)),
    ).validated()


def test_tc011_kiraci_yalitimi(iki_kiraci: object) -> None:
    """Bir kiracının deposu diğerinin satırını **göremez**.

    Yalıtım uygulama katmanında değil, veritabanında: adaptör hiçbir
    `WHERE tenant_id = ...` yazmıyor, kesen şey RLS politikası.
    """
    a = SqlOrganizationRepository(A_KIRACI)
    b = SqlOrganizationRepository(B_KIRACI)

    a.save_branch(_sube("AAA"))
    b.save_branch(_sube("BBB"))

    assert [s.code for s in a.branches()] == ["AAA"]
    assert [s.code for s in b.branches()] == ["BBB"]
    assert a.branch_by_code("BBB") is None
    assert b.branch_by_code("AAA") is None


def test_tc011_baska_kiracinin_kaydina_kimlikle_de_erisilemez(iki_kiraci: object) -> None:
    """Kimliği bilmek yetmez: satır başka kiracınınsa yok sayılır."""
    a = SqlOrganizationRepository(A_KIRACI)
    b = SqlOrganizationRepository(B_KIRACI)
    sube = _sube("AAA")
    a.save_branch(sube)

    assert a.branch(sube.id) is not None
    assert b.branch(sube.id) is None


def test_rls_kiraci_ayari_yoksa_hicbir_satir_gelmez() -> None:
    """Fail-closed: `app.tenant_id` ayarlanmazsa sorgu boş döner."""
    motor = create_db_engine()  # uygulama rolü, SET ROLE bağlantıda
    with motor.connect() as b:
        kullanici = b.execute(text("SELECT current_user")).scalar_one()
        bypass = b.execute(
            text("SELECT rolbypassrls FROM pg_roles WHERE rolname = current_user")
        ).scalar_one()
        sayi = b.execute(text("SELECT count(*) FROM branch")).scalar_one()

    assert kullanici == APP_ROLE
    assert bypass is False  # uygulama rolü RLS'i atlayamaz
    assert sayi == 0


def test_tohum_verisi_okunabiliyor() -> None:
    """Geliştirme kiracısında tohum duruyor (seed idempotent)."""
    org = SqlOrganizationRepository(DEV_TENANT)
    kodlar = {s.code for s in org.branches()}

    assert {"KDK", "BSK", "ALS"} <= kodlar


def test_sablon_surumu_bolum_ve_maddeleriyle_donuyor() -> None:
    """Eşleme kaybı olmamalı: bölüm, madde, seçenek ve aralık geri gelmeli."""
    sablonlar = SqlTemplateRepository(DEV_TENANT)
    kapanis = next(t for t in sablonlar.templates() if t.name.startswith("Kapanış"))
    surum = next(s for s in sablonlar.versions(kapanis.id) if s.status == "published")

    assert len(surum.sections) == 2
    assert surum.scored_item_count == 7
    sicaklik = next(i for i in surum.items if i.type == "temperature")
    assert (sicaklik.min_value, sicaklik.max_value, sicaklik.unit) == (0.0, 4.0, "°C")
    secimli = next(i for i in surum.items if i.type == "choice")
    assert [o.label for o in secimli.options] == ["Evet", "Hayır", "Uygun değil"]
    assert surum.publish_issues() == []


def test_sube_kaydi_gidip_geliyor(iki_kiraci: object) -> None:
    """Çalışma saatleri JSON'a yazılıp alan nesnesine geri dönüyor."""
    a = SqlOrganizationRepository(A_KIRACI)
    sube = _sube("RND")
    a.save_branch(sube)

    geri = a.branch_by_code("RND")

    assert geri is not None
    assert geri.name == sube.name
    assert geri.open_days == 7
    assert geri.business_hours[0] is not None
    assert geri.business_hours[0].close_time == time(23, 0)


def _alici(kiraci: UUID) -> User:
    """Bildirimin alıcısı gerçek bir kullanıcı olmalı: tabloda yabancı anahtar var.

    Kuyrukta silinmiş kullanıcıya ait kayıt kalmasın diye konuldu;
    adlar uydurma (ADR-0003).
    """
    kisi = User(
        id=uuid4(),
        full_name="Test Alıcı",
        phone=f"+90532{uuid4().int % 10_000_000:07d}",
        assignments=(RoleAssignment("admin"),),
    ).validated()
    SqlUserRepository(kiraci).save_user(kisi)
    return kisi


def _bildirim(baslik: str, alici: User) -> Notification:
    an = datetime.now(UTC)
    return Notification(
        id=uuid4(),
        kind="run_opened",
        channel="push",
        user_id=alici.id,
        title=baslik,
        body="gövde",
        send_at=an,
        created_at=an,
    ).validated()


def test_bildirim_kuyrugu_da_kiracilar_arasinda_yalitik(iki_kiraci: object) -> None:
    """Yeni tablo da RLS altında: 0002 göçü yetkiyi ve politikayı kurdu.

    Bildirim kuyruğu kim neyi görecek bilgisini taşıyor; sızması
    yalnızca gürültü değil, başka zincirin operasyonunu göstermek olur.
    """
    a = SqlNotificationRepository(A_KIRACI)
    b = SqlNotificationRepository(B_KIRACI)

    kayit = _bildirim("A kiracısının hatırlatması", _alici(A_KIRACI))
    a.save_notification(kayit)

    assert [n.title for n in a.notifications()] == ["A kiracısının hatırlatması"]
    assert b.notifications() == []
    assert b.notification(kayit.id) is None


def test_bildirim_teslimat_izi_gidip_geliyor(iki_kiraci: object) -> None:
    """Hata kodu ve deneme sayısı kalıcı: destek bunlara bakacak (FR-1005)."""
    depo = SqlNotificationRepository(A_KIRACI)
    kayit = _bildirim("Gönderilemeyen", _alici(A_KIRACI))
    depo.save_notification(kayit)

    an = datetime.now(UTC)
    depo.save_notification(kayit.failed(an, "surucu-yok", "push sürücüsü bağlı değil"))

    geri = depo.notification(kayit.id)
    assert geri is not None
    assert (geri.status, geri.error_code, geri.attempts) == ("failed", "surucu-yok", 1)


def _calistirma(kiraci: UUID) -> Run:
    """Kanıt bir çalıştırmaya bağlı (yabancı anahtar): zinciri gerçekten kuruyoruz.

    Şube → şablon → sürüm → plan → çalıştırma. Uydurma bir UUID ile
    kestirme yapmak, şemanın bütünlük kuralını test dışında bırakırdı.
    """
    org = SqlOrganizationRepository(kiraci)
    sube = _sube(f"K{uuid4().hex[:2].upper()}")
    org.save_branch(sube)

    sablonlar = SqlTemplateRepository(kiraci)
    sablon = Template(id=uuid4(), name="Kanıt denemesi")
    sablonlar.save_template(sablon)
    surum = TemplateVersion(
        id=uuid4(), template_id=sablon.id, version_no=1, status="published"
    ).validated()
    sablonlar.save_version(surum)

    planlar = SqlPlanRepository(kiraci)
    an = datetime.now(UTC)
    plan = Plan(
        id=uuid4(),
        name="Kanıt planı",
        template_version_id=surum.id,
        branch_ids=(sube.id,),
        rule=WindowRule(
            recurrence="daily",
            starts_on=an.date(),
            duration_minutes=60,
            start_time=time(9, 0),
        ),
    ).validated()
    planlar.save_plan(plan)

    run = Run(
        id=uuid4(),
        plan_id=plan.id,
        template_version_id=surum.id,
        branch_id=sube.id,
        business_day=an.date(),
        window_start=an,
        window_end=an + timedelta(hours=1),
        tolerance_end=an + timedelta(hours=2),
    )
    planlar.save_run(run)
    return run


def _kanit(run: Run, ozet: str) -> Evidence:
    return Evidence(
        id=uuid4(),
        run_id=run.id,
        answer_id=uuid4(),
        item_id=uuid4(),
        branch_id=run.branch_id,
        user_id=None,
        sha256=ozet,
        content_type="image/jpeg",
        size_bytes=1234,
        storage_key=f"evidence/{run.id}/{uuid4()}.jpg",
        created_at=datetime.now(UTC),
    ).validated()


def test_fr0614_ayni_ozet_veritabaninda_da_engellenir(iki_kiraci: object) -> None:
    """Tekillik şemaya yazılı: servis denetimi yarışta kaçabilir, indeks kaçmaz.

    Ürünün tek iddiası "kanıt gerçek"; onu yalnızca uygulama koduna
    bağlamak, iki eşzamanlı yüklemede iddiayı kaybetmek demek.
    """
    run = _calistirma(A_KIRACI)
    depo = SqlEvidenceRepository(A_KIRACI)
    ozet = "a" * 64
    depo.save_evidence(_kanit(run, ozet))

    with pytest.raises(IntegrityError):
        depo.save_evidence(_kanit(run, ozet))


def test_ayni_ozet_baska_kiracida_serbest(iki_kiraci: object) -> None:
    """Tekillik **hesap içinde** (FR-0614): başka zincirin fotoğrafı bizi bağlamaz."""
    ozet = "b" * 64
    SqlEvidenceRepository(A_KIRACI).save_evidence(_kanit(_calistirma(A_KIRACI), ozet))
    SqlEvidenceRepository(B_KIRACI).save_evidence(_kanit(_calistirma(B_KIRACI), ozet))

    assert SqlEvidenceRepository(A_KIRACI).evidence_by_digest(ozet) is not None
    assert SqlEvidenceRepository(B_KIRACI).evidence_by_digest(ozet) is not None


def test_kanit_silinebiliyor(iki_kiraci: object) -> None:
    """Doğrulanmamış yükleme silinir; tekillik kilidi onunla birlikte kalkar."""
    run = _calistirma(A_KIRACI)
    depo = SqlEvidenceRepository(A_KIRACI)
    ozet = "c" * 64
    kanit = _kanit(run, ozet)
    depo.save_evidence(kanit)

    depo.delete_evidence(kanit.id)

    assert depo.evidence_by_digest(ozet) is None
    depo.save_evidence(_kanit(run, ozet))  # aynı kare yeniden yüklenebilir
