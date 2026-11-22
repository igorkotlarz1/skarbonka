"""Apply merchants, rules and own-account transfer detection to allocations.

Layers, strongest first: manual change → owner's rules → merchant memory → (ML, LLM later).
Allocations the owner changed by hand (`source = "manual"`) and split transactions are never
touched here.
"""

from collections.abc import Iterable
from datetime import timedelta

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from skarbonka.categorization.merchants import (
    best_keyword_match,
    display_name,
    merchant_key,
    parse_counterparty,
)
from skarbonka.categorization.rules import RuleConditions, RuleSpec, TransactionView, evaluate
from skarbonka.db.models import (
    Allocation,
    Category,
    Merchant,
    MerchantAlias,
    Rule,
    Transaction,
)
from skarbonka.domain.categories import category_path, find_category

INTERNAL_CATEGORY = "Przelewy własne"
INTERNAL_WINDOW = timedelta(days=2)


class CategorizeStats(BaseModel):
    merchants_linked: int = 0
    allocations_changed: int = 0
    internal_pairs: int = 0


def resolve_merchant(session: Session, counterparty: str) -> Merchant | None:
    """Alias first, then whole-word keywords, else a new merchant with its own alias."""
    parsed = parse_counterparty(counterparty)
    key = merchant_key(parsed.name)
    if not key:
        return None
    alias = session.scalar(select(MerchantAlias).where(MerchantAlias.alias == key))
    if alias is not None:
        return session.get_one(Merchant, alias.merchant_id)

    merchants = list(session.scalars(select(Merchant)))
    by_name = {m.name: m for m in merchants}
    matched = best_keyword_match(parsed.name, {m.name: m.keywords for m in merchants})
    merchant = by_name.get(matched) if matched else by_name.get(display_name(key))
    if merchant is None:
        merchant = Merchant(name=display_name(key), keywords=[])
        session.add(merchant)
        session.flush()
    session.add(MerchantAlias(merchant_id=merchant.id, alias=key))
    session.flush()
    return merchant


def view(t: Transaction, merchant: Merchant | None) -> TransactionView:
    return TransactionView(
        counterparty=t.counterparty,
        title=t.title,
        amount=t.amount,
        account=t.account.name,
        transaction_date=t.transaction_date,
        operation_kind=t.operation_kind,
        merchant=merchant.name if merchant else None,
    )


def active_rules(session: Session) -> list[RuleSpec]:
    rules = session.scalars(select(Rule).where(Rule.active.is_(True)).order_by(Rule.id))
    return [
        RuleSpec(
            name=r.name,
            priority=r.priority,
            when=RuleConditions.model_validate(r.conditions),
            category=category_path(session, r.category_id),
            personal=r.personal,
        )
        for r in rules
    ]


def proposed(
    session: Session, rules: list[RuleSpec], t: Transaction, merchant: Merchant | None
) -> tuple[int | None, bool, str]:
    """(category id, personal, source) the automatic layers propose for one transaction."""
    outcome = evaluate(rules, view(t, merchant))
    category = find_category(session, outcome.category) if outcome.category else None
    source = "rule" if not outcome.empty else "import"
    category_id = category.id if category else None
    if category_id is None and merchant is not None and merchant.default_category_id:
        category_id = merchant.default_category_id
        source = "rule" if outcome.personal is not None else "merchant"
    return category_id, bool(outcome.personal), source


def editable(t: Transaction) -> Allocation | None:
    """The single non-manual allocation the automatic layers may change, if any."""
    if len(t.allocations) != 1 or t.allocations[0].source == "manual":
        return None
    return t.allocations[0]


def categorize(
    session: Session, transactions: Iterable[Transaction] | None = None
) -> CategorizeStats:
    """Link merchants and (re)apply rules and merchant memory. Flushes, never commits."""
    stats = CategorizeStats()
    rows = (
        list(transactions)
        if transactions is not None
        else list(session.scalars(select(Transaction)))
    )
    rules = active_rules(session)
    for t in rows:
        if t.merchant_id is None:
            merchant = resolve_merchant(session, t.counterparty)
            if merchant is not None:
                t.merchant_id = merchant.id
                stats.merchants_linked += 1
        allocation = editable(t)
        if allocation is None:
            continue
        merchant = session.get(Merchant, t.merchant_id) if t.merchant_id else None
        category_id, personal, source = proposed(session, rules, t, merchant)
        if (allocation.category_id, allocation.personal, allocation.source) != (
            category_id, personal, source,
        ):  # fmt: skip
            allocation.category_id, allocation.personal, allocation.source = (
                category_id, personal, source,
            )  # fmt: skip
            stats.allocations_changed += 1
    stats.internal_pairs = mark_internal_transfers(session)
    session.flush()
    return stats


def mark_internal_transfers(session: Session) -> int:
    """Pair an outflow with an equal inflow on another own account within ±2 days.

    Both legs get the system category that never reaches a settlement.
    """
    internal = find_category(session, INTERNAL_CATEGORY)
    if internal is None:
        return 0
    rows = list(session.scalars(select(Transaction).order_by(Transaction.transaction_date)))
    inflows = [t for t in rows if t.amount > 0]
    used: set[int] = set()
    pairs = 0
    for out in (t for t in rows if t.amount < 0):
        match = next(
            (
                t for t in inflows
                if t.id not in used and t.amount == -out.amount and t.account_id != out.account_id
                and abs(t.transaction_date - out.transaction_date) <= INTERNAL_WINDOW
            ),
            None,
        )  # fmt: skip
        if match is None:
            continue
        used.add(match.id)
        pairs += 1
        for leg in (out, match):
            allocation = editable(leg)
            if allocation is not None:
                allocation.category_id, allocation.personal, allocation.source = (
                    internal.id, False, "rule",
                )  # fmt: skip
    return pairs


def is_settleable(session: Session, allocation: Allocation) -> bool:
    """May this allocation go to the parents? Not personal and not an excluded category."""
    if allocation.personal:
        return False
    if allocation.category_id is None:
        return True
    category = session.get_one(Category, allocation.category_id)
    if category.excluded_from_settlement:
        return False
    parent = session.get(Category, category.parent_id) if category.parent_id else None
    return not (parent is not None and parent.excluded_from_settlement)
