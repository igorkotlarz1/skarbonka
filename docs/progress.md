# Progress log

Entries are appended by `/end-session`, newest at the bottom. `/start-session` reads only the last entry.

## 2026-10-29 S0: Setup
- Done: goals, context, requirements, session plan, Claude Code setup.
- Decisions: MVP covers ING only; mBank moves to stage 2.
- Next: S1, repository skeleton.

## 2026-11-20 M1: Repository skeleton
- Done: backend/ (uv, FastAPI /health, pydantic-settings, SQLAlchemy base with naming convention, Alembic wired to settings), docker-compose with pgvector/pg17 on 127.0.0.1, .env.example, pre-commit (bank-file block, ruff, mypy strict), GitHub Actions (lint, types, migrations, gates, tests, bank-file guard). Gate M1: 16 tests green.
- Decisions: test DB comes from SKARBONKA_TEST_DATABASE_URL (defaults to compose); a down DB fails the gate, never skips. Alembic reads the URL from settings or `-x url=`.
- Hard parts: privacy hook scans file contents, so tests build the raw-folder path at runtime; hatchling rejects readme outside backend/; Starlette warns that httpx is deprecated for httpx2 (not switched, needs approval).
- Next: M2, synthetic ING generator.

## 2026-11-20 M2: Synthetic ING generator
- Done: `importers/synthetic_ing.py` (reproducible generator: metadata, 21-field header, 22-field rows, footer, cp1250 or UTF-8 with BOM, card/BLIK/transfers/refund/internal transfer, seasonality, invented Katowice and Gliwice merchants), CLI to regenerate fixtures, 4 fixtures in `tests/fixtures/ing/`. Gate M2: 12 tests green (28 with M1).
- Decisions: amounts built from integer grosze (no float anywhere); fixtures checked byte-for-byte against regeneration; `.gitattributes` keeps fixtures out of line-ending conversion.
- Hard parts: metadata layout, non-card operation codes and row order are assumptions; holds (`Kwota blokady`) not generated yet. Owner to compare structure with a real export.
- Next: M3, ING parser and `inspect`.

## 2026-11-20 M3: ING parser and inspect
- Done: `importers/ing.py` (pure: strict encoding detection without latin-1, separator detection, header found by name, positional `Waluta` binding, metadata regexes tolerant to two layouts, field cleaning, quarantine with value-free reasons, count and debit/credit validation as warnings), `skarbonka inspect` CLI printing only aggregates. Gate M3: 18 tests (46 with M1–M2).
- Decisions: row validity is "last filled cell is Konto", not a field count; unknown operation codes pass through as kind `unknown`; hold-only rows use the hold amount.
- Hard parts: 22 vs 21 fields may be an anonymization artefact; ASCII-only files report utf-8; hold handling unconfirmed.
- Next: owner runs `inspect` on 2–3 real exports; then M4 (schema and import, Opus).
