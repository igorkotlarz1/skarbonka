"""Category lookups by "Parent/Child" path."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from skarbonka.db.models import Category


class UnknownCategoryError(LookupError):
    pass


def find_category(session: Session, path: str) -> Category | None:
    parent_name, _, child_name = path.partition("/")
    parent = session.scalar(
        select(Category).where(Category.parent_id.is_(None), Category.name == parent_name)
    )
    if parent is None or not child_name:
        return parent
    return session.scalar(
        select(Category).where(Category.parent_id == parent.id, Category.name == child_name)
    )


def category_by_path(session: Session, path: str) -> Category:
    category = find_category(session, path)
    if category is None:
        raise UnknownCategoryError(f"unknown category: {path!r}")
    return category


def category_path(session: Session, category_id: int | None) -> str | None:
    if category_id is None:
        return None
    category = session.get_one(Category, category_id)
    if category.parent_id is None:
        return category.name
    return f"{session.get_one(Category, category.parent_id).name}/{category.name}"
