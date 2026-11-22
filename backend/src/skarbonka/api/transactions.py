"""Transaction list, categories, and the owner's edits to allocations (M7, M8)."""

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from datetime import date
from decimal import Decimal
from typing import Self

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.orm import Session, selectinload

from skarbonka.api.imports import ModelDep, SessionDep, ThresholdDep
from skarbonka.db.models import Allocation, Category, Merchant, Transaction
from skarbonka.domain.allocations import owner_change
from skarbonka.domain.categories import UnknownCategoryError, category_by_path
from skarbonka.domain.categorize import categorize
from skarbonka.domain.splits import SettledError, SplitError, SplitPart, split_transaction
from skarbonka.domain.suggestions import RuleSuggestion, rule_suggestion

router = APIRouter(tags=["transactions"])

MAX_PAGE_SIZE = 500
MAX_BULK = 1000


class CategoryOut(BaseModel):
    id: int
    path: str
    name: str
    parent: str | None
    excluded_from_settlement: bool


class AllocationOut(BaseModel):
    id: int
    amount: Decimal
    category: str | None
    personal: bool
    source: str
    confidence: Decimal | None
    suggested_category: str | None


class TransactionOut(BaseModel):
    id: int
    transaction_date: date
    booking_date: date | None
    amount: Decimal
    currency: str
    counterparty: str
    title: str
    account: str
    merchant: str | None
    allocations: list[AllocationOut]


class TransactionPage(BaseModel):
    items: list[TransactionOut]
    total: int
    page: int
    page_size: int


class AllocationPatch(BaseModel):
    """Only the fields sent are changed; `"category": null` clears the category."""

    category: str | None = None
    personal: bool | None = None

    @model_validator(mode="after")
    def _something(self) -> Self:
        if not self.model_fields_set & {"category", "personal"}:
            raise ValueError("send category, personal, or both")
        return self


class BulkChange(AllocationPatch):
    allocation_ids: list[int] = Field(min_length=1, max_length=MAX_BULK)


class BulkResult(BaseModel):
    updated: int


class PatchResult(AllocationOut):
    """The changed allocation, plus a rule proposal when a category was set by hand."""

    rule_suggestion: RuleSuggestion | None = None


class AcceptBody(BaseModel):
    remember_for_merchant: bool = False


class SplitPartIn(BaseModel):
    amount: Decimal
    category: str | None = None
    personal: bool = False


class SplitIn(BaseModel):
    parts: list[SplitPartIn] = Field(min_length=1, max_length=50)


@contextmanager
def atomic(session: Session) -> Iterator[None]:
    """Commit everything the block did, the audit rows included, or roll all of it back."""
    try:
        yield
        session.commit()
    except BaseException:
        session.rollback()
        raise


def category_paths(session: Session) -> dict[int, str]:
    categories = list(session.scalars(select(Category)))
    names = {c.id: c.name for c in categories}
    return {c.id: f"{names[c.parent_id]}/{c.name}" if c.parent_id else c.name for c in categories}


def _category_id(session: Session, path: str | None) -> int | None:
    if path is None:
        return None
    try:
        return category_by_path(session, path).id
    except UnknownCategoryError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc


def _allocation_out(a: Allocation, paths: dict[int, str]) -> AllocationOut:
    return AllocationOut(
        id=a.id,
        amount=a.amount,
        category=paths.get(a.category_id) if a.category_id else None,
        personal=a.personal,
        source=a.source,
        confidence=a.confidence,
        suggested_category=paths.get(a.suggested_category_id) if a.suggested_category_id else None,
    )


def transactions_out(session: Session, rows: Sequence[Transaction]) -> list[TransactionOut]:
    paths = category_paths(session)
    merchant_ids = {t.merchant_id for t in rows if t.merchant_id}
    merchants = {
        m.id: m.name for m in session.scalars(select(Merchant).where(Merchant.id.in_(merchant_ids)))
    }
    return [
        TransactionOut(
            id=t.id,
            transaction_date=t.transaction_date,
            booking_date=t.booking_date,
            amount=t.amount,
            currency=t.currency,
            counterparty=t.counterparty.strip(),
            title=t.title.strip(),
            account=t.account.name,
            merchant=merchants.get(t.merchant_id) if t.merchant_id else None,
            allocations=[_allocation_out(a, paths) for a in t.allocations],
        )
        for t in rows
    ]


@router.get("/categories")
def list_categories(session: SessionDep) -> list[CategoryOut]:
    categories = list(session.scalars(select(Category).order_by(Category.id)))
    names = {c.id: c.name for c in categories}
    rows = [
        CategoryOut(
            id=c.id,
            path=f"{names[c.parent_id]}/{c.name}" if c.parent_id else c.name,
            name=c.name,
            parent=names[c.parent_id] if c.parent_id else None,
            excluded_from_settlement=c.excluded_from_settlement,
        )
        for c in categories
    ]
    return sorted(rows, key=lambda r: r.path)


