"""Rules, rule preview, re-categorization and manual labels."""

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from skarbonka.api.imports import ModelDep, SessionDep, ThresholdDep
from skarbonka.categorization.rules import RuleSpec
from skarbonka.db.models import Allocation, AuditLog, Merchant, Rule, Transaction
from skarbonka.domain.categories import UnknownCategoryError, category_by_path, category_path
from skarbonka.domain.categorize import (
    CategorizeStats,
    active_rules,
    categorize,
    editable,
    proposed,
)

router = APIRouter(tags=["categorization"])

PREVIEW_SAMPLE = 10


class RuleOut(BaseModel):
    id: int
    rule: RuleSpec


class PreviewRow(BaseModel):
    transaction_id: int
    transaction_date: date
    counterparty: str
    amount: Decimal
    category_now: str | None
    category_after: str | None
    personal_now: bool
    personal_after: bool


class PreviewOut(BaseModel):
    matched: int
    would_change: int
    sample: list[PreviewRow]


class ManualCategory(BaseModel):
    category: str | None
    personal: bool | None = None
    remember_for_merchant: bool = False


def _unprocessable(exc: Exception) -> HTTPException:
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc))


@router.get("/rules")
def list_rules(session: SessionDep) -> list[RuleSpec]:
    return active_rules(session)


@router.post("/rules", status_code=status.HTTP_201_CREATED)
def create_rule(
    spec: RuleSpec, session: SessionDep, model: ModelDep, threshold: ThresholdDep
) -> RuleOut:
    try:
        category_id = category_by_path(session, spec.category).id if spec.category else None
    except UnknownCategoryError as exc:
        raise _unprocessable(exc) from exc
    rule = Rule(
        name=spec.name,
        priority=spec.priority,
        conditions=spec.when.model_dump(mode="json", exclude_none=True),
        category_id=category_id,
        personal=spec.personal,
        active=True,
    )
    session.add(rule)
    try:
        session.flush()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, f"rule {spec.name!r} exists") from exc
    categorize(session, model=model, threshold=threshold)
    session.commit()
    return RuleOut(id=rule.id, rule=spec)


@router.post("/rules/preview")
def preview_rule(spec: RuleSpec, session: SessionDep) -> PreviewOut:
    """What would this rule change if it were added with its priority? Writes nothing."""
    if spec.category:
        try:
            category_by_path(session, spec.category)
        except UnknownCategoryError as exc:
            raise _unprocessable(exc) from exc
    rules_now = active_rules(session)
    rules_after = [*rules_now, spec]
    single_rule = [spec]
    matched, changes = 0, []
    for t in session.scalars(select(Transaction).order_by(Transaction.transaction_date.desc())):
        allocation = editable(t)
        merchant = session.get(Merchant, t.merchant_id) if t.merchant_id else None
        if allocation is None or proposed(session, single_rule, t, merchant)[2] != "rule":
            continue
        matched += 1
        category_id, personal, _ = proposed(session, rules_after, t, merchant)
        if (category_id, personal) != (allocation.category_id, allocation.personal):
            changes.append(PreviewRow(
                transaction_id=t.id, transaction_date=t.transaction_date,
                counterparty=t.counterparty, amount=t.amount,
                category_now=category_path(session, allocation.category_id),
                category_after=category_path(session, category_id),
                personal_now=allocation.personal, personal_after=personal,
            ))  # fmt: skip
    return PreviewOut(matched=matched, would_change=len(changes), sample=changes[:PREVIEW_SAMPLE])


@router.post("/categorize")
def recategorize(session: SessionDep, model: ModelDep, threshold: ThresholdDep) -> CategorizeStats:
    """Re-apply merchants, rules, the classifier and transfer detection (manual stays)."""
    stats = categorize(session, model=model, threshold=threshold)
    session.commit()
    return stats


@router.put("/transactions/{transaction_id}/category")
def set_category(
    transaction_id: int,
    body: ManualCategory,
    session: SessionDep,
    model: ModelDep,
    threshold: ThresholdDep,
) -> dict[str, str]:
    t = session.get(Transaction, transaction_id)
    if t is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such transaction")
    if len(t.allocations) != 1:
        raise HTTPException(status.HTTP_409_CONFLICT, "split transaction: edit its parts")
    try:
        category = category_by_path(session, body.category) if body.category else None
    except UnknownCategoryError as exc:
        raise _unprocessable(exc) from exc

    allocation = t.allocations[0]
    before = {"category_id": allocation.category_id, "personal": allocation.personal,
              "source": allocation.source}  # fmt: skip
    allocation.category_id = category.id if category else None
    if body.personal is not None:
        allocation.personal = body.personal
    allocation.source = "manual"
    allocation.suggested_category_id = None
    session.add(AuditLog(
        entity="allocation", entity_id=allocation.id, action="manual_category", before=before,
        after={"category_id": allocation.category_id, "personal": allocation.personal,
               "source": "manual"},
    ))  # fmt: skip
    if body.remember_for_merchant and category is not None and t.merchant_id is not None:
        merchant = session.get_one(Merchant, t.merchant_id)
        merchant.default_category_id = category.id
        same_merchant = session.scalars(
            select(Transaction).where(Transaction.merchant_id == merchant.id)
        )
        categorize(session, same_merchant, model=model, threshold=threshold)
    session.commit()
    return {"status": "ok"}


class ReviewRow(BaseModel):
    transaction_id: int
    transaction_date: date
    counterparty: str
    title: str
    amount: Decimal
    suggested_category: str | None
    confidence: Decimal | None


@router.get("/review-queue")
def review_queue(session: SessionDep, limit: int = 100) -> list[ReviewRow]:
    """Transactions still without a category, newest first, with the model's guess if any."""
    rows = session.execute(
        select(Transaction, Allocation)
        .join(Allocation, Allocation.transaction_id == Transaction.id)
        .where(Allocation.category_id.is_(None))
        .order_by(Transaction.transaction_date.desc(), Transaction.id.desc())
        .limit(limit)
    ).all()
    return [
        ReviewRow(
            transaction_id=t.id, transaction_date=t.transaction_date,
            counterparty=t.counterparty, title=t.title, amount=t.amount,
            suggested_category=category_path(session, a.suggested_category_id),
            confidence=a.confidence,
        )
        for t, a in rows
    ]  # fmt: skip
