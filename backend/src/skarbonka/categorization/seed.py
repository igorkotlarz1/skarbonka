"""Seed categories, merchants and rules from `categories.toml` (owner-editable).

Seeding only adds and updates. It never deletes, never changes a merchant's default category
the owner already set, and never touches allocations.
"""

import tomllib
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from skarbonka.categorization.rules import RuleSpec
from skarbonka.db.models import Category, Merchant, Rule
from skarbonka.domain.categories import category_by_path

DEFAULT_SEED_FILE = Path(__file__).with_name("categories.toml")


class CategorySeed(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    children: list[str] = []
    excluded_from_settlement: bool = False


class MerchantSeed(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    keywords: list[str] = Field(min_length=1)
    category: str | None = None


class SeedConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: list[CategorySeed] = []
    merchant: list[MerchantSeed] = []
    rule: list[RuleSpec] = []


def load_seed(path: Path = DEFAULT_SEED_FILE) -> SeedConfig:
    with path.open("rb") as handle:
        return SeedConfig.model_validate(tomllib.load(handle))


def _category(session: Session, name: str, parent: Category | None) -> Category:
    parent_id = parent.id if parent else None
    found = session.scalar(
        select(Category).where(
            Category.name == name,
            Category.parent_id.is_(None) if parent is None else Category.parent_id == parent_id,
        )
    )
    if found is None:
        found = Category(name=name, parent_id=parent_id)
        session.add(found)
        session.flush()
    return found


def seed(session: Session, config: SeedConfig) -> None:
    for c in config.category:
        parent = _category(session, c.name, None)
        parent.excluded_from_settlement = c.excluded_from_settlement
        for child in c.children:
            _category(session, child, parent).excluded_from_settlement = c.excluded_from_settlement

    for m in config.merchant:
        merchant = session.scalar(select(Merchant).where(Merchant.name == m.name))
        if merchant is None:
            merchant = Merchant(name=m.name, keywords=[])
            session.add(merchant)
        merchant.keywords = sorted({*merchant.keywords, *(k.upper() for k in m.keywords)})
        if m.category and merchant.default_category_id is None:
            merchant.default_category_id = category_by_path(session, m.category).id

    for r in config.rule:
        if r.category:
            category_by_path(session, r.category)  # fail early on a typo
        rule = session.scalar(select(Rule).where(Rule.name == r.name))
        if rule is None:
            rule = Rule(name=r.name)
            session.add(rule)
        rule.priority = r.priority
        rule.conditions = r.when.model_dump(mode="json", exclude_none=True)
        rule.category_id = category_by_path(session, r.category).id if r.category else None
        rule.personal = r.personal
        rule.active = True
    session.flush()
