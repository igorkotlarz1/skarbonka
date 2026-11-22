"""M8 gate: receipt splits, atomic audit, rule suggestions, one-click acceptance of proposals."""

from collections.abc import Sequence
from dataclasses import replace
from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from skarbonka.categorization.classifier import Prediction
from skarbonka.categorization.rules import TransactionView
from skarbonka.categorization.seed import load_seed, seed
from skarbonka.db.models import Allocation, AuditLog, Merchant, Settlement, Transaction
from skarbonka.domain.imports import import_ing_file
from skarbonka.importers.synthetic_ing import (
    MAIN_ACCOUNT,
    SyntheticTransaction,
    generate_export,
    render_csv,
)

GROCERIES = "Jedzenie/Zakupy spożywcze"
SNACKS = "Jedzenie/Przekąski"
FURNITURE = "Dom/Meble i wyposażenie"


def card(counterparty: str, amount: str, day: int) -> SyntheticTransaction:
    return SyntheticTransaction(
        "card", date(2026, 6, day), date(2026, 6, day), counterparty,
        f" Płatność kartą {day:02d}.06.2026 Nr karty 4246xx1234", "", "", "",
        Decimal(amount), MAIN_ACCOUNT,
    )  # fmt: skip


RECEIPT = card(" LIDL SKLEP  GLIWICE  POL ", "-123.45", 3)
LIDL_AGAIN = card(" LIDL SKLEP  KATOWICE  POL ", "-40.00", 4)
BAKERY = card(" PIEKARNIA U ZOSI  GLIWICE  POL ", "-12.40", 5)


def export(*rows: SyntheticTransaction) -> bytes:
    base = generate_export(seed=808, start=date(2026, 6, 1), end=date(2026, 6, 2))
    return render_csv(replace(base, transactions=rows))


class FixedPredictor:
    """Stands in for a trained model: always the same unsure guess."""

    def predict(self, views: Sequence[TransactionView]) -> list[Prediction]:
        return [Prediction(FURNITURE, 0.41, {FURNITURE: 0.41}) for _ in views]


@pytest.fixture
def loaded(db: Session) -> Session:
    seed(db, load_seed())
    import_ing_file(db, "june.csv", export(RECEIPT, LIDL_AGAIN, BAKERY), model=FixedPredictor())
    db.commit()  # like a real import: a failed request later rolls back only its own work
    return db


def find(session: Session, marker: str, amount: str) -> Transaction:
    return session.scalars(
        select(Transaction).where(
            Transaction.counterparty.contains(marker), Transaction.amount == Decimal(amount)
        )
    ).one()


def audit_rows(session: Session) -> int:
    return session.scalar(select(func.count()).select_from(AuditLog)) or 0


def row_of(session: Session, t: Transaction) -> tuple[Any, ...]:
    return tuple(session.execute(select(Transaction.__table__).where(Transaction.id == t.id)).one())


def split(client: TestClient, t: Transaction, *parts: tuple[str, str | None, bool]) -> Any:
    body = {"parts": [{"amount": a, "category": c, "personal": p} for a, c, p in parts]}
    return client.put(f"/transactions/{t.id}/splits", json=body)


def test_split_with_exact_sum_succeeds(loaded: Session, client: TestClient) -> None:
    """Parts that sum exactly to the transaction amount are accepted."""
    t = find(loaded, "LIDL", "-123.45")
    response = split(client, t, ("-100.00", GROCERIES, False), ("-23.45", SNACKS, True))
    assert response.status_code == 200, response.text
    parts = response.json()["allocations"]
    assert [(p["amount"], p["category"], p["personal"]) for p in parts] == [
        ("-100.00", GROCERIES, False),
        ("-23.45", SNACKS, True),
    ]


def test_split_off_by_one_grosz_is_rejected(loaded: Session, client: TestClient) -> None:
    """A part sum off by 0.01 is rejected and nothing changes."""
    t = find(loaded, "LIDL", "-123.45")
    before = [(a.id, a.amount) for a in t.allocations]
    response = split(client, t, ("-100.00", GROCERIES, False), ("-23.44", SNACKS, False))
    assert response.status_code == 422
    assert "0.01" in response.text
    loaded.expire_all()
    assert [(a.id, a.amount) for a in loaded.get_one(Transaction, t.id).allocations] == before


@pytest.mark.parametrize(
    "parts",
    [
        [("-133.45", GROCERIES, False), ("10.00", SNACKS, False)],  # sums, but one part is a credit
        [("-123.45", GROCERIES, False), ("0.00", SNACKS, False)],  # an empty part
    ],
)
def test_split_signs_match_the_transaction(
    loaded: Session, client: TestClient, parts: list[tuple[str, str, bool]]
) -> None:
    """Every part of a debit is negative (and of a credit positive); zero parts are rejected."""
    t = find(loaded, "LIDL", "-123.45")
    assert split(client, t, *parts).status_code == 422


