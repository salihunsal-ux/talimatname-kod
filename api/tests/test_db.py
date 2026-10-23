"""PostgreSQL adaptörleri ve kiracı yalıtımı (TC-011, ADR-0014 md.4).

Bu testler **çalışan bir veritabanı ister**: `DATABASE_URL` yoksa sebebi
yazılarak atlanır (sessiz atlama yok). Kendi kiracısını açar, işini
yapar, sonra siler — paylaşılan geliştirme veritabanını kirletmez.
"""

from __future__ import annotations

from datetime import UTC, datetime, time
from uuid import UUID, uuid4, uuid5

import pytest
from sqlalchemy import text

from talimatname.domain.organization import Branch, uniform_hours
from talimatname.settings import get_settings

pytestmark = pytest.mark.db

if get_settings().database_url is None:  # pragma: no cover - ortam bağımlı
    pytest.skip(
        "DATABASE_URL tanımlı değil: veritabanı testleri atlandı "
        "(bkz. infra/veritabani-kurulum.md)",
        allow_module_level=True,
    )

from talimatname.infra.db.adapters import (  # noqa: E402
    SqlOrganizationRepository,
    SqlTemplateRepository,
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
