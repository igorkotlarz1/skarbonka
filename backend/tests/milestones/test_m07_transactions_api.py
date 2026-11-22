"""M7 gate (backend side): transaction list with filters, personal toggle, bulk category change."""

from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from skarbonka.categorization.seed import load_seed, seed
from skarbonka.db.models import Allocation, AuditLog, Transaction
from skarbonka.domain.imports import import_ing_file
from skarbonka.importers.synthetic_ing import generate_export, render_csv

QUARTER = render_csv(generate_export(seed=707, start=date(2026, 1, 1), end=date(2026, 3, 31)))


@pytest.fixture
def loaded(db: Session) -> Session:
    seed(db, load_seed())
    import_ing_file(db, "quarter.csv", QUARTER)
    return db


def items(client: TestClient, **params: Any) -> list[dict[str, Any]]:
    response = client.get("/transactions", params={"page_size": 500, **params})
    assert response.status_code == 200, response.text
    body: list[dict[str, Any]] = response.json()["items"]
    return body


def audit_rows(session: Session) -> int:
    return session.scalar(select(func.count()).select_from(AuditLog)) or 0


def test_list_filters_by_period_category_merchant_personal_review_and_text(
    loaded: Session, client: TestClient
) -> None:
    """GET /transactions filters by period, category, merchant, personal, needs-review, text."""
    everything = items(client)
    assert len(everything) == loaded.scalar(select(func.count()).select_from(Transaction))

    february = items(client, date_from="2026-02-01", date_to="2026-02-28")
    assert february
    assert all("2026-02-01" <= r["transaction_date"] <= "2026-02-28" for r in february)

    groceries = items(client, category="Jedzenie/Zakupy spożywcze")
    assert groceries
    assert all(r["allocations"][0]["category"] == "Jedzenie/Zakupy spożywcze" for r in groceries)
    parent = items(client, category="Jedzenie")
    assert {r["id"] for r in groceries} < {r["id"] for r in parent}  # parent includes children

    lidl = items(client, merchant="Lidl")
    assert lidl
    assert {r["merchant"] for r in lidl} == {"Lidl"}

    personal = items(client, personal=True)
    assert personal
    assert all(r["allocations"][0]["personal"] for r in personal)
    assert {r["merchant"] for r in personal} >= {"Żabka"}

    review = items(client, needs_review=True)
    assert review
    assert all(r["allocations"][0]["category"] is None for r in review)

    text = items(client, q="biedronka")
    assert text
    assert all("BIEDRONKA" in r["counterparty"].upper() for r in text)


def test_list_paginates_newest_first(loaded: Session, client: TestClient) -> None:
    """Pages are disjoint, ordered newest first, and report the total."""
    first = client.get("/transactions", params={"page": 1, "page_size": 10}).json()
    second = client.get("/transactions", params={"page": 2, "page_size": 10}).json()
    assert first["total"] == second["total"] > 20
    assert len(first["items"]) == len(second["items"]) == 10
    assert not {r["id"] for r in first["items"]} & {r["id"] for r in second["items"]}
    dates = [r["transaction_date"] for r in first["items"] + second["items"]]
    assert dates == sorted(dates, reverse=True)


def test_patch_toggles_personal_and_writes_audit_log(loaded: Session, client: TestClient) -> None:
    """PATCH on an allocation toggles personal and writes one audit_log row."""
    row = items(client, merchant="Lidl")[0]
    allocation_id = row["allocations"][0]["id"]
    before = audit_rows(loaded)

    response = client.patch(f"/allocations/{allocation_id}", json={"personal": True})
    assert response.status_code == 200, response.text
    assert response.json()["personal"] is True

    allocation = loaded.get_one(Allocation, allocation_id)
    loaded.refresh(allocation)
    assert allocation.personal is True
    assert allocation.source == "manual"  # the owner's decision survives re-categorization
    assert audit_rows(loaded) == before + 1
    log = loaded.scalars(select(AuditLog).order_by(AuditLog.id.desc())).first()
    assert log is not None
    assert (log.entity, log.entity_id) == ("allocation", allocation_id)
    assert log.before is not None
    assert log.after is not None
    assert (log.before["personal"], log.after["personal"]) == (False, True)


def test_bulk_category_change_updates_all_selected(loaded: Session, client: TestClient) -> None:
    """A bulk category change updates every selected allocation."""
    ids = [r["allocations"][0]["id"] for r in items(client, merchant="Biedronka")[:5]]
    assert len(ids) == 5
    before = audit_rows(loaded)

    response = client.post("/allocations/bulk", json={
        "allocation_ids": ids, "category": "Jedzenie/Przekąski",
    })  # fmt: skip
    assert response.status_code == 200, response.text
    assert response.json()["updated"] == 5

    for row in items(client, category="Jedzenie/Przekąski"):
        ids_seen = {a["id"] for a in row["allocations"]}
        if ids_seen & set(ids):
            assert row["allocations"][0]["source"] == "manual"
    assert audit_rows(loaded) == before + 5


def test_bulk_change_is_all_or_nothing(loaded: Session, client: TestClient) -> None:
    """One bad id: nothing changes, because the bulk update is one database transaction."""
    ids = [r["allocations"][0]["id"] for r in items(client, merchant="Biedronka")[:3]]
    snapshot = {i: loaded.get_one(Allocation, i).category_id for i in ids}
    before = audit_rows(loaded)

    response = client.post("/allocations/bulk", json={
        "allocation_ids": [*ids, 999_999_999], "category": "Inne",
    })  # fmt: skip
    assert response.status_code == 404

    loaded.expire_all()
    assert {i: loaded.get_one(Allocation, i).category_id for i in ids} == snapshot
    assert audit_rows(loaded) == before


def test_amounts_are_exact_strings(loaded: Session, client: TestClient) -> None:
    """Money leaves the API as exact decimal strings, never floats."""
    row = items(client)[0]
    assert isinstance(row["amount"], str)
    assert Decimal(row["amount"]) == loaded.get_one(Transaction, row["id"]).amount
