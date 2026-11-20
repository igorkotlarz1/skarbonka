"""Command line: `uv run skarbonka <command>`.

`inspect` is the only safe way to look at a real bank export: it prints
aggregated statistics and warnings, never a row, a counterparty or a title.
Run it in your own terminal and paste only its output into Claude.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from collections.abc import Sequence
from decimal import Decimal
from pathlib import Path

from skarbonka.importers.ing import EncodingNotSupportedError, ParseResult, parse_ing


def format_inspect(name: str, result: ParseResult) -> str:
    """Stats only. Every value here is an aggregate or comes from the file structure."""
    rows = result.transactions
    meta = result.metadata
    debits = [t.amount for t in rows if t.amount < 0]
    credits = [t.amount for t in rows if t.amount > 0]
    holds = sum(1 for t in rows if t.hold_amount is not None)
    dates = sorted(t.transaction_date for t in rows)
    codes = Counter(t.operation_code or "(empty)" for t in rows)
    kinds = {t.operation_code or "(empty)": t.operation_kind for t in rows}
    currencies = Counter(t.currency for t in rows)
    accounts = len({t.account for t in rows})

    def declared(count: int | None, total: Decimal | None) -> str:
        return "n/a" if count is None or total is None else f"{count} for {total} PLN"

    lines = [
        f"File: {name}",
        f"Encoding: {result.encoding}  Separator: {result.separator!r}",
        f"Header: {len(result.header)} fields, named: " + ", ".join(h for h in result.header if h),
        "",
        f"Transactions parsed: {len(rows)}  (bank says: {meta.declared_count or 'n/a'})",
        f"Quarantine: {len(result.quarantine)} rows",
    ]
    lines += [f"  line {q.line_number}: {q.reason}" for q in result.quarantine]
    lines += [
        f"Debits: {len(debits)} for {-sum(debits, Decimal(0))} PLN"
        f"  (bank says: {declared(meta.debit_count, meta.debit_total)})",
        f"Credits: {len(credits)} for {sum(credits, Decimal(0))} PLN"
        f"  (bank says: {declared(meta.credit_count, meta.credit_total)})",
        f"Holds: {holds}",
        f"Date range: {dates[0]} .. {dates[-1]}" if dates else "Date range: n/a",
        f"Metadata range: {meta.date_from or 'n/a'} .. {meta.date_to or 'n/a'}",
        f"Accounts: {accounts}   Currencies: "
        + ", ".join(f"{c} {n}" for c, n in currencies.most_common()),
        "Operation codes:",
    ]
    lines += [f"  {code:<12} {n:>5}  ({kinds[code]})" for code, n in codes.most_common()]
    lines.append("Warnings:" if result.warnings else "Warnings: none")
    lines += [f"  - {w}" for w in result.warnings]
    return "\n".join(lines)


def inspect(paths: Sequence[Path]) -> int:
    status = 0
    for path in paths:
        try:
            result = parse_ing(path.read_bytes())
        except (EncodingNotSupportedError, ValueError) as exc:
            print(f"File: {path.name}\nERROR: {exc}")
            status = 1
            continue
        print(format_inspect(path.name, result))
        print()
    return status


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="skarbonka")
    commands = parser.add_subparsers(dest="command", required=True)
    inspect_cmd = commands.add_parser(
        "inspect", help="print safe statistics about ING exports (never rows)"
    )
    inspect_cmd.add_argument("files", nargs="+", type=Path)
    args = parser.parse_args(argv)
    if args.command == "inspect":
        return inspect(args.files)
    return 2  # pragma: no cover - argparse rejects unknown commands


if __name__ == "__main__":
    sys.exit(main())
