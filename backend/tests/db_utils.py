"""Helpers for tests that need their own Postgres database."""

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import make_url, text

from skarbonka.db.session import make_engine

BACKEND_DIR = Path(__file__).resolve().parents[1]


def with_database(url: str, name: str) -> str:
    """Same server and credentials, another database name."""
    return make_url(url).set(database=name).render_as_string(hide_password=False)


def recreate_database(server_url: str, name: str) -> str:
    """Drop and create `name` on the server behind `server_url`; return its URL."""
    engine = make_engine(server_url).execution_options(isolation_level="AUTOCOMMIT")
    with engine.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        conn.execute(text(f'CREATE DATABASE "{name}"'))
    engine.dispose()
    return with_database(server_url, name)


def run_alembic(url: str, action: str, revision: str) -> None:
    """Run `alembic upgrade|downgrade <revision>` against `url`."""
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "src/skarbonka/db/migrations"))
    config.cmd_opts = None
    config.attributes["url"] = url
    getattr(command, action)(config, revision)
