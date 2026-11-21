"""Pure rule engine and seed file checks (no database)."""

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from skarbonka.categorization.rules import RuleConditions, RuleSpec, TransactionView, evaluate
from skarbonka.categorization.seed import load_seed
from skarbonka.cli import main

T = TransactionView(
    counterparty=" STOKROTKA 12  GLIWICE  POL ",
    title="Płatność kartą",
    amount=Decimal("-64.20"),
    account="Konto Direct",
    transaction_date=date(2026, 3, 7),  # Saturday
    operation_kind="card",
    merchant="Stokrotka",
)


def rule(name: str, priority: int, **kwargs: object) -> RuleSpec:
    return RuleSpec.model_validate({"name": name, "priority": priority, **kwargs})


def test_each_outcome_field_comes_from_the_first_matching_rule() -> None:
    rules = [
        rule("late category", 50, when={"merchant": "stokrotka"}, category="Inne"),
        rule("early personal", 10, when={"weekdays": [5, 6]}, personal=True),
        rule("no match", 1, when={"amount_min": "100"}, category="Dom"),
    ]
    outcome = evaluate(rules, T)
    assert (outcome.category, outcome.personal) == ("Inne", True)


def test_amount_bounds_use_the_absolute_value() -> None:
    assert evaluate([rule("r", 1, when={"amount_max": "70"}, personal=False)], T).personal is False


@pytest.mark.parametrize(
    "when",
    [{}, {"merchnt": "Lidl"}, {"regex": "("}, {"weekdays": [7]}, {"amount_min": "-1"}],
)
def test_bad_conditions_are_rejected(when: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        RuleConditions.model_validate(when)


def test_rule_without_outcome_is_rejected() -> None:
    with pytest.raises(ValidationError):
        rule("nothing", 1, when={"merchant": "Lidl"})


def test_default_seed_file_loads() -> None:
    config = load_seed()
    assert any(c.excluded_from_settlement for c in config.category)
    assert {r.name for r in config.rule} >= {"Żabka jest osobista"}


def test_seed_command_reports_a_broken_file(tmp_path: Path) -> None:
    broken = tmp_path / "broken.toml"
    broken.write_text("[[category]]\nnam = 'typo'\n", encoding="utf-8")
    assert main(["seed", "--file", str(broken)]) == 1