@router.get("/transactions")
def list_transactions(
    session: SessionDep,
    date_from: date | None = None,
    date_to: date | None = None,
    category: str | None = None,
    merchant: str | None = None,
    personal: bool | None = None,
    needs_review: bool | None = None,
    q: str | None = Query(default=None, max_length=200),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=MAX_PAGE_SIZE),
) -> TransactionPage:
    """Newest first. A parent category also matches its children."""
    conditions = []
    if date_from:
        conditions.append(Transaction.transaction_date >= date_from)
    if date_to:
        conditions.append(Transaction.transaction_date <= date_to)
    if category:
        chosen = _category_id(session, category)
        ids = [chosen, *session.scalars(select(Category.id).where(Category.parent_id == chosen))]
        conditions.append(Transaction.allocations.any(Allocation.category_id.in_(ids)))
    if merchant:
        same_name = func.lower(Merchant.name) == merchant.lower()
        conditions.append(exists().where(and_(Merchant.id == Transaction.merchant_id, same_name)))
    if personal is not None:
        conditions.append(Transaction.allocations.any(Allocation.personal.is_(personal)))
    if needs_review is not None:
        missing = Transaction.allocations.any(Allocation.category_id.is_(None))
        conditions.append(missing if needs_review else ~missing)
    if q:
        pattern = f"%{q.replace('%', r'\%').replace('_', r'\_')}%"
        conditions.append(
            or_(Transaction.counterparty.ilike(pattern), Transaction.title.ilike(pattern))
        )

    total = session.scalar(select(func.count()).select_from(Transaction).where(*conditions)) or 0
    rows = session.scalars(
        select(Transaction)
        .where(*conditions)
        .options(selectinload(Transaction.allocations), selectinload(Transaction.account))
        .order_by(Transaction.transaction_date.desc(), Transaction.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return TransactionPage(
        items=transactions_out(session, rows), total=total, page=page, page_size=page_size
    )


@router.patch("/allocations/{allocation_id}")
def patch_allocation(allocation_id: int, body: AllocationPatch, session: SessionDep) -> PatchResult:
    allocation = session.get(Allocation, allocation_id)
    if allocation is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such allocation")
    set_category = "category" in body.model_fields_set
    with atomic(session):
        owner_change(
            session,
            allocation,
            set_category=set_category,
            category_id=_category_id(session, body.category) if set_category else None,
            personal=body.personal,
            action="patch",
        )
    out = _allocation_out(allocation, category_paths(session))
    suggestion = rule_suggestion(session, allocation) if set_category else None
    return PatchResult(**out.model_dump(), rule_suggestion=suggestion)


@router.post("/allocations/{allocation_id}/accept")
def accept_suggestion(
    allocation_id: int,
    body: AcceptBody,
    session: SessionDep,
    model: ModelDep,
    threshold: ThresholdDep,
) -> AllocationOut:
    """The owner's one click on a proposal: it becomes a manual category, optionally the
    merchant's default (which then recategorizes the merchant's other automatic rows)."""
    allocation = session.get(Allocation, allocation_id)
    if allocation is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such allocation")
    suggested = allocation.suggested_category_id
    if suggested is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "nothing to accept")
    with atomic(session):
        owner_change(
            session,
            allocation,
            set_category=True,
            category_id=suggested,
            personal=None,
            action="accept",
        )
        merchant_id = allocation.transaction.merchant_id
        if body.remember_for_merchant and merchant_id is not None:
            session.get_one(Merchant, merchant_id).default_category_id = suggested
            same = session.scalars(
                select(Transaction).where(Transaction.merchant_id == merchant_id)
            )
            categorize(session, same, model=model, threshold=threshold)
    return _allocation_out(allocation, category_paths(session))


@router.put("/transactions/{transaction_id}/splits")
def put_splits(transaction_id: int, body: SplitIn, session: SessionDep) -> TransactionOut:
    """Split a transaction into parts that sum to it exactly; one part merges it back."""
    t = session.get(Transaction, transaction_id)
    if t is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such transaction")
    parts = [SplitPart(p.amount, _category_id(session, p.category), p.personal) for p in body.parts]
    try:
        with atomic(session):
            split_transaction(session, t, parts)
    except SplitError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    except SettledError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    session.refresh(t)
    return transactions_out(session, [t])[0]


@router.post("/allocations/bulk")
def bulk_change(body: BulkChange, session: SessionDep) -> BulkResult:
    """All selected allocations change together, or none do (one database transaction)."""
    wanted = set(body.allocation_ids)
    allocations = list(session.scalars(select(Allocation).where(Allocation.id.in_(wanted))))
    missing = wanted - {a.id for a in allocations}
    if missing:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no such allocations: {sorted(missing)}")
    set_category = "category" in body.model_fields_set
    category_id = _category_id(session, body.category) if set_category else None
    with atomic(session):
        for allocation in allocations:
            owner_change(
                session,
                allocation,
                set_category=set_category,
                category_id=category_id,
                personal=body.personal,
                action="bulk",
            )
    return BulkResult(updated=len(allocations))
