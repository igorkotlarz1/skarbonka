"""Import service: file bytes -> parser -> deduplication -> transactions with one allocation.

Deduplication key per transaction (unique in the database):
- with a bank transaction number: ``nr:<account id>:<number>``;
- without one: ``fp:<sha256>`` over account, dates, amount, currency, counterparty and title,
  plus the occurrence index of that combination within the file. The index keeps two
  identical purchases on the same day apart, and is stable when the same day is exported
  again in full.

Hold-only rows (no booked amount yet) are not imported; they are counted and will arrive as
ordinary bookings in a later export. The service flushes but never commits: the caller owns
the transaction.
"""

import hashlib
from collections import Counter
from collections.abc import Sequence
from typing import Any

from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from skarbonka.categorization.classifier import CategoryPredictor
from skarbonka.db.models import Account, Allocation, ImportBatch, RawRow, Transaction
from skarbonka.domain.categorize import DEFAULT_THRESHOLD, categorize
from skarbonka.importers.ing import IngTransaction, parse_ing

BANK_ING = "ING"


class ImportStats(BaseModel):
    """What happened to one file. Holds no row content, so it is safe to show and log."""

    model_config = ConfigDict(frozen=True)

    batch_id: int
    filename: str
    status: str
    error: str | None = None
    rows_parsed: int = 0
    inserted: int = 0
    duplicates: int = 0
    holds_skipped: int = 0
    quarantined: int = 0
    warnings: list[str] = []


def fingerprint_base(account_id: int, t: IngTransaction) -> str:
    booking = t.booking_date.isoformat() if t.booking_date else ""
    parts = (str(account_id), t.transaction_date.isoformat(), booking, f"{t.amount:.2f}",
             t.currency, t.counterparty, t.title)  # fmt: skip
    return "\x1f".join(parts)


def dedup_keys(rows: Sequence[tuple[int, IngTransaction]]) -> list[str]:
    """One key per (account id, transaction), in input order. Pure."""
    seen: Counter[str] = Counter()
    keys: list[str] = []
    for account_id, t in rows:
        if t.transaction_number:
            keys.append(f"nr:{account_id}:{t.transaction_number}")
            continue
        base = fingerprint_base(account_id, t)
        occurrence = seen[base]
        seen[base] += 1
        digest = hashlib.sha256(f"{base}\x1f#{occurrence}".encode()).hexdigest()
        keys.append(f"fp:{digest}")
    return keys


def _account(session: Session, cache: dict[str, Account], name: str, currency: str) -> Account:
    if name in cache:
        return cache[name]
    account = session.scalar(select(Account).where(Account.bank == BANK_ING, Account.name == name))
    if account is None:
        account = Account(bank=BANK_ING, name=name, currency=currency)
        session.add(account)
        session.flush()
    cache[name] = account
    return account


def raw_row(
    batch: ImportBatch,
    line_number: int,
    status: str,
    payload: dict[str, Any],
    transaction_id: int | None = None,
) -> RawRow:
    return RawRow(
        import_batch_id=batch.id,
        line_number=line_number,
        status=status,
        payload=payload,
        transaction_id=transaction_id,
    )


def import_ing_file(
    session: Session,
    filename: str,
    raw: bytes,
    model: CategoryPredictor | None = None,
    threshold: float = DEFAULT_THRESHOLD,
) -> ImportStats:
    """Import one ING export. A file that cannot be parsed is recorded as a failed batch."""
    batch = ImportBatch(
        bank=BANK_ING, filename=filename, sha256=hashlib.sha256(raw).hexdigest(), status="ok",
        rows_parsed=0, inserted=0, duplicates=0, holds_skipped=0, quarantined=0, warnings=[],
    )  # fmt: skip
    session.add(batch)
    try:
        result = parse_ing(raw)
    except ValueError as exc:
        batch.status, batch.error = "failed", str(exc)
        session.flush()
        return to_stats(batch)
    session.flush()

    batch.rows_parsed = len(result.transactions)
    batch.quarantined = len(result.quarantine)
    batch.warnings = list(result.warnings)
    for q in result.quarantine:
        session.add(raw_row(batch, q.line_number, "quarantined", {"reason": q.reason}))

    accounts: dict[str, Account] = {}
    booked: list[tuple[int, IngTransaction]] = []
    for t in result.transactions:
        if t.is_hold:
            batch.holds_skipped += 1
            session.add(raw_row(batch, t.line_number, "hold_skipped", t.model_dump(mode="json")))
            continue
        booked.append((_account(session, accounts, t.account, t.currency).id, t))

    keys = dedup_keys(booked)
    existing = set(
        session.scalars(select(Transaction.dedup_key).where(Transaction.dedup_key.in_(keys)))
    )
    new_transactions: list[Transaction] = []
    for (account_id, t), key in zip(booked, keys, strict=True):
        payload = t.model_dump(mode="json")
        if key in existing:
            batch.duplicates += 1
            session.add(raw_row(batch, t.line_number, "duplicate", payload))
            continue
        existing.add(key)
        transaction = Transaction(
            account_id=account_id,
            import_batch_id=batch.id,
            dedup_key=key,
            transaction_number=t.transaction_number or None,
            transaction_date=t.transaction_date,
            booking_date=t.booking_date,
            amount=t.amount,
            currency=t.currency,
            original_amount=t.foreign_amount,
            original_currency=t.foreign_currency or None,
            counterparty=t.counterparty,
            title=t.title,
            counterparty_account=t.account_number,
            operation_code=t.operation_code,
            operation_kind=t.operation_kind,
            allocations=[Allocation(amount=t.amount, source="import")],
        )
        session.add(transaction)
        session.flush()
        new_transactions.append(transaction)
        session.add(raw_row(batch, t.line_number, "inserted", payload, transaction.id))
        batch.inserted += 1

    session.flush()
    if new_transactions:
        categorize(session, new_transactions, model=model, threshold=threshold)
    return to_stats(batch)


def to_stats(batch: ImportBatch) -> ImportStats:
    return ImportStats(
        batch_id=batch.id, filename=batch.filename, status=batch.status, error=batch.error,
        rows_parsed=batch.rows_parsed, inserted=batch.inserted, duplicates=batch.duplicates,
        holds_skipped=batch.holds_skipped, quarantined=batch.quarantined,
        warnings=list(batch.warnings or []),
    )  # fmt: skip
