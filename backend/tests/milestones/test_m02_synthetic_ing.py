"""M2 gate: synthetic ING export generator and the committed fixtures."""

import csv
import io
import subprocess
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from skarbonka.importers.synthetic_ing import (
    FIXTURES,
    HEADER,
    Encoding,
    SyntheticExport,
    build_fixture,
    generate_export,
    render_csv,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE_DIR = REPO_ROOT / "backend" / "tests" / "fixtures" / "ing"


@dataclass
class ReadBack:
    """Minimal test-side reading of the format (the real parser comes in M3)."""

    meta: dict[str, str]
    header: list[str]
    rows: list[list[str]]


def read_back(raw: bytes, encoding: str) -> ReadBack:
    lines = list(csv.reader(io.StringIO(raw.decode(encoding)), delimiter=";"))
    header_at = next(i for i, line in enumerate(lines) if line and line[0] == HEADER[0])
    meta = {line[0].rstrip(":"): line[1] for line in lines[:header_at] if len(line) >= 2}
    rows = []
    for line in lines[header_at + 1 :]:
        if not any(cell.strip() for cell in line):
            break
        rows.append(line)
    return ReadBack(meta=meta, header=lines[header_at], rows=rows)


def amount(cell: str) -> Decimal:
    return Decimal(cell.replace(" ", "").replace(",", "."))


def declared_total(text: str) -> tuple[int, Decimal]:
    """'(29): 2601,24 PLN' -> (29, Decimal('2601.24'))."""
    count_part, value_part = text.split(":")
    return int(count_part.strip(" ()")), amount(value_part.replace("PLN", ""))


def small_export(seed: int = 7) -> SyntheticExport:
    return generate_export(seed=seed, start=date(2026, 1, 1), end=date(2026, 2, 28))


def test_metadata_matches_rows_to_the_grosz() -> None:
    """Declared count, debit total and credit total equal the generated rows."""
    export = small_export()
    back = read_back(render_csv(export, encoding="cp1250"), "cp1250")
    amounts = [amount(row[8]) for row in back.rows]
    debits = [a for a in amounts if a < 0]
    credits = [a for a in amounts if a > 0]

    assert int(back.meta["Liczba transakcji"]) == len(back.rows) == len(export.transactions)
    assert declared_total(back.meta["Suma obciążeń"]) == (len(debits), -sum(debits))
    assert declared_total(back.meta["Suma uznań"]) == (len(credits), sum(credits))
    assert all(isinstance(t.amount, Decimal) for t in export.transactions)


def test_generator_is_deterministic() -> None:
    """Same seed gives a byte-identical file; another seed gives a different one."""
    assert render_csv(small_export(7), encoding="cp1250") == render_csv(
        small_export(7), encoding="cp1250"
    )
    assert render_csv(small_export(7), encoding="cp1250") != render_csv(
        small_export(8), encoding="cp1250"
    )


@pytest.mark.parametrize("encoding", ["cp1250", "utf-8-sig"])
def test_polish_characters_round_trip(encoding: Encoding) -> None:
    """Both supported encodings keep every Polish letter intact."""
    raw = render_csv(small_export(), encoding=encoding)
    text = raw.decode(encoding)
    assert "Płatność kartą" in text
    assert "nie stanowi dowodu księgowego" in text
    assert set("ąćęłóśż") <= set(text)
    if encoding == "utf-8-sig":
        assert raw.startswith(b"\xef\xbb\xbf")
    else:
        assert not raw.startswith(b"\xef\xbb\xbf")
        with pytest.raises(UnicodeDecodeError):
            raw.decode("utf-8")


def test_rows_mimic_bank_column_quirk() -> None:
    """Header has 21 fields (15 named + empty) and data rows 22, like the real export."""
    back = read_back(render_csv(small_export(), encoding="cp1250"), "cp1250")
    assert back.header[: len(HEADER)] == list(HEADER)
    assert len(back.header) == 21
    assert {len(row) for row in back.rows} == {22}
    assert all(row[7].startswith("'") and row[7].endswith("'") for row in back.rows)


def test_row_shapes_cover_operation_kinds() -> None:
    """Card, BLIK, outgoing and incoming transfer, and refund all appear."""
    kinds = {t.kind for t in small_export().transactions}
    assert {"card", "blik", "transfer_out", "transfer_in", "refund"} <= kinds


@pytest.mark.parametrize("name", sorted(FIXTURES))
def test_fixture_committed_and_in_sync(name: str) -> None:
    """Each fixture exists, is not gitignored, and equals a fresh regeneration."""
    path = FIXTURE_DIR / f"{name}.csv"
    assert path.exists(), "run: uv run python -m skarbonka.importers.synthetic_ing"
    ignored = subprocess.run(
        ["git", "check-ignore", "-q", str(path.relative_to(REPO_ROOT))],
        cwd=REPO_ROOT,
        check=False,
    )
    assert ignored.returncode == 1, "fixture is gitignored"
    assert path.read_bytes() == build_fixture(name)


def test_two_accounts_fixture_has_internal_transfer() -> None:
    """The two-account fixture holds both accounts and a matching transfer pair."""
    back = read_back((FIXTURE_DIR / "two_accounts.csv").read_bytes(), "cp1250")
    accounts = {row[14] for row in back.rows}
    assert len(accounts) == 2
    internal = [row for row in back.rows if "Przelew własny" in row[3]]
    assert (
        sorted(amount(row[8]) for row in internal)[0]
        == -sorted(amount(row[8]) for row in internal)[-1]
    )


def test_malformed_fixture_has_exactly_one_bad_row() -> None:
    """Exactly one data row has a wrong column count; the rest are well formed."""
    back = read_back((FIXTURE_DIR / "malformed_row.csv").read_bytes(), "cp1250")
    bad = [row for row in back.rows if len(row) != 22]
    assert len(bad) == 1
    assert len(back.rows) == int(back.meta["Liczba transakcji"])
