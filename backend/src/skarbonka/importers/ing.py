"""Parser for ING Bank Śląski "Lista transakcji" CSV exports.

Pure functions: bytes in, a `ParseResult` out. Nothing here touches the
database or the file system, so every rule is testable on synthetic fixtures.

The bank's own summary (count and totals in the metadata block) is used to
validate the import. Disagreements become warnings, never exceptions, so a
partly broken file can still be inspected and fixed.
"""

from __future__ import annotations

import csv
import io
import re
from collections.abc import Iterable, Sequence
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Literal

from pydantic import BaseModel, ConfigDict

Separator = Literal[";", ",", "\t"]
OperationKind = Literal["card", "blik", "transfer", "unknown"]

# Header cells the parser needs, by their exact name in the export.
COL_TRANSACTION_DATE = "Data transakcji"
COL_BOOKING_DATE = "Data księgowania"
COL_COUNTERPARTY = "Dane kontrahenta"
COL_TITLE = "Tytuł"
COL_ACCOUNT_NUMBER = "Nr rachunku"
COL_BANK_NAME = "Nazwa banku"
COL_DETAILS = "Szczegóły"
COL_TRANSACTION_NUMBER = "Nr transakcji"
COL_AMOUNT = "Kwota transakcji (waluta rachunku)"
COL_HOLD = "Kwota blokady/zwolnienie blokady"
COL_FOREIGN = "Kwota płatności w walucie"
COL_CURRENCY = "Waluta"  # appears three times: right after each amount column
COL_ACCOUNT = "Konto"
REQUIRED = (COL_TRANSACTION_DATE, COL_AMOUNT, COL_TRANSACTION_NUMBER, COL_ACCOUNT)

# Only TR.KART is confirmed on a real export; the rest are ASSUMPTIONS until
# `inspect` on real files shows the codes (docs/milestones.md, M3 owner step).
OPERATION_KINDS: dict[str, OperationKind] = {
    "TR.KART": "card",
    "TR.BLIK": "blik",
    "PRZELEW": "transfer",
}

THOUSANDS_SPACES = str.maketrans("", "", "    ")
_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
_COUNT = re.compile(r"Liczba transakcji\s*:?\s*(\d+)")
_RANGE = re.compile(r"(\d{4}-\d{2}-\d{2})\s*-\s*(\d{4}-\d{2}-\d{2})")


def _sum_pattern(label: str) -> re.Pattern[str]:
    # Matches both "Suma obciążeń (29): 2601,24 PLN" and "Suma obciążeń:;(29): 2601,24 PLN".
    return re.compile(label + r"\s*:?\s*\((\d+)\)\s*:?\s*(-?[\d\s  ]+,\d{2})")


_DEBITS = _sum_pattern("Suma obciążeń")
_CREDITS = _sum_pattern("Suma uznań")


class EncodingNotSupportedError(ValueError):
    """The bytes are neither UTF-8 (with or without BOM) nor Windows-1250."""


class IngMetadata(BaseModel):
    model_config = ConfigDict(frozen=True)

    declared_count: int | None = None
    debit_count: int | None = None
    debit_total: Decimal | None = None
    credit_count: int | None = None
    credit_total: Decimal | None = None
    date_from: date | None = None
    date_to: date | None = None


class IngTransaction(BaseModel):
    model_config = ConfigDict(frozen=True)

    line_number: int
    transaction_date: date
    booking_date: date | None
    counterparty: str
    title: str
    account_number: str
    bank_name: str
    operation_code: str
    operation_kind: OperationKind
    transaction_number: str
    amount: Decimal
    currency: str
    hold_amount: Decimal | None
    foreign_amount: Decimal | None
    foreign_currency: str
    account: str


class QuarantinedRow(BaseModel):
    """A row that could not be read. Holds no cell values, so it is safe to print."""

    model_config = ConfigDict(frozen=True)

    line_number: int
    reason: str


class ParseResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    encoding: str
    separator: Separator
    header: tuple[str, ...]
    metadata: IngMetadata
    transactions: tuple[IngTransaction, ...]
    quarantine: list[QuarantinedRow]
    warnings: list[str]


