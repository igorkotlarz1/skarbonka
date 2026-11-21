"""FastAPI dependencies."""

from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy.orm import Session, sessionmaker

from skarbonka.config import get_settings
from skarbonka.db.session import make_engine, make_session_factory


@lru_cache
def session_factory() -> sessionmaker[Session]:
    return make_session_factory(make_engine(get_settings().database_url))


def get_session() -> Iterator[Session]:
    """One session per request; the endpoint decides when to commit."""
    with session_factory()() as session:
        yield session
