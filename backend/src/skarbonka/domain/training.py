"""Labelled examples for the classifier, taken from the owner's own database.

Labels come from manual decisions (gold), rules and merchant memory (silver). The model's
own outputs (`ml`) are never fed back, and transfers between own accounts are left out.
"""

from collections import Counter

from sqlalchemy import select
from sqlalchemy.orm import Session

from skarbonka.categorization.synthetic_labels import LabelledExample
from skarbonka.db.models import Allocation, Category, Merchant, Transaction
from skarbonka.domain.categories import category_path
from skarbonka.domain.categorize import view

LABEL_SOURCES = ("manual", "rule", "merchant")


def labelled_examples(session: Session) -> tuple[list[LabelledExample], Counter[str]]:
    """Examples plus how many labels came from each source (manual = hand-confirmed)."""
    excluded = set(
        session.scalars(select(Category.id).where(Category.excluded_from_settlement.is_(True)))
    )
    rows = session.execute(
        select(Transaction, Allocation)
        .join(Allocation, Allocation.transaction_id == Transaction.id)
        .where(Allocation.source.in_(LABEL_SOURCES), Allocation.category_id.is_not(None))
    ).all()
    examples: list[LabelledExample] = []
    sources: Counter[str] = Counter()
    for t, a in rows:
        if len(t.allocations) != 1 or a.category_id is None or a.category_id in excluded:
            continue
        merchant = session.get(Merchant, t.merchant_id) if t.merchant_id else None
        label = category_path(session, a.category_id)
        if label is None:
            continue
        group = merchant.name if merchant else t.counterparty.strip() or f"tx-{t.id}"
        examples.append(LabelledExample(view(t, merchant), label, group))
        sources[a.source] += 1
    return examples, sources