class RowError(ValueError):
    """Raised inside row parsing; the message becomes the quarantine reason."""


# --- small pure helpers ---------------------------------------------------------


def decode(raw: bytes) -> tuple[str, str]:
    """Strict detection: UTF-8 with BOM, UTF-8, then cp1250. Never latin-1."""
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw.decode("utf-8-sig"), "utf-8-sig"
    for encoding in ("utf-8", "cp1250"):
        try:
            return raw.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    raise EncodingNotSupportedError(
        "File is neither UTF-8 nor Windows-1250. Re-export it from ING instead of re-saving it."
    )


def detect_separator(text: str) -> Separator:
    """The separator that splits the header line into the most known columns."""
    header_line = next(
        (line for line in text.splitlines() if COL_TRANSACTION_DATE in line and COL_AMOUNT in line),
        "",
    )
    candidates: tuple[Separator, ...] = (";", "\t", ",")
    return max(candidates, key=lambda sep: header_line.count(sep))


def parse_amount(cell: str) -> Decimal:
    """'-1 234,56' (any space as thousands separator) -> Decimal('-1234.56')."""
    cleaned = cell.strip().translate(THOUSANDS_SPACES).replace(",", ".")
    try:
        return Decimal(cleaned).quantize(Decimal("0.01"))
    except InvalidOperation as exc:
        raise RowError("amount is not a number") from exc


def parse_optional_amount(cell: str) -> Decimal | None:
    return parse_amount(cell) if cell.strip() else None


def parse_date(cell: str) -> date:
    cell = cell.strip()
    if not _DATE.fullmatch(cell):
        raise RowError("date is not YYYY-MM-DD")
    return date.fromisoformat(cell)


def unquote(cell: str) -> str:
    """ "'2026054973'" -> "2026054973" (the bank wraps numbers in apostrophes)."""
    return cell.strip().strip("'").strip()


def column_index(header: Sequence[str]) -> dict[str, int]:
    """Map column names to positions; each 'Waluta' is bound to the amount before it."""
    index: dict[str, int] = {}
    for position, name in enumerate(header):
        name = name.strip()
        if name == COL_CURRENCY and position > 0:
            previous = header[position - 1].strip()
            index[f"{COL_CURRENCY}:{previous}"] = position
        elif name and name not in index:
            index[name] = position
    missing = [name for name in REQUIRED if name not in index]
    if missing:
        raise ValueError(f"header is missing columns: {', '.join(missing)}")
    return index


def parse_metadata(lines: Iterable[Sequence[str]]) -> IngMetadata:
    text = "\n".join(" ".join(cell.strip() for cell in line) for line in lines)
    values: dict[str, object] = {}
    if match := _COUNT.search(text):
        values["declared_count"] = int(match.group(1))
    if match := _DEBITS.search(text):
        values["debit_count"] = int(match.group(1))
        values["debit_total"] = abs(parse_amount(match.group(2)))
    if match := _CREDITS.search(text):
        values["credit_count"] = int(match.group(1))
        values["credit_total"] = parse_amount(match.group(2))
    if match := _RANGE.search(text):
        values["date_from"] = date.fromisoformat(match.group(1))
        values["date_to"] = date.fromisoformat(match.group(2))
    return IngMetadata.model_validate(values)


