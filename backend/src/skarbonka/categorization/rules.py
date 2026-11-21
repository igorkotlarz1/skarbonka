"""Rule engine: validated JSONB conditions and pure matching.

A rule has conditions (all must hold) and an outcome: a category, the personal flag, or both.
Rules run by ascending `priority`; for each outcome the first matching rule that sets it wins.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from skarbonka.categorization.merchants import contains_word


class RuleConditions(BaseModel):
    """What a rule looks at. Unknown keys are rejected, so a typo never matches everything."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    merchant: str | None = None
    phrase: str | None = None
    regex: str | None = None
    amount_min: Decimal | None = Field(default=None, ge=0)
    amount_max: Decimal | None = Field(default=None, ge=0)
    account: str | None = None
    weekdays: list[int] | None = None
    operation_kind: str | None = None

    @field_validator("regex")
    @classmethod
    def _regex_compiles(cls, value: str | None) -> str | None:
        if value is not None:
            try:
                re.compile(value)
            except re.error as exc:
                raise ValueError(f"invalid regex: {exc}") from exc
        return value

    @field_validator("weekdays")
    @classmethod
    def _weekdays_in_range(cls, value: list[int] | None) -> list[int] | None:
        if value is not None and not all(0 <= day <= 6 for day in value):
            raise ValueError("weekdays are 0 (Monday) to 6 (Sunday)")
        return value

    @model_validator(mode="after")
    def _not_empty(self) -> Self:
        if not self.model_dump(exclude_none=True):
            raise ValueError("a rule needs at least one condition")
        return self


class RuleSpec(BaseModel):
    """A rule as the owner writes it (TOML seed or API). `category` is a "Parent/Child" path."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    priority: int = 100
    when: RuleConditions
    category: str | None = None
    personal: bool | None = None

    @model_validator(mode="after")
    def _has_outcome(self) -> Self:
        if self.category is None and self.personal is None:
            raise ValueError("a rule must set a category, the personal flag, or both")
        return self


@dataclass(frozen=True)
class TransactionView:
    """The fields rules may look at. Amount is signed (debits negative)."""

    counterparty: str
    title: str
    amount: Decimal
    account: str
    transaction_date: date
    operation_kind: str
    merchant: str | None


def matches(when: RuleConditions, t: TransactionView) -> bool:
    text = f"{t.counterparty} {t.title}"
    size = abs(t.amount)
    checks = (
        when.merchant is None or (t.merchant or "").casefold() == when.merchant.casefold(),
        when.phrase is None or contains_word(text, when.phrase),
        when.regex is None or re.search(when.regex, text, re.IGNORECASE) is not None,
        when.amount_min is None or size >= when.amount_min,
        when.amount_max is None or size <= when.amount_max,
        when.account is None or t.account == when.account,
        when.weekdays is None or t.transaction_date.weekday() in when.weekdays,
        when.operation_kind is None or t.operation_kind == when.operation_kind,
    )
    return all(checks)


@dataclass(frozen=True)
class Outcome:
    category: str | None = None
    personal: bool | None = None

    @property
    def empty(self) -> bool:
        return self.category is None and self.personal is None


def evaluate(rules: Sequence[RuleSpec], t: TransactionView) -> Outcome:
    """First matching rule per outcome field, in ascending priority (stable for ties)."""
    category: str | None = None
    personal: bool | None = None
    for rule in sorted(rules, key=lambda r: r.priority):
        if not matches(rule.when, t):
            continue
        if category is None and rule.category is not None:
            category = rule.category
        if personal is None and rule.personal is not None:
            personal = rule.personal
        if category is not None and personal is not None:
            break
    return Outcome(category, personal)
