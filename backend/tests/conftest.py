"""Shared fixtures."""

import os
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from skarbonka.api.deps import get_session
from skarbonka.api.main import create_app
from skarbonka.db.session import make_engine
from tests.db_utils import recreate_database, run_alembic

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


TEST_DB_NAME = "skarbonka_test"
SCRATCH_DB_NAME = "skarbonka_migrations"


@pytest.fixture(scope="session")
def test_database_url(database_url: str) -> str:
    """A fresh `skarbonka_test` database migrated to head, shared by the whole run."""
    url = recreate_database(database_url, TEST_DB_NAME)
    run_alembic(url, "upgrade", "head")
    return url


@pytest.fixture
def scratch_database_url(database_url: str) -> str:
    """An empty database for migration round trips."""
    return recreate_database(database_url, SCRATCH_DB_NAME)


@pytest.fixture
def db(test_database_url: str) -> Iterator[Session]:
    """A session inside a transaction that is rolled back after the test.

    `commit()` in code under test only releases a savepoint, so tests never leak state.
    """
    engine = make_engine(test_database_url)
    connection = engine.connect()
    outer = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        outer.rollback()
        connection.close()
        engine.dispose()


@pytest.fixture
def client(db: Session) -> Iterator[TestClient]:
    """API client whose requests share the rolled-back test session."""
    app = create_app()
    app.dependency_overrides[get_session] = lambda: db
    with TestClient(app) as test_client:
        yield test_client
