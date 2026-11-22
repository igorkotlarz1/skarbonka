"""After a manual correction: should this become a rule? (M8)"""

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from skarbonka.categorization.rules import RuleConditions, RuleSpec
from skarbonka.db.models import Allocation, Merchant, Rule, Transaction
from skarbonka.domain.categories import category_path
from skarbonka.domain.categorize import editable


class RuleSuggestion(BaseModel):
    """A ready `POST /rules` body plus how many other transactions it would recategorize now."""

    rule: RuleSpec
    would_change: int


def rule_suggestion(session: Session, allocation: Allocation) -> RuleSuggestion | None:
    """Propose "merchant → category" when the owner's choice differs from what the
    merchant's memory gives. None for splits, unknown merchants or a rule that exists."""
    t = allocation.transaction
    path = category_path(session, allocation.category_id)
    if path is None or t.merchant_id is None or len(t.allocations) != 1:
        return None
    merchant = session.get_one(Merchant, t.merchant_id)
    if merchant.default_category_id == allocation.category_id:
        return None
    name = f"{merchant.name} → {path}"
    if session.scalar(select(Rule.id).where(Rule.name == name)) is not None:
        return None
    others = session.scalars(
        select(Transaction).where(Transaction.merchant_id == merchant.id, Transaction.id != t.id)
    )
    would_change = 0
    for other in others:
        candidate = editable(other)
        if candidate is not None and candidate.category_id != allocation.category_id:
            would_change += 1
    rule = RuleSpec(name=name, when=RuleConditions(merchant=merchant.name), category=path)
    return RuleSuggestion(rule=rule, would_change=would_change)
