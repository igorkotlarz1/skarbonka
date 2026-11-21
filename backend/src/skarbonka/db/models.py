"""ORM models. Bank transactions are immutable; everything the owner decides lives in allocations.

Money is NUMERIC(12,2) with an explicit ISO 4217 currency next to it, so foreign-currency
accounts (Revolut, M3.5) fit without a schema change.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from skarbonka.db.base import Base

Money = Numeric(12, 2)
Currency = String(3)

ALLOCATION_SOURCES = ("import", "rule", "merchant", "ml", "llm", "manual")
RAW_ROW_STATUSES = ("inserted", "duplicate", "hold_skipped", "quarantined")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Account(TimestampMixin, Base):
    """One bank account as the export names it (ING column `Konto`)."""

    __tablename__ = "accounts"
    __table_args__ = (UniqueConstraint("bank", "name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    bank: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(200))
    currency: Mapped[str] = mapped_column(Currency, default="PLN")


class ImportBatch(TimestampMixin, Base):
    """One uploaded file and what happened to its rows."""

    __tablename__ = "import_batches"
    __table_args__ = (CheckConstraint(_in("status", ("ok", "failed")), name="status"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    bank: Mapped[str] = mapped_column(String(32))
    filename: Mapped[str] = mapped_column(String(255))
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(16))
    error: Mapped[str | None] = mapped_column(Text)
    rows_parsed: Mapped[int] = mapped_column(Integer, default=0)
    inserted: Mapped[int] = mapped_column(Integer, default=0)
    duplicates: Mapped[int] = mapped_column(Integer, default=0)
    holds_skipped: Mapped[int] = mapped_column(Integer, default=0)
    quarantined: Mapped[int] = mapped_column(Integer, default=0)
    warnings: Mapped[list[str]] = mapped_column(JSONB, default=list)


class RawRow(Base):
    """Every parsed or quarantined row of a batch, for audit and re-processing."""

    __tablename__ = "raw_rows"
    __table_args__ = (CheckConstraint(_in("status", RAW_ROW_STATUSES), name="status"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    import_batch_id: Mapped[int] = mapped_column(
        ForeignKey("import_batches.id", ondelete="CASCADE"), index=True
    )
    line_number: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    transaction_id: Mapped[int | None] = mapped_column(
        ForeignKey("transactions.id", ondelete="SET NULL"), index=True
    )


class Transaction(TimestampMixin, Base):
    """A booked bank transaction. Never updated after import."""

    __tablename__ = "transactions"
    __table_args__ = (
        Index("ix_transactions_account_date", "account_id", "transaction_date"),
        CheckConstraint("amount <> 0", name="amount_not_zero"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"))
    import_batch_id: Mapped[int] = mapped_column(ForeignKey("import_batches.id"), index=True)
    # "nr:<account>:<number>" or "fp:<sha256>"; see domain/imports.py.
    dedup_key: Mapped[str] = mapped_column(String(128), unique=True)
    transaction_number: Mapped[str | None] = mapped_column(String(64))
    transaction_date: Mapped[date] = mapped_column(Date)
    booking_date: Mapped[date | None] = mapped_column(Date)
    amount: Mapped[Decimal] = mapped_column(Money)
    currency: Mapped[str] = mapped_column(Currency)
    original_amount: Mapped[Decimal | None] = mapped_column(Money)
    original_currency: Mapped[str | None] = mapped_column(Currency)
    counterparty: Mapped[str] = mapped_column(Text, default="")
    title: Mapped[str] = mapped_column(Text, default="")
    counterparty_account: Mapped[str] = mapped_column(String(64), default="")
    operation_code: Mapped[str] = mapped_column(String(32), default="")
    operation_kind: Mapped[str] = mapped_column(String(16), default="unknown")

    account: Mapped[Account] = relationship()
    allocations: Mapped[list["Allocation"]] = relationship(
        back_populates="transaction", order_by="Allocation.id"
    )


class Category(Base):
    """Two levels: a parent (e.g. Jedzenie) and its children (e.g. Pieczywo)."""

    __tablename__ = "categories"
    __table_args__ = (UniqueConstraint("parent_id", "name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"))
    name: Mapped[str] = mapped_column(String(100))


class Merchant(TimestampMixin, Base):
    __tablename__ = "merchants"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True)
    default_category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"))


class MerchantAlias(Base):
    """A normalized counterparty string that maps to a merchant."""

    __tablename__ = "merchant_aliases"

    id: Mapped[int] = mapped_column(primary_key=True)
    merchant_id: Mapped[int] = mapped_column(
        ForeignKey("merchants.id", ondelete="CASCADE"), index=True
    )
    alias: Mapped[str] = mapped_column(String(300), unique=True)


class Rule(TimestampMixin, Base):
    """Owner's rule: JSONB conditions (M5) that set a category and/or the personal flag."""

    __tablename__ = "rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    priority: Mapped[int] = mapped_column(Integer, default=100)
    conditions: Mapped[dict[str, Any]] = mapped_column(JSONB)
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"))
    personal: Mapped[bool | None] = mapped_column()
    active: Mapped[bool] = mapped_column(default=True)


class Settlement(TimestampMixin, Base):
    __tablename__ = "settlements"
    __table_args__ = (
        CheckConstraint(_in("status", ("draft", "sent")), name="status"),
        CheckConstraint("period_start <= period_end", name="period"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(16), default="draft")
    total: Mapped[Decimal] = mapped_column(Money, default=Decimal("0.00"))
    currency: Mapped[str] = mapped_column(Currency, default="PLN")
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Allocation(TimestampMixin, Base):
    """A slice of a transaction: category, personal flag, where the decision came from.

    Every transaction starts with one allocation for its full amount; receipt splits (M8)
    replace it with several whose amounts sum to the transaction amount.
    """

    __tablename__ = "allocations"
    __table_args__ = (
        CheckConstraint(_in("source", ALLOCATION_SOURCES), name="source"),
        CheckConstraint("confidence IS NULL OR confidence BETWEEN 0 AND 1", name="confidence"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    transaction_id: Mapped[int] = mapped_column(
        ForeignKey("transactions.id", ondelete="CASCADE"), index=True
    )
    amount: Mapped[Decimal] = mapped_column(Money)
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"), index=True)
    personal: Mapped[bool] = mapped_column(default=False)
    source: Mapped[str] = mapped_column(String(16), default="import")
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    settlement_id: Mapped[int | None] = mapped_column(
        ForeignKey("settlements.id", ondelete="SET NULL"), index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    transaction: Mapped[Transaction] = relationship(back_populates="allocations")


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    entity: Mapped[str] = mapped_column(String(50))
    entity_id: Mapped[int] = mapped_column(Integer)
    action: Mapped[str] = mapped_column(String(50))
    before: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    after: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
