"""Shared fixtures."""

import os

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from skarbonka.db.session import make_engine

DEFAULT_TEST_DATABASE_URL = "postgresql+psycopg://skarbonka:skarbonka@localhost:5432/skarbonka"


@pytest.fixture(scope="session")
def database_url() -> str:
    """URL of the test database; fails (never skips) when Postgres is down."""
    url = os.environ.get("SKARBONKA_TEST_DATABASE_URL", DEFAULT_TEST_DATABASE_URL)
    engine = make_engine(url)
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except OperationalError as exc:
        pytest.fail(
            "Postgres is not reachable. Start it with `docker compose up -d db` "
            f"from the repo root, or set SKARBONKA_TEST_DATABASE_URL. ({exc.orig})"
        )
    finally:
        engine.dispose()
    return url
