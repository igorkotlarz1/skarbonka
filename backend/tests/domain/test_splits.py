"""Pure split validation: exact sums, consistent signs, whole grosze."""

from decimal import Decimal

import pytest

from skarbonka.domain.splits import SplitError, check_split

D = Decimal


@pytest.mark.parametrize(
    ("total", "parts"),
    [
        (D("-123.45"), [D("-100.00"), D("-23.45")]),
        (D("-0.03"), [D("-0.01"), D("-0.01"), D("-0.01")]),
        (D("250.00"), [D("200"), D("50.00")]),  # a credit splits into credits
        (D("-9.99"), [D("-9.99")]),  # one part: back to a single allocation
    ],
)
def test_valid_splits(total: Decimal, parts: list[Decimal]) -> None:
    check_split(total, parts)


@pytest.mark.parametrize(
    ("total", "parts", "message"),
    [
        (D("-123.45"), [D("-100.00"), D("-23.44")], "0.01"),
        (D("-123.45"), [D("-100.00"), D("-23.46")], "-0.01"),
        (D("-50.00"), [D("-60.00"), D("10.00")], "sign"),
        (D("-50.00"), [D("-50.00"), D("0")], "zero"),
        (D("-50.00"), [D("-49.995"), D("-0.005")], "grosz"),
        (D("-50.00"), [], "at least one"),
    ],
)
def test_invalid_splits(total: Decimal, parts: list[Decimal], message: str) -> None:
    with pytest.raises(SplitError, match=message):
        check_split(total, parts)
