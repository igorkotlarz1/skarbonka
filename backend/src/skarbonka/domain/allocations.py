"""The owner's changes to allocations: always `manual`, always audited in the same transaction."""

from typing import Any

from sqlalchemy.orm import Session

from skarbonka.db.models import Allocation, AuditLog


def snapshot(allocation: Allocation) -> dict[str, Any]:
    return {
        "category_id": allocation.category_id,
        "personal": allocation.personal,
        "source": allocation.source,
    }


def owner_change(
    session: Session,
    allocation: Allocation,
    *,
    set_category: bool,
    category_id: int | None,
    personal: bool | None,
    action: str,
) -> None:
    """Apply what the owner decided. Marking the allocation `manual` keeps later
    re-categorization (rules, merchant memory, ML) from undoing it. Flushes nothing."""
    before = snapshot(allocation)
    if set_category:
        allocation.category_id = category_id
        allocation.suggested_category_id = None
    if personal is not None:
        allocation.personal = personal
    allocation.source = "manual"
    session.add(
        AuditLog(
            entity="allocation",
            entity_id=allocation.id,
            action=action,
            before=before,
            after=snapshot(allocation),
        )
    )
