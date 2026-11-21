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

## 2026-11-21 M4: Schema and import
- Done: SQLAlchemy models and the first Alembic migration (accounts, import_batches, raw_rows, transactions, allocations, categories, merchants, merchant_aliases, rules, settlements, audit_log; money NUMERIC(12,2) with an explicit currency, original amount and currency kept; pgvector extension enabled), `domain/imports.py` (parse → skip holds → dedup → one allocation per transaction → batch stats), `POST /imports` (several files, per-file stats, a broken file fails alone) and `GET /imports`. Gate M4: 12 tests (58 with M1–M3) + 4 unit tests.
- Decisions: hold-only rows are not imported, only counted (`holds_skipped`), so a hold that later becomes a booking can never be counted twice. Dedup key is unique in the DB: `nr:<account>:<number>` or `fp:<sha256>` with an occurrence index for rows without a number. Statuses are strings with CHECK constraints, not Postgres enums (cheaper migrations). Tests get their own `skarbonka_test` DB and roll back every test. New dependency: python-multipart (approved).
- Hard parts: the occurrence index keeps identical unnumbered purchases apart, but only if both exports contain the whole day; a file cut mid-day could still mismatch. Real exports seem to always carry a number, so this is theoretical until `inspect` shows otherwise.
- Next: owner runs `inspect` on real exports; then M3.5 (Revolut, NBP) or M5 (merchants and rules).

## 2026-11-21 M5: Merchants and rules
- Done: `categorization/merchants.py` (counterparty split on 2+ spaces, processor prefix and trailing country stripped, merchant key without digit tokens, whole-word keyword match), `categorization/rules.py` (Pydantic conditions with unknown keys rejected, pure priority evaluation per outcome field), `categorization/categories.toml` + `skarbonka seed` (editable category tree, merchants with keywords, rules), `domain/categorize.py` (alias → keyword → new merchant, rules → merchant memory, own-account transfer pairs ±2 days into the excluded "Przelewy własne"), API `GET/POST /rules`, `POST /rules/preview`, `POST /categorize`, `PUT /transactions/{id}/category` (manual label, optional "remember for merchant", audit log). Import categorizes new rows. Gate M5: 11 tests (69 with M1–M4) + 10 unit tests.
- Decisions: the tree, merchants and rules live in a TOML file the owner edits; `seed` is idempotent (TOML wins for rules, merchant default category is set only when empty so manual teaching survives). Manual and split allocations are never touched by automatic layers. `transactions.merchant_id` is derived enrichment, not bank data. `allocations.suggested_category_id` added now for the M8 "LLM suggests, owner accepts or corrects" flow.
- Hard parts: the gate checks the starting rules from `docs/context.md`; the owner's notebook rules are not compared yet. Internal transfer detection is greedy (first equal inflow wins), fine for two accounts.
- Next: owner runs `seed`; notebook rules comparison; M3.5 (Revolut) once an anonymized CSV exists, else M6.

