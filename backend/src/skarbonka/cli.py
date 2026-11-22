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
from typing import Any, get_args

from skarbonka.categorization.features import Backend
from skarbonka.categorization.synthetic_labels import LabelledExample, synthetic_examples
from skarbonka.importers.ing import EncodingNotSupportedError, ParseResult, parse_ing

BACKENDS: tuple[str, ...] = get_args(Backend)


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


def seed_command(file: Path | None) -> int:
    """Load the category tree, merchants and rules from TOML into the database."""
    from skarbonka.api.deps import session_factory
    from skarbonka.categorization.seed import DEFAULT_SEED_FILE, load_seed, seed
    from skarbonka.domain.categorize import categorize

    path = file or DEFAULT_SEED_FILE
    try:
        config = load_seed(path)
    except (OSError, ValueError) as exc:
        print(f"ERROR: {path}: {exc}")
        return 1
    categories = sum(1 + len(c.children) for c in config.category)
    with session_factory()() as session:
        seed(session, config)
        stats = categorize(session)
        session.commit()
    print(
        f"Seeded from {path.name}: {categories} categories, "
        f"{len(config.merchant)} merchants, {len(config.rule)} rules.\n"
        f"Re-categorized: {stats.allocations_changed} allocations changed, "
        f"{stats.internal_pairs} own-account transfer pairs."
    )
    return 0


def _examples(synthetic: bool) -> list[LabelledExample]:
    if synthetic:
        return synthetic_examples(seed=0)
    from skarbonka.api.deps import session_factory
    from skarbonka.domain.training import labelled_examples

    with session_factory()() as session:
        examples, sources = labelled_examples(session)
    print("Labels: " + ", ".join(f"{k} {n}" for k, n in sources.most_common()) or "none")
    return examples


def format_report(report: dict[str, Any]) -> str:
    """Metrics only: counts and scores per category name, never a transaction."""
    test = report["test"]
    split = report["split"]
    at = test["accuracy_at_threshold"]
    lines = [
        f"Backend: {report['backend']}  calibrated: {report['calibrated']}",
        f"Split by merchant: train {split['train']} ({split['train_merchants']} merchants), "
        f"test {split['test']} ({split['test_merchants']} new merchants), "
        f"shared {split['shared_merchants']}",
        f"Macro-F1: {test['macro_f1']:.3f}  accuracy: {test['accuracy']:.3f}",
        f"At threshold {test['threshold']}: coverage {test['coverage_at_threshold']:.1%}, "
        f"accuracy {'n/a' if at is None else format(at, '.1%')}  "
        f"(calibration error {test['expected_calibration_error']:.3f})",
        f"  {'category':<28} {'f1':>6} {'prec':>6} {'rec':>6} {'n':>5}",
    ]
    lines += [
        f"  {label:<28} {m['f1']:>6.3f} {m['precision']:>6.3f} {m['recall']:>6.3f} "
        f"{m['support']:>5}"
        for label, m in sorted(test["per_class"].items(), key=lambda kv: -kv[1]["support"])
    ]
    return "\n".join(lines)


def train_command(
    backend: Backend, synthetic: bool, models_dir: Path | None, threshold: float
) -> int:
    from skarbonka.categorization.evaluate import train_and_evaluate
    from skarbonka.config import get_settings

    examples = _examples(synthetic)
    if len({e.label for e in examples}) < 2:
        print("ERROR: need labelled transactions from at least two categories")
        return 1
    target = models_dir or get_settings().models_dir
    try:
        report = train_and_evaluate(examples, target, backend=backend, threshold=threshold)
    except ValueError as exc:
        print(f"ERROR: {exc}")
        return 1
    print(format_report(report))
    print(f"Model and metrics.json written to {target}")
    return 0


def evaluate_command(backends: Sequence[Backend], synthetic: bool, threshold: float) -> int:
    from skarbonka.categorization.evaluate import evaluate_backend

    examples = _examples(synthetic)
    try:
        for backend in backends:
            print(format_report(evaluate_backend(examples, backend, threshold, seed=0)))
            print()
    except ValueError as exc:
        print(f"ERROR: {exc}")
        return 1
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="skarbonka")
    commands = parser.add_subparsers(dest="command", required=True)
    inspect_cmd = commands.add_parser(
        "inspect", help="print safe statistics about ING exports (never rows)"
    )
    inspect_cmd.add_argument("files", nargs="+", type=Path)
    seed_cmd = commands.add_parser(
        "seed", help="load categories, merchants and rules from categories.toml"
    )
    seed_cmd.add_argument("--file", type=Path, default=None, help="another TOML file")
    for name, help_text in (
        ("train", "train the category classifier and save it to models/ (prints metrics)"),
        ("evaluate", "compare classifier backends on a merchant-grouped split (no saving)"),
    ):
        cmd = commands.add_parser(name, help=help_text)
        cmd.add_argument("--synthetic", action="store_true", help="use invented examples")
        cmd.add_argument("--threshold", type=float, default=0.8)
        if name == "train":
            cmd.add_argument("--backend", choices=BACKENDS, default="tfidf")
            cmd.add_argument("--models-dir", type=Path, default=None)
        else:
            cmd.add_argument("--backends", nargs="+", choices=BACKENDS, default=["tfidf"])
    args = parser.parse_args(argv)
    if args.command == "train":
        return train_command(args.backend, args.synthetic, args.models_dir, args.threshold)
    if args.command == "evaluate":
        return evaluate_command(args.backends, args.synthetic, args.threshold)
    if args.command == "inspect":
        return inspect(args.files)
    if args.command == "seed":
        return seed_command(args.file)
    return 2  # pragma: no cover - argparse rejects unknown commands


if __name__ == "__main__":
    sys.exit(main())
