"""Receipt splits: one bank transaction, several allocations that sum to it exactly.

The bank row never changes. A split replaces the transaction's allocations with new
`manual` ones and writes one audit row; the caller commits both together or neither.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from skarbonka.db.models import Allocation, AuditLog, Transaction

GROSZ = Decimal("0.01")


class SplitError(ValueError):
    """The parts do not form a valid split of the transaction."""


class SettledError(RuntimeError):
    """The transaction is already in a settlement; it is corrected there (M9), not split."""


@dataclass(frozen=True)
class SplitPart:
    amount: Decimal
    category_id: int | None
    personal: bool


def check_split(total: Decimal, amounts: Sequence[Decimal]) -> None:
    """Raise SplitError unless the amounts are whole grosze, share the total's sign,
    are not zero, and add up to the total exactly."""
    if not amounts:
        raise SplitError("a split needs at least one part")
    for amount in amounts:
        if amount != amount.quantize(GROSZ):
            raise SplitError(f"part {amount} is not a whole grosz")
        if amount == 0:
            raise SplitError("a part cannot be zero")
        if (amount < 0) != (total < 0):
            raise SplitError(f"part {amount} has the wrong sign for a total of {total}")
    parts_sum = sum(amounts, Decimal("0"))
    if parts_sum != total:
        raise SplitError(f"parts sum to {parts_sum}, off by {parts_sum - total} from {total}")


def _snapshot(allocations: Sequence[Allocation]) -> dict[str, Any]:
    return {
        "parts": [
            {
                "amount": str(a.amount),
                "category_id": a.category_id,
                "personal": a.personal,
                "source": a.source,
            }
            for a in allocations
        ]
    }


def audit_split(session: Session, t: Transaction, before: dict[str, Any]) -> None:
    session.add(
        AuditLog(
            entity="transaction",
            entity_id=t.id,
            action="split",
            before=before,
            after=_snapshot(t.allocations),
        )
    )


def split_transaction(session: Session, t: Transaction, parts: Sequence[SplitPart]) -> None:
    """Replace the allocations of `t` with `parts`. Flushes; does not commit."""
    if any(a.settlement_id is not None for a in t.allocations):
        raise SettledError("transaction is in a settlement")
    check_split(t.amount, [p.amount for p in parts])
    before = _snapshot(t.allocations)
    for old in list(t.allocations):
        session.delete(old)
    session.flush()
    session.expire(t, ["allocations"])
    for part in parts:
        session.add(
            Allocation(
                transaction_id=t.id,
                amount=part.amount,
                category_id=part.category_id,
                personal=part.personal,
                source="manual",
            )
        )
    session.flush()
    session.expire(t, ["allocations"])
    audit_split(session, t, before)
    session.flush()
