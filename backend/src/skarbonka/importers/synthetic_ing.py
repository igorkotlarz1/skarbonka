"""Synthetic ING "Lista transakcji" exports for tests and the demo.

Claude Code never sees real bank files, so the parser is developed against files
generated here in the same shape as the real export (see "ING CSV format" in
docs/context.md). Every merchant, card and account number below is invented.

Regenerate the committed fixtures with:

    uv run python -m skarbonka.importers.synthetic_ing

Unconfirmed details are marked ASSUMPTION and are to be checked by the owner
against a real export (structure only, never values).
"""

from __future__ import annotations

import argparse
import csv
import io
import random
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Literal

Encoding = Literal["cp1250", "utf-8-sig"]
Kind = Literal["card", "blik", "transfer_out", "transfer_in", "refund", "internal"]

HEADER: tuple[str, ...] = (
    "Data transakcji",
    "Data księgowania",
    "Dane kontrahenta",
    "Tytuł",
    "Nr rachunku",
    "Nazwa banku",
    "Szczegóły",
    "Nr transakcji",
    "Kwota transakcji (waluta rachunku)",
    "Waluta",
    "Kwota blokady/zwolnienie blokady",
    "Waluta",
    "Kwota płatności w walucie",
    "Waluta",
    "Konto",
)
# The real export pads the header with empty fields to 21, and every data row
# carries one more trailing empty field (22). The parser must cope with both.
HEADER_FIELDS = 21
ROW_FIELDS = 22
FOOTER = "Dokument ma charakter informacyjny, nie stanowi dowodu księgowego"

# ASSUMPTION: only TR.KART is confirmed; the other codes await a full export.
OPERATION_CODES: dict[Kind, str] = {
    "card": "TR.KART",
    "blik": "TR.BLIK",
    "transfer_out": "PRZELEW",
    "transfer_in": "PRZELEW",
    "refund": "TR.KART",
    "internal": "PRZELEW",
}

MAIN_ACCOUNT = "KONTO Mobi 18-26"
SAVINGS_ACCOUNT = "Otwarte Konto Oszczędnościowe"
CARD = "4246xx0000"  # invented


@dataclass(frozen=True)
class Merchant:
    name: str
    street: str
    city: str
    min_grosze: int
    max_grosze: int
    weight: int
    country: str = "POL"


# Invented but plausible counterparties from Katowice and Gliwice. The field
# shapes copy the real quirks: double-space separators, store numbers, a
# processor prefix, a missing country code, and "POL" inside a name.
MERCHANTS: tuple[Merchant, ...] = (
    Merchant("LIDL", "OSIEDLOWA", "KATOWICE", 1500, 32000, 14),
    Merchant("LIDL", "ZWYCIĘSTWA", "GLIWICE", 1500, 28000, 8),
    Merchant("JMP S.A. BIEDRONKA 4417", "", "KATOWICE", 800, 21000, 12, country=""),
    Merchant("JMP S.A. BIEDRONKA 5023", "", "GLIWICE", 800, 19000, 7, country=""),
    Merchant("AUCHAN POLSKA", "ŚLĄSKA 9", "KATOWICE", 4000, 45000, 4),
    Merchant("POLOMARKET", "KRÓLOWEJ JADWIGI", "GLIWICE", 600, 9000, 3),
    Merchant("CARREFOUR EXPRESS", "MARIACKA", "KATOWICE", 900, 12000, 4),
    Merchant("ŻABKA Z8812 K.1", "", "KATOWICE", 399, 4999, 9),
    Merchant("ROSSMANN 712", "3 MAJA", "KATOWICE", 1200, 15000, 3),
    Merchant("APTEKA POD ŁABĘDZIEM", "", "GLIWICE", 900, 12000, 2),
    Merchant("ORLEN STACJA NR 4471", "", "KATOWICE", 9000, 32000, 3),
    Merchant("BP-PIAST", "TOSZECKA", "GLIWICE", 9000, 30000, 2),
    Merchant("IKEA KATOWICE", "", "KATOWICE", 3000, 90000, 1),
    Merchant("STOŁÓWKA STUDENCKA", "", "GLIWICE", 1200, 2600, 3),
    Merchant("BKG*Booking.com Hotel", "", "Amsterdam", 25000, 90000, 1, country="N"),
)

BLIK_TITLES = ("Zakup BLIK allegro.pl", "Zakup BLIK pyszne.pl", "Zakup BLIK bilet.silesia")
TRANSFER_OUT = ("Spółdzielnia Mieszkaniowa Śląsk", "Opłata za czynsz")
TRANSFER_IN = ("JAN KOWALSKI", "Zwrot za zakupy")

