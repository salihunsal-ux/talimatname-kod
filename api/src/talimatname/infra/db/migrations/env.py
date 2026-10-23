"""Alembic ortamı. Göçler **sahip rolüyle** koşar (RLS'i kurabilmek için)."""

from __future__ import annotations

from alembic import context

from talimatname.infra.db.models import Base
from talimatname.infra.db.session import create_db_engine

target_metadata = Base.metadata


def run_migrations_online() -> None:
    motor = create_db_engine(as_owner=True)
    with motor.connect() as baglanti:
        context.configure(
            connection=baglanti,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


def run_migrations_offline() -> None:
    raise SystemExit("Çevrimdışı göç kullanılmıyor: DATABASE_URL ile çalışın.")


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