def parse_row(cells: Sequence[str], index: dict[str, int], line_number: int) -> IngTransaction:
    # Only empty cells may follow the last named column (the bank pads rows).
    used = max(index.values()) + 1
    last_filled = max((i for i, cell in enumerate(cells) if cell.strip()), default=-1)
    if last_filled != index[COL_ACCOUNT]:
        raise RowError(
            f"wrong column layout: expected the account name in column {index[COL_ACCOUNT] + 1}, "
            f"row has {len(cells)} columns"
        )
    if len(cells) < used:
        raise RowError(f"too few columns: {len(cells)} < {used}")

    def cell(name: str) -> str:
        position = index.get(name)
        return cells[position].strip() if position is not None else ""

    code = cell(COL_DETAILS)
    amount_cell, hold_cell = cell(COL_AMOUNT), cell(COL_HOLD)
    if not amount_cell and not hold_cell:
        raise RowError("row has neither an amount nor a hold amount")
    booking = cell(COL_BOOKING_DATE)
    return IngTransaction(
        line_number=line_number,
        transaction_date=parse_date(cell(COL_TRANSACTION_DATE)),
        booking_date=parse_date(booking) if booking else None,
        counterparty=cell(COL_COUNTERPARTY),
        title=cell(COL_TITLE),
        account_number=unquote(cell(COL_ACCOUNT_NUMBER)),
        bank_name=cell(COL_BANK_NAME),
        operation_code=code,
        operation_kind=OPERATION_KINDS.get(code, "unknown"),
        transaction_number=unquote(cell(COL_TRANSACTION_NUMBER)),
        amount=parse_amount(amount_cell) if amount_cell else parse_amount(hold_cell),
        currency=cell(f"{COL_CURRENCY}:{COL_AMOUNT}") or "PLN",
        hold_amount=parse_optional_amount(hold_cell),
        foreign_amount=parse_optional_amount(cell(COL_FOREIGN)),
        foreign_currency=cell(f"{COL_CURRENCY}:{COL_FOREIGN}"),
        account=cell(COL_ACCOUNT),
    )


def validate(
    meta: IngMetadata, transactions: Sequence[IngTransaction], quarantined: int
) -> list[str]:
    """Compare the rows with the bank's own summary. Messages hold no row content."""
    warnings: list[str] = []
    rows = len(transactions)
    if meta.declared_count is None:
        warnings.append("metadata has no transaction count; totals not validated")
    elif meta.declared_count != rows:
        warnings.append(
            f"transaction count mismatch: bank says {meta.declared_count}, parsed {rows}"
            + (f" (+{quarantined} in quarantine)" if quarantined else "")
        )
    debits = [t.amount for t in transactions if t.amount < 0]
    credits = [t.amount for t in transactions if t.amount > 0]
    checks = (
        ("debit", meta.debit_count, meta.debit_total, len(debits), -sum(debits, Decimal(0))),
        ("credit", meta.credit_count, meta.credit_total, len(credits), sum(credits, Decimal(0))),
    )
    for label, declared_n, declared_total, n, total in checks:
        if declared_n is None or declared_total is None:
            continue
        if (declared_n, declared_total) != (n, total):
            warnings.append(
                f"{label} total mismatch: bank says {declared_n} for {declared_total} PLN, "
                f"parsed {n} for {total} PLN"
            )
    return warnings


# --- entry point ---------------------------------------------------------------------


def parse_ing(raw: bytes) -> ParseResult:
    """Parse one ING export. Raises only when the file is unreadable as a whole."""
    text, encoding = decode(raw)
    separator = detect_separator(text)
    lines = list(csv.reader(io.StringIO(text), delimiter=separator))

    header_at = next(
        (
            i
            for i, line in enumerate(lines)
            if COL_TRANSACTION_DATE in (c.strip() for c in line)
            and COL_AMOUNT in (c.strip() for c in line)
        ),
        None,
    )
    if header_at is None:
        raise ValueError("no ING header row found (looked for 'Data transakcji' and amount)")
    header = tuple(cell.strip() for cell in lines[header_at])
    index = column_index(header)
    metadata = parse_metadata(lines[:header_at])

    transactions: list[IngTransaction] = []
    quarantine: list[QuarantinedRow] = []
    for offset, cells in enumerate(lines[header_at + 1 :], start=header_at + 2):
        if not any(cell.strip() for cell in cells):
            break  # the table ends at the first empty line; the footer follows
        try:
            transactions.append(parse_row(cells, index, offset))
        except RowError as exc:
            quarantine.append(QuarantinedRow(line_number=offset, reason=str(exc)))

    return ParseResult(
        encoding=encoding,
        separator=separator,
        header=header,
        metadata=metadata,
        transactions=tuple(transactions),
        quarantine=quarantine,
        warnings=validate(metadata, transactions, len(quarantine)),
    )
