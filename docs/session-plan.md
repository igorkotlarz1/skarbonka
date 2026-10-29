# Session plan: MVP (ING only)

One session = one task, about 2–3 h. Start each with `/clear` and `/start-session N`, finish with `/end-session`. Requirement IDs (FR, NFR) refer to the requirements doc.

Model: Sonnet by default. Opus only where marked (schema design, ML). Switch with `/model`.

---

## S0. Setup (no Claude Code)

- Create a private GitHub repo and clone it inside WSL2, e.g. `~/code/skarbonka` (WSL filesystem, not `C:`, so Docker is much faster).
- Copy the starter pack contents to the repo root: `CLAUDE.md`, `README.md`, `LICENSE`, `.gitignore`, `docs/`, `.claude/`.
- Install Docker Desktop (WSL2 backend), uv, Node.js LTS, Ollama for Windows, and Claude Code in WSL.
- Create `data/` and put real ING CSVs there. Check `git status`: `data/` must not appear.
- First commit: `chore: initial project docs and Claude Code setup`.

## S1. Repository skeleton

Requirements: NFR-11, NFR-14, NFR-15.

> Read CLAUDE.md. Task: scaffold the backend in `backend/` (uv, FastAPI with `/health`, pydantic-settings with `.env`, Ruff, mypy strict, pytest), `docker-compose.yml` with Postgres 17 + pgvector and a volume, Alembic configured for SQLAlchemy 2, pre-commit (ruff, mypy, block CSV/XLSX files outside `backend/tests/fixtures/`), and a GitHub Actions workflow (lint, types, tests). No domain models yet. Plan first.

Done when: `docker compose up -d db` works, `uv run pytest` is green, CI is green on GitHub.

## S2. Synthetic ING file generator

Requirements: NFR-18 (partly), foundation for parser tests. Claude Code cannot see real files, so it builds a generator in the exact ING format first.

> Using "ING CSV format" in docs/context.md, write a synthetic ING export generator in `backend/src/skarbonka/importers/synthetic_ing.py`: metadata with transaction count and total, header, rows (card, BLIK, outgoing and incoming transfer, refund), footer, Windows-1250 or UTF-8 encoding, optionally two accounts. Realistic merchants from Katowice and Gliwice, seasonality. Generate 4 fixtures into `backend/tests/fixtures/ing/` (plain, two accounts, UTF-8 with BOM, one malformed row). Plan first.

Done when: the fixtures exist and you compared them by eye with a real file in your own editor (without showing it to Claude Code).

## S3. ING parser

Requirements: FR-02 to FR-11.

> Write the ING parser in `backend/src/skarbonka/importers/ing.py` as pure functions: detect encoding and separator, find the header by column names, read metadata, clean fields (apostrophes, whitespace, comma amounts as Decimal, dates, operation type), quarantine rows with a wrong column count, validate row count and total against metadata. Return Pydantic models. Tests first, on the S2 fixtures. Add a CLI command `uv run skarbonka inspect <file>` that prints only stats (row count, total, date range, operation types with counts, warnings), never rows.

Done when: tests are green and you ran `inspect` on a real file **in your own terminal** (not via `!` in Claude Code) and the numbers match the bank. You may paste the `inspect` output into Claude Code.

## S4. Database schema and import (Opus)

Requirements: FR-01, FR-09, FR-10, FR-14, FR-16, NFR-04, NFR-05.

> Design SQLAlchemy models and the first Alembic migration for: accounts, import_batches, raw_rows, transactions, merchants, merchant_aliases, categories, rules, allocations, settlements, audit_log (see "Data model" in docs/context.md). Then the import service: file → parser → dedup by transaction number or fingerprint → store transactions with one allocation each → import stats. Endpoints `POST /imports` (multiple files) and `GET /imports`. Integration tests against Postgres in Docker. Plan and schema first, for approval.

Done when: importing a fixture twice yields 0 duplicates and the import history shows the counts.

## S5. Merchants and rule engine

Requirements: FR-21, FR-30 to FR-34, FR-13.