def test_split_replaces_allocation_transaction_unchanged(
    loaded: Session, client: TestClient
) -> None:
    """The split replaces the single allocation; the bank transaction row stays byte for byte."""
    t = find(loaded, "LIDL", "-123.45")
    old_ids = {a.id for a in t.allocations}
    row_before = row_of(loaded, t)

    response = split(client, t, ("-100.00", GROCERIES, False), ("-23.45", SNACKS, False))
    assert response.status_code == 200, response.text

    loaded.expire_all()
    parts = loaded.scalars(select(Allocation).where(Allocation.transaction_id == t.id)).all()
    assert len(parts) == 2
    assert not {a.id for a in parts} & old_ids
    assert {a.source for a in parts} == {"manual"}
    assert sum(a.amount for a in parts) == Decimal("-123.45")
    assert row_of(loaded, t) == row_before
    log = loaded.scalars(select(AuditLog).order_by(AuditLog.id.desc())).first()
    assert log is not None
    assert (log.entity, log.entity_id, log.action) == ("transaction", t.id, "split")


def test_failure_writes_no_audit(
    loaded: Session, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Audit and change share one database transaction: a failure in between writes nothing."""
    t = find(loaded, "LIDL", "-123.45")
    before = [(a.id, a.amount, a.category_id) for a in t.allocations]
    audit_before = audit_rows(loaded)

    def broken_audit(*args: object, **kwargs: object) -> None:
        raise RuntimeError("simulated failure while writing the audit row")

    monkeypatch.setattr("skarbonka.domain.splits.audit_split", broken_audit)
    with pytest.raises(RuntimeError, match="simulated"):
        split(client, t, ("-100.00", GROCERIES, False), ("-23.45", SNACKS, False))

    loaded.expire_all()
    after = [(a.id, a.amount, a.category_id) for a in loaded.get_one(Transaction, t.id).allocations]
    assert after == before
    assert audit_rows(loaded) == audit_before


def test_manual_correction_returns_rule_suggestion(loaded: Session, client: TestClient) -> None:
    """After a manual category change the API proposes a merchant rule and its reach."""
    t = find(loaded, "LIDL", "-123.45")
    allocation_id = t.allocations[0].id

    response = client.patch(f"/allocations/{allocation_id}", json={"category": SNACKS})
    assert response.status_code == 200, response.text
    suggestion = response.json()["rule_suggestion"]
    assert suggestion["rule"]["when"]["merchant"] == "Lidl"
    assert suggestion["rule"]["category"] == SNACKS
    assert suggestion["would_change"] == 1  # the other Lidl purchase, still groceries

    created = client.post("/rules", json=suggestion["rule"])  # the suggestion is a ready rule
    assert created.status_code == 201, created.text


def test_unknown_merchant_gets_suggestion_and_click_accepts(
    loaded: Session, client: TestClient
) -> None:
    """An unsure proposal waits in suggested_category_id; one click makes it manual."""
    bakery = find(loaded, "PIEKARNIA", "-12.40").allocations[0]
    assert bakery.category_id is None  # nothing applied without the owner's click
    assert bakery.suggested_category_id is not None

    response = client.post(f"/allocations/{bakery.id}/accept", json={"remember_for_merchant": True})
    assert response.status_code == 200, response.text
    assert response.json()["category"] == FURNITURE

    loaded.expire_all()
    accepted = loaded.get_one(Allocation, bakery.id)
    assert (accepted.source, accepted.suggested_category_id) == ("manual", None)
    merchant = loaded.get_one(Merchant, accepted.transaction.merchant_id)
    assert merchant.default_category_id == accepted.category_id  # remembered for next time

    again = client.post(f"/allocations/{bakery.id}/accept", json={})
    assert again.status_code == 409  # nothing left to accept


def test_split_of_settled_transaction_is_refused(loaded: Session, client: TestClient) -> None:
    """Decision for M8: a transaction already in a settlement cannot be split (corrections: M9)."""
    t = find(loaded, "LIDL", "-123.45")
    settlement = Settlement(period_start=date(2026, 6, 1), period_end=date(2026, 6, 30))
    loaded.add(settlement)
    loaded.flush()
    t.allocations[0].settlement_id = settlement.id
    loaded.flush()

    response = split(client, t, ("-100.00", GROCERIES, False), ("-23.45", SNACKS, False))
    assert response.status_code == 409