# ASSUMPTION: months with more shopping (holidays) get a higher weight.
MONTH_WEIGHT = {1: 0.9, 2: 0.85, 3: 1.0, 4: 1.1, 5: 1.0, 6: 1.0, 7: 0.9, 8: 0.9}
MONTH_WEIGHT |= {9: 1.0, 10: 1.0, 11: 1.1, 12: 1.4}


@dataclass(frozen=True)
class SyntheticTransaction:
    kind: Kind
    transaction_date: date
    booking_date: date
    counterparty: str
    title: str
    account_number: str
    bank_name: str
    transaction_number: str
    amount: Decimal
    account: str


@dataclass(frozen=True)
class SyntheticExport:
    start: date
    end: date
    generated_on: date
    accounts: tuple[str, ...]
    transactions: tuple[SyntheticTransaction, ...]
    document_number: str


def grosze(value: int) -> Decimal:
    return (Decimal(value) / 100).quantize(Decimal("0.01"))


def format_amount(value: Decimal) -> str:
    """Decimal comma, no thousands separator: Decimal('-1234.5') -> '-1234,50'."""
    return f"{value:.2f}".replace(".", ",")


def counterparty_field(m: Merchant) -> str:
    """' LIDL PANEWICKA  KATOWICE  POL ': name and street share one space, then double."""
    head = f"{m.name} {m.street}" if m.street else m.name
    return " " + "  ".join(part for part in (head, m.city, m.country) if part) + " "


def generate_export(
    *,
    seed: int,
    start: date,
    end: date,
    accounts: Sequence[str] = (MAIN_ACCOUNT,),
    per_day: float = 0.6,
) -> SyntheticExport:
    """Random but reproducible transactions between start and end (inclusive)."""
    rng = random.Random(seed)  # noqa: S311 - reproducible test data, not crypto
    merchants = list(MERCHANTS)
    weights = [m.weight for m in merchants]
    rows: list[SyntheticTransaction] = []

    def number() -> str:
        return "'" + str(rng.randrange(10**17, 10**18)) + "'"

    def booked(day: date) -> date:
        return min(day + timedelta(days=rng.choice((0, 0, 1, 1, 2))), end)

    day = start
    while day <= end:
        rate = per_day * MONTH_WEIGHT[day.month] * (1.4 if day.weekday() >= 5 else 1.0)
        for _ in range(int(rate) + (rng.random() < rate - int(rate))):
            m = rng.choices(merchants, weights)[0]
            value = -grosze(rng.randint(m.min_grosze, m.max_grosze))
            rows.append(card_row(day, booked(day), m, value, number(), accounts[0]))
        if rng.random() < 0.08:
            value = -grosze(rng.randint(1999, 24999))
            rows.append(
                SyntheticTransaction(
                    "blik", day, booked(day), " ", f" {rng.choice(BLIK_TITLES)} ", "", "",
                    number(), value, accounts[0],
                )
            )  # fmt: skip
        if day.day == 10:
            rows.append(
                transfer(day, booked(day), "transfer_out", TRANSFER_OUT, -grosze(64000),
                         number(), accounts[0])
            )  # fmt: skip
        day += timedelta(days=1)

    card_rows = [r for r in rows if r.kind == "card"]
    if card_rows:  # one refund of an earlier purchase
        bought = rng.choice(card_rows)
        refund_day = min(bought.transaction_date + timedelta(days=3), end)
        rows.append(
            replace(bought, kind="refund", transaction_date=refund_day,
                    booking_date=refund_day, amount=-bought.amount,
                    title=f" Zwrot płatności kartą {refund_day:%d.%m.%Y} Nr karty {CARD}",
                    transaction_number=number())
        )  # fmt: skip
    parents_day = end - timedelta(days=2)
    spent = -sum((r.amount for r in rows if r.amount < 0), Decimal(0))
    rows.append(
        transfer(parents_day, parents_day, "transfer_in", TRANSFER_IN,
                 (spent / 4).quantize(Decimal("0.01")), number(), accounts[0])
    )  # fmt: skip
    if len(accounts) > 1:  # internal transfer pair between own accounts
        moved = grosze(50000)
        mid = start + (end - start) / 2
        for account, value in ((accounts[0], -moved), (accounts[1], moved)):
            rows.append(
                SyntheticTransaction(
                    "internal", mid, mid, " ANNA TESTOWA ", " Przelew własny ",
                    "'00000000000000000000000000'", "ING Bank Śląski S.A.",
                    number(), value, account,
                )
            )  # fmt: skip

    # ASSUMPTION: newest first, like the bank's web listing.
    rows.sort(key=lambda r: (r.transaction_date, r.transaction_number), reverse=True)
    return SyntheticExport(
        start=start,
        end=end,
        generated_on=end + timedelta(days=1),
        accounts=tuple(accounts),
        transactions=tuple(rows),
        document_number=str(rng.randrange(10**9, 10**10)),
    )


