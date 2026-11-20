"""M3 gate: ING parser (pure functions) and the `skarbonka inspect` CLI."""

import csv
import io
import re
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from skarbonka.cli import main as cli_main
from skarbonka.importers.ing import EncodingNotSupportedError, parse_amount, parse_ing
from skarbonka.importers.synthetic_ing import MERCHANTS, build_fixture

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "ing"
CLEAN_FIXTURES = ["plain", "two_accounts", "utf8_bom"]


def fixture(name: str) -> bytes:
    return (FIXTURE_DIR / f"{name}.csv").read_bytes()


@pytest.mark.parametrize("name", CLEAN_FIXTURES)
def test_clean_fixtures_match_their_metadata(name: str) -> None:
    """Row count, debit and credit totals equal the bank's own summary; no warnings."""
    result = parse_ing(fixture(name))
    meta = result.metadata
    debits = [t.amount for t in result.transactions if t.amount < 0]
    credits = [t.amount for t in result.transactions if t.amount > 0]

    assert meta.declared_count == len(result.transactions) > 0
    assert meta.debit_count == len(debits)
    assert meta.debit_total == -sum(debits)
    assert meta.credit_count == len(credits)
    assert meta.credit_total == sum(credits)
    assert result.quarantine == []
    assert result.warnings == []
    first = result.transactions[0]
    assert isinstance(first.amount, Decimal)
    assert isinstance(first.transaction_date, date)
    assert first.transaction_number.isdigit()  # apostrophes stripped
    assert first.counterparty == first.counterparty.strip()


def test_detects_encodings_without_latin1_fallback() -> None:
    """cp1250 and UTF-8 BOM are detected; bytes valid in neither raise, never latin-1."""
    plain, bom = parse_ing(fixture("plain")), parse_ing(fixture("utf8_bom"))
    assert (plain.encoding, bom.encoding) == ("cp1250", "utf-8-sig")
    assert plain.transactions == bom.transactions
    assert any("ł" in t.title for t in plain.transactions)
    broken = fixture("plain").replace(b"Lista", b"Li\x98ta")  # 0x98 is undefined in cp1250
    with pytest.raises(EncodingNotSupportedError):
        parse_ing(broken)


def test_header_found_by_name_not_position() -> None:
    """Extra lines above the header do not change the result."""
    shifted = b"Dodatkowa linia\r\nI jeszcze jedna;x\r\n\r\n" + fixture("plain")
    moved, original = parse_ing(shifted).transactions, parse_ing(fixture("plain")).transactions
    assert [t.line_number - 3 for t in moved] == [t.line_number for t in original]
    assert [t.model_copy(update={"line_number": 0}) for t in moved] == [
        t.model_copy(update={"line_number": 0}) for t in original
    ]


def test_separator_is_detected() -> None:
    """A tab-separated copy of the export parses the same as the original."""
    text = fixture("plain").decode("cp1250")
    rows = csv.reader(io.StringIO(text), delimiter=";")
    out = io.StringIO()
    csv.writer(out, delimiter="\t", lineterminator="\r\n").writerows(rows)
    tabbed = parse_ing(out.getvalue().encode("cp1250"))
    assert tabbed.separator == "\t"
    assert tabbed.transactions == parse_ing(fixture("plain")).transactions


def test_malformed_row_is_quarantined() -> None:
    """The broken row lands in quarantine with a reason; all others import; totals warn."""
    result = parse_ing(fixture("malformed_row"))
    assert len(result.quarantine) == 1
    bad = result.quarantine[0]
    assert "column" in bad.reason
    assert bad.line_number > 0
    assert result.metadata.declared_count is not None
    assert len(result.transactions) == result.metadata.declared_count - 1
    assert any("count" in w for w in result.warnings)


def test_count_and_total_mismatch_warn_without_crashing() -> None:
    """A summary that disagrees with the rows yields warnings, not an exception."""
    text = fixture("plain").decode("cp1250")
    text = text.replace("Liczba transakcji:;", "Liczba transakcji:;9")
    text = re.sub(r"(Suma obciążeń:;\(\d+\): )[\d,]+", r"\g<1>1,00", text)
    result = parse_ing(text.encode("cp1250"))
    assert len(result.transactions) == len(parse_ing(fixture("plain")).transactions)
    assert any("count" in w for w in result.warnings)
    assert any("debit" in w for w in result.warnings)
    assert not any("credit" in w for w in result.warnings)


def test_unknown_operation_code_passes_through() -> None:
    """An unseen operation code is kept, marked unknown, and does not drop the row."""
    raw = fixture("plain").replace(b"TR.KART   ", b"TR.NOWY   ", 1)
    result = parse_ing(raw)
    unknown = [t for t in result.transactions if t.operation_kind == "unknown"]
    assert [t.operation_code for t in unknown] == ["TR.NOWY"]
    assert len(result.transactions) == result.metadata.declared_count


@pytest.mark.parametrize(
    ("cell", "expected"),
    [
        ("-83,25", "-83.25"),
        ("1266,83", "1266.83"),
        ("-1 234,56", "-1234.56"),
        ("-1 234,56", "-1234.56"),
        ("-1 234,56", "-1234.56"),
        (" 12,5 ", "12.50"),
    ],
)
def test_parse_amount_handles_polish_formats(cell: str, expected: str) -> None:
    """Decimal comma, spaces and (narrow) non-breaking spaces as thousands separators."""
    assert parse_amount(cell) == Decimal(expected)


def test_currency_columns_are_read_by_position() -> None:
    """The first 'Waluta' belongs to the transaction amount."""
    result = parse_ing(fixture("plain"))
    assert {t.currency for t in result.transactions} == {"PLN"}


def test_inspect_prints_stats_and_never_rows(capsys: pytest.CaptureFixture[str]) -> None:
    """`skarbonka inspect` shows counts, totals, dates and codes but no merchant or title."""
    path = FIXTURE_DIR / "malformed_row.csv"
    assert cli_main(["inspect", str(path)]) == 0
    out = capsys.readouterr().out
    result = parse_ing(path.read_bytes())

    assert f"{len(result.transactions)}" in out
    assert "TR.KART" in out
    assert "2026-01-05" in out
    assert "quarantine" in out.lower()
    for merchant in MERCHANTS:
        assert merchant.name not in out
        assert merchant.city not in out
    assert "Płatność kartą" not in out
    for t in result.transactions:
        assert t.transaction_number not in out


def test_parsing_fixture_bytes_from_generator_is_stable() -> None:
    """Parsing the generator's in-memory output equals parsing the committed file."""
    assert parse_ing(build_fixture("plain")) == parse_ing(fixture("plain"))
