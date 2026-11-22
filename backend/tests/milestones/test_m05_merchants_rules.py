"""M5 gate: merchant normalization, the rule engine, rule preview and own-account transfers."""

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from skarbonka.categorization.merchants import contains_word, parse_counterparty
from skarbonka.categorization.seed import load_seed, seed
from skarbonka.db.models import Allocation, Category, Merchant, Transaction
from skarbonka.domain.categorize import is_settleable
from skarbonka.domain.imports import import_ing_file
from skarbonka.importers.synthetic_ing import (
    MERCHANTS,
    counterparty_field,
    generate_export,
    render_csv,
)

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "ing"


def fixture(name: str) -> bytes:
    return (FIXTURE_DIR / f"{name}.csv").read_bytes()


# Half a year of synthetic history: every merchant and chain variant shows up.
HALF_YEAR = render_csv(generate_export(seed=606, start=date(2026, 1, 1), end=date(2026, 6, 30)))


@pytest.fixture
def seeded(db: Session) -> Session:
    seed(db, load_seed())
    return db


def category_path(session: Session, allocation: Allocation) -> str | None:
    if allocation.category_id is None:
        return None
    category = session.get_one(Category, allocation.category_id)
    parent = session.get(Category, category.parent_id) if category.parent_id else None
    return f"{parent.name}/{category.name}" if parent else category.name


def merchant_of(session: Session, t: Transaction) -> str | None:
    return session.get_one(Merchant, t.merchant_id).name if t.merchant_id else None


def test_chain_variants_map_to_one_merchant(seeded: Session) -> None:
    """Lidl, Biedronka and Auchan variants from the fixtures each map to one merchant."""
    import_ing_file(seeded, "half-year.csv", HALF_YEAR)
    by_chain: dict[str, set[str | None]] = {"LIDL": set(), "BIEDRONKA": set(), "AUCHAN": set()}
    seen_raw: dict[str, set[str]] = {chain: set() for chain in by_chain}
    for t in seeded.scalars(select(Transaction)):
        for chain in by_chain:
            if chain in t.counterparty:
                by_chain[chain].add(merchant_of(seeded, t))
                seen_raw[chain].add(t.counterparty)

    assert by_chain == {"LIDL": {"Lidl"}, "BIEDRONKA": {"Biedronka"}, "AUCHAN": {"Auchan"}}
    assert len(seen_raw["LIDL"]) > 1  # real variants
    assert len(seen_raw["BIEDRONKA"]) > 1


def test_country_code_is_stripped_only_at_the_end() -> None:
    """`POLOmarket` keeps its name; `POL` goes only when it is the last field."""
    polo = next(m for m in MERCHANTS if m.name == "POLOMARKET")
    parsed = parse_counterparty(counterparty_field(polo))
    assert parsed.name.startswith("POLOMARKET")
    assert (parsed.city, parsed.country) == ("GLIWICE", "POL")

    biedronka = parse_counterparty(" JMP S.A. BIEDRONKA 4417  KATOWICE ")
    assert (biedronka.city, biedronka.country) == ("KATOWICE", "")
    booking = parse_counterparty(" BKG*Booking.com Hotel  Amsterdam  N ")
    assert booking.name == "Booking.com Hotel"  # processor prefix gone


@pytest.mark.parametrize(
    ("text", "found"),
    [("BP-PIAST TOSZECKA", True), ("STACJA BP", True), ("BPH BANK", False), ("UBP SA", False)],
)
def test_bp_matches_only_as_a_whole_word(text: str, found: bool) -> None:
    """`BP` matches as a whole word only, never inside `BPH` or `UBP`."""
    assert contains_word(text, "BP") is found


