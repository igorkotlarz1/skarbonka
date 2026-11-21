"""Alembic environment. The database URL comes from Skarbonka settings, not alembic.ini."""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from skarbonka.config import Settings
from skarbonka.db import models  # noqa: F401  (registers tables on Base.metadata)
from skarbonka.db.base import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Models are imported above so autogenerate sees every table.
target_metadata = Base.metadata


def database_url() -> str:
    """A URL passed by tests, then `-x url=...`, then SKARBONKA_DATABASE_URL."""
    url = config.attributes.get("url") or context.get_x_argument(as_dictionary=True).get("url")
    return str(url) if url else Settings().database_url


def run_migrations_offline() -> None:
    context.configure(
        url=database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(database_url(), poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