> Add merchant normalization (split the counterparty field into name, city and country; strip the country code only at the end; strip prefixes like "BKG*" and store numbers) and a prioritized rule engine (JSONB conditions: merchant, whole-word or regex phrase, amount range, account, weekday, type; outcome: category and/or personal). Seed the starting categories and rules from docs/context.md. Endpoint to preview a rule against history. Detect transfers between own accounts. Tests, including the "POLOmarket" case.

Done when: Lidl, Biedronka and Auchan variants in the fixtures map to one merchant each, and the notebook rules work.

## S6. ML classifier (Opus)

Requirements: FR-35 to FR-37.

> Build a category and personal-flag classifier in `backend/src/skarbonka/categorization/`: description embedding (sentence-transformers, a multilingual model from docs/context.md, CPU-friendly) plus features (amount, weekday, type, account), calibrated logistic regression. Training and evaluation script (macro-F1, per-category accuracy, comparison with the notebook regexes) run locally, model saved to `models/` (gitignored). Categorization pipeline: manual > rules > merchant memory > ML > review queue. Use the S2 fixtures.

Done when: you ran training and evaluation yourself on real data and pasted only the metrics into Claude Code.

## S7. Frontend skeleton and transaction list

Requirements: FR-20, FR-23, FR-24, NFR-17.

> Scaffold `frontend/` (Vite, React, strict TypeScript, TanStack Query and Router, shadcn/ui, Tailwind, light and dark mode, UI strings in Polish). First screen: transaction list with filters (period, category, merchant, personal, needs review, text), a personal toggle per row, multi-select with bulk category change. Add the backend endpoints it needs. Plan the screens first.

Done when: you can browse fixture transactions and mark personal ones.

## S8. Review queue and receipt splits

Requirements: FR-25, FR-26, FR-28, FR-29.

> Add a "needs review" queue with keyboard shortcuts (category, personal, next) and a dialog to split a transaction into parts (amount, category, personal; parts must sum to the transaction amount). Every change goes to audit_log. After a manual correction, offer "turn this into a rule?".

Done when: reviewing a fixture week takes a few minutes without the mouse.

## S9. Settlements

Requirements: FR-50 to FR-53, FR-58.

> Add settlements: create for a period (default: the day after the last one), only ING allocations that are not personal and not in another settlement; preview with total, per-category totals and comparison with the previous period; statuses draft, sent, paid; lock transactions once sent; match the refund transfer. Tests on totals to the grosz. UI screen.

Done when: a fixture settlement total matches a manual calculation.

## S10. PDF and Excel report

Requirements: FR-54, FR-55.

> Generate the settlement report: PDF (Jinja2 + WeasyPrint in a container) with the refund total, category pie and bar charts, the list, and comparison with the previous period; Excel in the old notebook layout (Data, Sklep, Kategoria, Kwota, per-category sums, SUMA, filename `rozliczenie_d.m-d.m.yyyy.xlsx`) with currency formatting. Downloadable from the UI. Report text in Polish.

Done when: the PDF opens correctly on a phone and Polish characters render.

## S11. Gmail draft

Requirements: FR-56, FR-57.

> Integrate the Gmail API (OAuth, token stored locally outside the repo) to create a draft with the PDF and Excel attached and a body from a template. Google Cloud setup guide in `docs/gmail.md`. Recipients and template in settings.

Done when: the draft appears in your Gmail.

## S12. Basic dashboard

Requirements: FR-70 to FR-72.

> Add a dashboard: view switch (Settlements, My spending), category pie and bar charts for a period (ECharts), tiles (total, change vs previous period, needs review, amount awaiting refund). Clicking a category filters the transaction list.

## S13. MVP acceptance

Requirements: MVP success metrics in docs/goals.md, NFR-12, NFR-13.

> Go through the MVP success metrics in docs/goals.md: add missing tests (parser and settlement coverage at least 90%), a regression test "same total as the old notebook" on a fixture, and README setup instructions. List anything that still fails the criteria.

Done when: you do your first real settlement without the notebook.
