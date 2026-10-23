"""Veritabanı bağlantısı ve kiracı oturumu (ADR-0014 md.4).

İki katmanlı savunmanın alt katmanı burada kurulur:

* Uygulama **asla sahip rolüyle çalışmaz**. Bağlantı açılır açılmaz
  `SET ROLE` ile `BYPASSRLS` taşımayan uygulama rolüne geçilir; göçler
  bunun dışındadır (sahip rolüyle koşar).
* Her iş birimi `SET LOCAL app.tenant_id` ile hangi kiracıda çalıştığını
  söyler. Söylemezse RLS politikası **hiçbir satır** döndürmez —
  unutmak veri sızdırmaz, boş liste verir.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache
from uuid import UUID

from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

from talimatname.settings import Settings, get_settings

#: Uygulamanın kullandığı rol. Göç bu rolü `NOBYPASSRLS` olarak yaratır.
APP_ROLE = "talimatname_app"


def normalize_url(url: str) -> str:
    """Sağlayıcının verdiği dizeyi SQLAlchemy sürücüsüne çevirir.

    Neon ve çoğu sağlayıcı `postgresql://…` verir; biz psycopg 3
    kullanıyoruz. Kullanıcının dizeyi elle düzenlemesini istemiyoruz:
    yanlış yazma riski, kazandıracağı şeyden büyük.
    """
    if url.startswith("postgresql+"):
        return url
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://") :]
    return url.replace("postgresql://", "postgresql+psycopg://", 1)


def create_db_engine(settings: Settings | None = None, *, as_owner: bool = False) -> Engine:
    """Motor üretir. `as_owner=True` yalnızca göçler içindir."""
    ayar = settings or get_settings()
    motor = create_engine(
        normalize_url(ayar.require_database_url()),
        pool_pre_ping=True,  # uykuya geçen sunucuda ilk istek düşmesin
        pool_size=5,
        max_overflow=5,
        future=True,
    )
    if as_owner:
        return motor

    @event.listens_for(motor, "connect")
    def _rol_degistir(dbapi_connection: object, _record: object) -> None:
        """Bağlantı açılır açılmaz uygulama rolüne geç (RLS etkin olsun)."""
        imlec = dbapi_connection.cursor()  # type: ignore[attr-defined]
        try:
            imlec.execute(f'SET ROLE "{APP_ROLE}"')
        finally:
            imlec.close()

    return motor


@lru_cache
def _engine() -> Engine:
    return create_db_engine()


@lru_cache
def _session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=_engine(), expire_on_commit=False, future=True)


@contextmanager
def tenant_session(tenant_id: UUID) -> Iterator[Session]:
    """Kiracı bağlamında bir iş birimi.

    `SET LOCAL` kullanıyoruz: ayar yalnızca bu işlem (transaction) için
    geçerli, bağlantı havuza dönünce kendiliğinden düşer. Havuzdan gelen
    bir bağlantının önceki kiracının ayarını taşıması mümkün değil.
    """
    oturum = _session_factory()()
    try:
        oturum.execute(
            text("SELECT set_config('app.tenant_id', :kiraci, true)"),
            {"kiraci": str(tenant_id)},
        )
        yield oturum
        oturum.commit()
    except Exception:
        oturum.rollback()
        raise
    finally:
        oturum.close()
