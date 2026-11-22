"""FastAPI dependencies."""

from collections.abc import Iterator
from functools import lru_cache
from pathlib import Path

from sqlalchemy.orm import Session, sessionmaker

from skarbonka.categorization.classifier import MODEL_FILE, CategoryModel, CategoryPredictor
from skarbonka.config import get_settings
from skarbonka.db.session import make_engine, make_session_factory


@lru_cache
def session_factory() -> sessionmaker[Session]:
    return make_session_factory(make_engine(get_settings().database_url))


def _load_model(path: Path, mtime: float) -> CategoryModel:
    return CategoryModel.load(path)


_cached_model = lru_cache(maxsize=1)(_load_model)


def get_category_model() -> CategoryPredictor | None:
    """The trained classifier from `models/`, reloaded when the file changes; None if absent."""
    path = get_settings().models_dir / MODEL_FILE
    if not path.is_file():
        return None
    return _cached_model(path, path.stat().st_mtime)


def get_ml_threshold() -> float:
    return get_settings().ml_threshold


def get_session() -> Iterator[Session]:
    """One session per request; the endpoint decides when to commit."""
    with session_factory()() as session:
        yield session