def card_row(
    day: date, booking: date, m: Merchant, value: Decimal, number: str, account: str
) -> SyntheticTransaction:
    title = f" Płatność kartą {day:%d.%m.%Y} Nr karty {CARD}"
    return SyntheticTransaction(
        "card", day, booking, counterparty_field(m), title, "", "", number, value, account
    )


def transfer(
    day: date,
    booking: date,
    kind: Kind,
    who_what: tuple[str, str],
    value: Decimal,
    number: str,
    account: str,
) -> SyntheticTransaction:
    who, what = who_what
    return SyntheticTransaction(
        kind, day, booking, f" {who} ", f" {what} ", "'11112222333344445555666677'",
        "Bank Testowy S.A.", number, value, account,
    )  # fmt: skip


def metadata_lines(export: SyntheticExport) -> list[list[str]]:
    """ASSUMPTION: labels follow docs/context.md; exact order and count unconfirmed."""
    debits = [t.amount for t in export.transactions if t.amount < 0]
    credits = [t.amount for t in export.transactions if t.amount > 0]
    lines: list[list[str]] = [
        ["Lista transakcji"],
        [],
        ["Numer dokumentu:", export.document_number],
        ["Data wygenerowania:", f"{export.generated_on:%Y-%m-%d}"],
        [],
        ["Wybrane rachunki:"],
    ]
    lines += [[name, "PL00 0000 0000 0000 0000 0000 0000"] for name in export.accounts]
    lines += [
        [],
        ["Zakres dat:", f"{export.start:%Y-%m-%d} - {export.end:%Y-%m-%d}"],
        ["Rodzaj transakcji:", "Wszystkie"],
        ["Waluta:", "Wszystkie"],
        [],
        ["Liczba transakcji:", str(len(export.transactions))],
        ["Suma obciążeń:", f"({len(debits)}): {format_amount(-sum(debits, Decimal(0)))} PLN"],
        ["Suma uznań:", f"({len(credits)}): {format_amount(sum(credits, Decimal(0)))} PLN"],
        [],
        [],
    ]
    return lines


def row_cells(t: SyntheticTransaction) -> list[str]:
    op = OPERATION_CODES[t.kind]
    cells = [
        f"{t.transaction_date:%Y-%m-%d}",
        f"{t.booking_date:%Y-%m-%d}",
        t.counterparty,
        t.title,
        t.account_number,
        t.bank_name,
        f"{op:<10}",  # padded with spaces, like the real export
        t.transaction_number,
        format_amount(t.amount),
        "PLN",
        "",
        "",
        "",
        "",
        t.account,
    ]
    return cells + [""] * (ROW_FIELDS - len(cells))


def render_csv(
    export: SyntheticExport,
    *,
    encoding: Encoding = "cp1250",
    malformed_row: int | None = None,
) -> bytes:
    """Serialize like the bank does: `;` separator, CRLF line ends, metadata, footer."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";", lineterminator="\r\n")
    for line in metadata_lines(export):
        writer.writerow(line)
    writer.writerow(list(HEADER) + [""] * (HEADER_FIELDS - len(HEADER)))
    for index, t in enumerate(export.transactions):
        cells = row_cells(t)
        if index == malformed_row:
            del cells[4]  # a lost field shifts every later column
        writer.writerow(cells)
    writer.writerow([])
    writer.writerow([])
    writer.writerow([FOOTER])
    return buffer.getvalue().encode(encoding)


# name -> how to build it. Seeds are fixed so the committed files never drift.
FIXTURES: dict[str, str] = {
    "plain": "One account, one month, Windows-1250",
    "two_accounts": "Main and savings account with an internal transfer pair",
    "utf8_bom": "Same shape as plain, but UTF-8 with BOM",
    "malformed_row": "One data row lost a field (wrong column count)",
}


def build_fixture(name: str) -> bytes:
    start, end = date(2026, 1, 5), date(2026, 2, 4)
    if name == "plain":
        return render_csv(generate_export(seed=101, start=start, end=end))
    if name == "two_accounts":
        export = generate_export(
            seed=202, accounts=(MAIN_ACCOUNT, SAVINGS_ACCOUNT), start=start, end=end
        )
        return render_csv(export)
    if name == "utf8_bom":
        return render_csv(generate_export(seed=101, start=start, end=end), encoding="utf-8-sig")
    if name == "malformed_row":
        return render_csv(generate_export(seed=303, start=start, end=end), malformed_row=5)
    raise KeyError(name)


def main(argv: Sequence[str] | None = None) -> None:
    default_out = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "ing"
    parser = argparse.ArgumentParser(description="Write the synthetic ING fixtures.")
    parser.add_argument("--out", type=Path, default=default_out)
    args = parser.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)
    for name, about in FIXTURES.items():
        path = args.out / f"{name}.csv"
        path.write_bytes(build_fixture(name))
        print(f"{path.name}: {about}")


if __name__ == "__main__":
    main()
