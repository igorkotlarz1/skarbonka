"""M4 gate: database schema, Alembic migrations and the ING import with deduplication."""

from dataclasses import replace
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from skarbonka.db.models import Allocation, ImportBatch, Transaction
from skarbonka.domain.imports import import_ing_file
from skarbonka.importers.synthetic_ing import (
    MAIN_ACCOUNT,
    SyntheticTransaction,
    generate_export,
    render_csv,
)
from tests.db_utils import run_alembic

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "ing"


def fixture(name: str) -> bytes:
    return (FIXTURE_DIR / f"{name}.csv").read_bytes()


def count(session: Session, model: type[object]) -> int:
    return session.scalar(select(func.count()).select_from(model)) or 0


def test_migrations_upgrade_downgrade_upgrade(scratch_database_url: str) -> None:
    """`alembic upgrade head`, `downgrade base`, `upgrade head` all succeed on an empty DB."""
    run_alembic(scratch_database_url, "upgrade", "head")
    run_alembic(scratch_database_url, "downgrade", "base")
    run_alembic(scratch_database_url, "upgrade", "head")


def test_import_creates_one_allocation_per_transaction(db: Session) -> None:
    """N transactions, each with exactly one allocation for its full amount."""
    stats = import_ing_file(db, "plain.csv", fixture("plain"))
    transactions = db.scalars(select(Transaction)).all()

    assert stats.inserted == len(transactions) > 0
    assert stats.duplicates == 0
    for t in transactions:
        assert len(t.allocations) == 1
        assert t.allocations[0].amount == t.amount
        assert t.allocations[0].personal is False
        assert t.allocations[0].source == "import"
    assert count(db, Allocation) == len(transactions)


def test_reimport_adds_nothing(db: Session) -> None:
    """Importing the same file again adds 0 transactions and records the duplicates."""
    first = import_ing_file(db, "plain.csv", fixture("plain"))
    second = import_ing_file(db, "plain.csv", fixture("plain"))

    assert second.inserted == 0
    assert second.duplicates == first.inserted
    assert count(db, Transaction) == first.inserted
    assert count(db, ImportBatch) == 2


def test_overlapping_file_adds_only_new_rows(db: Session) -> None:
    """Two exports sharing a week: the shared rows are stored once."""
    full = generate_export(seed=404, start=date(2026, 3, 1), end=date(2026, 3, 31))

    def window(start: date, end: date) -> bytes:
        rows = tuple(t for t in full.transactions if start <= t.transaction_date <= end)
        return render_csv(replace(full, start=start, end=end, transactions=rows))

    early = import_ing_file(db, "march-a.csv", window(date(2026, 3, 1), date(2026, 3, 20)))
    late = import_ing_file(db, "march-b.csv", window(date(2026, 3, 14), date(2026, 3, 31)))

    assert early.inserted + late.inserted == len(full.transactions)
    assert late.duplicates > 0
    assert count(db, Transaction) == len(full.transactions)


def test_identical_purchases_without_number_are_both_kept(db: Session) -> None:
    """Same day, amount and merchant, no transaction number: two rows stay two rows."""
    base = generate_export(seed=505, start=date(2026, 4, 1), end=date(2026, 4, 3))
    coffee = SyntheticTransaction(
        "card", date(2026, 4, 2), date(2026, 4, 2), " KAWIARNIA TESTOWA  GLIWICE  POL ",
        " Płatność kartą 02.04.2026 Nr karty 4246xx1234", "", "", "",
        Decimal("-12.50"), MAIN_ACCOUNT,
    )  # fmt: skip
    export = replace(base, transactions=(coffee, coffee, *base.transactions))

    first = import_ing_file(db, "twins.csv", render_csv(export))
    again = import_ing_file(db, "twins.csv", render_csv(export))

    twins = db.scalars(select(Transaction).where(Transaction.amount == Decimal("-12.50"))).all()
    assert len(twins) == 2
    assert first.inserted == len(export.transactions)
    assert again.inserted == 0


def test_hold_rows_are_counted_not_imported(db: Session) -> None:
    """A row with only a hold amount is skipped and shows up in the stats."""
    raw = fixture("plain").decode("cp1250").split("\r\n")
    header_at = next(i for i, line in enumerate(raw) if line.startswith("Data transakcji"))
    cells = raw[header_at + 1].split(";")
    cells[1] = ""  # no booking date yet
    cells[10], cells[11] = cells[8], cells[9]  # amount moves to the hold columns
    cells[8], cells[9] = "", ""
    raw[header_at + 1] = ";".join(cells)

    stats = import_ing_file(db, "hold.csv", "\r\n".join(raw).encode("cp1250"))

    assert stats.holds_skipped == 1
    assert stats.inserted == count(db, Transaction)


def test_import_api_handles_several_files_and_lists_history(client: TestClient) -> None:
    """`POST /imports` with 2 files returns per-file stats; `GET /imports` lists them."""
    files = [
        ("files", ("plain.csv", fixture("plain"), "text/csv")),
        ("files", ("two_accounts.csv", fixture("two_accounts"), "text/csv")),
    ]
    response = client.post("/imports", files=files)
    assert response.status_code == 200
    results = response.json()["imports"]
    assert [r["filename"] for r in results] == ["plain.csv", "two_accounts.csv"]
    assert all(r["status"] == "ok" and r["inserted"] > 0 for r in results)

    history = client.get("/imports").json()
    assert {h["filename"] for h in history} == {"plain.csv", "two_accounts.csv"}
    assert all({"inserted", "duplicates", "holds_skipped", "quarantined"} <= h.keys()
               for h in history)  # fmt: skip


def test_broken_file_is_reported_not_raised(client: TestClient) -> None:
    """A file that is not a readable export fails alone; the other file still imports."""
    files = [
        ("files", ("garbage.csv", b"\x98\x98\x98 not an export", "text/csv")),
        ("files", ("plain.csv", fixture("plain"), "text/csv")),
    ]
    results = client.post("/imports", files=files).json()["imports"]
    assert results[0]["status"] == "failed"
    assert results[0]["error"]
    assert results[1]["status"] == "ok"


@pytest.mark.parametrize(
    ("table", "column"),
    [("transactions", "amount"), ("transactions", "original_amount"),
     ("allocations", "amount"), ("settlements", "total")],
)  # fmt: skip
def test_amount_columns_are_numeric_12_2(db: Session, table: str, column: str) -> None:
    """Money columns are NUMERIC(12,2) in the database itself."""
    row = db.execute(
        text(
            "SELECT data_type, numeric_precision, numeric_scale FROM information_schema.columns "
            "WHERE table_name = :t AND column_name = :c"
        ),
        {"t": table, "c": column},
    ).one()
    assert tuple(row) == ("numeric", 12, 2)