def test_higher_priority_rule_wins(seeded: Session, client: TestClient) -> None:
    """Rules apply in priority order: the lower priority number wins."""
    rules = [("Lidl to Inne", 50, "Inne"), ("Lidl to Restauracje", 5, "Jedzenie/Restauracje")]
    for name, priority, category in rules:
        response = client.post("/rules", json={
            "name": name, "priority": priority,
            "when": {"merchant": "Lidl"}, "category": category,
        })  # fmt: skip
        assert response.status_code == 201, response.text
    import_ing_file(seeded, "half-year.csv", HALF_YEAR)

    lidl = [t for t in seeded.scalars(select(Transaction)) if merchant_of(seeded, t) == "Lidl"]
    assert lidl
    assert {category_path(seeded, t.allocations[0]) for t in lidl} == {"Jedzenie/Restauracje"}
    assert {t.allocations[0].source for t in lidl} == {"rule"}


def test_starting_rules_reproduce_expected_categories(seeded: Session) -> None:
    """The starting rules (docs/context.md) give the expected category and personal flag."""
    import_ing_file(seeded, "half-year.csv", HALF_YEAR)
    expected = {
        "Lidl": ("Jedzenie/Zakupy spożywcze", False),
        "Biedronka": ("Jedzenie/Zakupy spożywcze", False),
        "POLOmarket": ("Jedzenie/Zakupy spożywcze", False),
        "Żabka": ("Jedzenie/Przekąski", True),
        "Rossmann": ("Dom/Chemia i higiena", False),
        "Orlen": ("Transport/Paliwo", False),
        "BP": ("Transport/Paliwo", False),
        "Apteka": ("Zdrowie/Apteka", False),
    }
    checked = 0
    for t in seeded.scalars(select(Transaction)):
        merchant = merchant_of(seeded, t)
        if merchant in expected and t.amount < 0:
            a = t.allocations[0]
            assert (category_path(seeded, a), a.personal) == expected[merchant], merchant
            checked += 1
    assert checked > 10


def test_rule_preview_changes_nothing(seeded: Session, client: TestClient) -> None:
    """Preview returns the count and a sample of affected history and writes nothing."""
    import_ing_file(seeded, "half-year.csv", HALF_YEAR)
    before = [
        (a.id, a.category_id, a.personal, a.source) for a in seeded.scalars(select(Allocation))
    ]

    response = client.post("/rules/preview", json={
        "name": "test", "when": {"merchant": "Lidl", "amount_min": "50"},
        "category": "Inne", "personal": True,
    })  # fmt: skip
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["matched"] > 0
    assert 0 < len(body["sample"]) <= 10
    assert all(abs(Decimal(row["amount"])) >= Decimal("50") for row in body["sample"])
    seeded.expire_all()
    after = [
        (a.id, a.category_id, a.personal, a.source) for a in seeded.scalars(select(Allocation))
    ]
    assert after == before


def test_own_account_transfer_is_internal_and_not_settleable(seeded: Session) -> None:
    """A transfer between two own accounts is flagged internal and never settleable."""
    import_ing_file(seeded, "two_accounts.csv", fixture("two_accounts"))
    internal = [t for t in seeded.scalars(select(Transaction)) if "Przelew własny" in t.title]

    assert len(internal) == 2
    assert {t.amount for t in internal} == {internal[0].amount, -internal[0].amount}
    for t in internal:
        allocation = t.allocations[0]
        assert category_path(seeded, allocation) == "Przelewy własne"
        assert not is_settleable(seeded, allocation)


def test_manual_category_wins_and_can_teach_the_merchant(
    seeded: Session, client: TestClient
) -> None:
    """A manual label is kept on re-categorization and can become the merchant's default."""
    import_ing_file(seeded, "half-year.csv", HALF_YEAR)
    carrefour = [t for t in seeded.scalars(select(Transaction))
                 if merchant_of(seeded, t) == "Carrefour"]  # fmt: skip
    assert len(carrefour) >= 2
    first = carrefour[0]

    response = client.put(f"/transactions/{first.id}/category", json={
        "category": "Jedzenie/Przekąski", "remember_for_merchant": True,
    })  # fmt: skip
    assert response.status_code == 200, response.text
    assert client.post("/categorize").status_code == 200

    seeded.expire_all()
    assert first.allocations[0].source == "manual"
    for t in carrefour:
        assert category_path(seeded, t.allocations[0]) == "Jedzenie/Przekąski"
