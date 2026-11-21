"""Unit tests for the pure deduplication key builder."""

from datetime import date
from decimal import Decimal

from skarbonka.domain.imports import dedup_keys
from skarbonka.importers.ing import IngTransaction


def tx(number: str = "", amount: str = "-12.50", title: str = "kawa") -> IngTransaction:
    return IngTransaction(
        line_number=1, transaction_date=date(2026, 4, 2), booking_date=date(2026, 4, 2),
        counterparty="KAWIARNIA", title=title, account_number="", bank_name="",
        operation_code="TR.KART", operation_kind="card", transaction_number=number,
        amount=Decimal(amount), currency="PLN", hold_amount=None, foreign_amount=None,
        foreign_currency="", account="KONTO",
    )  # fmt: skip


def test_numbered_rows_use_account_and_number() -> None:
    assert dedup_keys([(7, tx("123"))]) == ["nr:7:123"]


def test_same_number_on_other_account_is_another_key() -> None:
    first, second = dedup_keys([(1, tx("123")), (2, tx("123"))])
    assert first != second


def test_identical_unnumbered_rows_get_distinct_stable_keys() -> None:
    rows = [(1, tx()), (1, tx())]
    keys = dedup_keys(rows)
    assert len(set(keys)) == 2
    assert dedup_keys(rows) == keys  # same file again -> same keys


def test_any_field_change_changes_the_fingerprint() -> None:
    (base,) = dedup_keys([(1, tx())])
    assert dedup_keys([(1, tx(amount="-12.51"))]) != [base]
    assert dedup_keys([(1, tx(title="herbata"))]) != [base]
    assert dedup_keys([(2, tx())]) != [base]
