# Skarbonka: context

Domain, decisions and data format. Claude Code reads this only when it needs domain knowledge, not at the start of every session.

## How a settlement works

- The owner buys household goods by card or BLIK from an ING account and pays everything upfront.
- A settlement covers a chosen period (week, 2 weeks, month, or custom dates). The next one starts the day after the previous one ends.
- It includes only allocations from ING that are not personal and not in another settlement.
- The parents receive a PDF (total, category charts, list) and an Excel file by email, then refund 100% by bank transfer. Only the owner shops.
- Statuses: draft, sent, paid. A sent settlement locks its transactions.

## Glossary

| Term | Meaning |
| --- | --- |
| Transaction | Immutable bank row (date, amount, counterparty, title, transaction number) |
| Allocation | Part of a transaction with its own amount, category and personal flag. Allocations sum to the transaction amount. Unsplit transactions have one |
| Personal | Owner's own spending, excluded from settlements (e.g. Żabka, gym, Booking) |
| Merchant | Normalized name, e.g. "Lidl" for "LIDL PANEWICKA  KATOWICE  POL" |
| Rule | Conditions (merchant, phrase, amount range, account, weekday, type) and outcome (category, personal). Rules beat ML and LLM |
| Settlement | Set of allocations for a period, with a refund total and a report |
| Import | One uploaded CSV with metadata and stats (new, duplicates, quarantined) |

## ING CSV format

Based on an anonymized "Lista transakcji" export (2026-03):

- Separator `;`. Encoding most likely Windows-1250 (to confirm on an original file). Also support UTF-8 and UTF-8 with BOM.
- About 19 metadata lines precede the table; the count depends on how many accounts were selected. They include the document number, generation date, selected accounts, date range (`2025-12-22 - 2026-02-21`), `Liczba transakcji: 29`, `Suma obciążeń (29): 2601,24 PLN`, `Suma uznań (0)`.
- Header row: `Data transakcji; Data księgowania; Dane kontrahenta; Tytuł; Nr rachunku; Nazwa banku; Szczegóły; Nr transakcji; Kwota transakcji (waluta rachunku); Waluta; Kwota blokady/zwolnienie blokady; Waluta; Kwota płatności w walucie; Waluta; Konto`, then empty columns.
- Footer: empty lines and `Dokument ma charakter informacyjny, nie stanowi dowodu księgowego`.
- Dates `YYYY-MM-DD`. Amounts use a decimal comma; debits are negative (`-83,25`).
- Transaction number wrapped in apostrophes: `'202605497304731334'`. Primary deduplication key.
- `Szczegóły` is the operation type padded with spaces, e.g. `TR.KART  `. Other codes (BLIK, transfers, credits) to be confirmed on a full export.
- `Dane kontrahenta`: name, street, city and country code separated by double spaces, e.g. ` LIDL PANEWICKA  KATOWICE  POL`, ` BKG*Booking.com Hotel  Amsterdam  N`, ` JMP S.A. BIEDRONKA 6279  KATOWICE`. Leading and trailing spaces.
- `Tytuł`: e.g. ` Płatność kartą 21.02.2026 Nr karty 4246xx1234`.
- `Konto`: account name (e.g. `KONTO Mobi 18-26`). One file can hold several accounts (e.g. Mobi and Otwarte Konto Oszczędnościowe); transfers between them are internal.

## Old notebook (`tracker.ipynb`), to be replaced

- `pd.read_csv(skiprows=20, skipfooter=3, usecols=[0,2,8], encoding='latin_1')`: hardcoded line counts and the wrong encoding (breaks Polish characters).
- `str.replace('POL','')` strips "POL" anywhere in a name (POLOmarket → "OMARKET").
- Personal: regex `ZABKA|GYM|BOOKING` plus manual `drop(index=[...])`.
- Regex categories, first match wins: Zakupy spożywcze (LIDL, BIEDRONKA, CARREFOUR, AUCHAN), Sport (SKARPA, LIMBO, GYM, PREZERO), Paliwo (ORLEN, BP, SHELL), Meble (IKEA, AGATA), Jedzenie/Przekąski (ZABKA), Podróże (WIZZ, RYAN, BOOKING), Jedzenie na Uczelni (STOLOWKA, STUDENCKA, TOMASZ KULA), otherwise Inne. Note: `BP` as a substring matches unrelated names.
- Excel: columns Data (index), Sklep, Kategoria, Kwota; below them per-category sums and `SUMA`; filename `rozliczenie_d.m-d.m.yyyy.xlsx`. Charts: category pie and bar.
- Historical category "labels" come from these regexes, so they are not ground truth. The owner will hand-confirm a test set of about 300 transactions.

## Starting category tree

Category names stay in Polish (they appear in the UI and reports).

| Main | Subcategories | Starting rules |
| --- | --- | --- |
| Jedzenie | Zakupy spożywcze, Przekąski, Jedzenie na uczelni, Restauracje | Lidl, Biedronka, Carrefour, Auchan → Zakupy spożywcze; Żabka → Przekąski; Stołówka Studencka, Tomasz Kula → Jedzenie na uczelni |
| Dom | Meble i wyposażenie, Chemia i higiena | IKEA, Agata → Meble i wyposażenie |
| Transport | Paliwo, Komunikacja | Orlen, BP (whole word), Shell → Paliwo |
| Sport | Siłownia, Aktywności | Skarpa, Limbo, Gym, Prezero |
| Podróże | Transport, Noclegi | Wizz, Ryanair → Transport; Booking → Noclegi |
| Zdrowie | Apteka, Lekarz | none |
| Inne | none | everything unmatched |

Starting "personal" rules: Żabka, Gym, Booking. The tree awaits the owner's confirmation.

## Architecture (summary)

- Everything local on Windows (Docker Desktop + WSL2). Only the finished report leaves the machine, via the Gmail API.
- Backend: Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2 + Alembic, uv, Ruff, mypy, pytest.
- Database: PostgreSQL 17 + pgvector (source of truth). DuckDB and Polars for notebook analytics.
- Frontend: React + TypeScript, Vite, TanStack Query and Router, shadcn/ui, Tailwind, ECharts.
- Reports: Jinja2 + WeasyPrint (PDF), XlsxWriter (Excel).
- Later: Celery + Redis (stage 2), MLflow (2), Prometheus + Grafana (3), MCP server (4).
- LLM: Ollama natively on Windows (RTX 2070 8 GB GPU); containers reach it at `host.docker.internal:11434`. Candidates: Qwen3.5-9B (agent), Bielik 11B or 4.5B v3 (Polish text), Gemma 4 E4B (categorization), BGE-M3 or multilingual-e5 (embeddings). Final choice after evaluation on the owner's data.

## Data model (summary)

`accounts`, `import_batches`, `raw_rows`, `transactions` (immutable), `merchants`, `merchant_aliases`, `categories` (2 levels), `rules` (conditions in JSONB), `allocations` (amount, category, personal, source, confidence, settlement), `settlements`, `audit_log`. Later: `forecasts`, `model_runs`, `assistant_messages`, `pending_actions`. Amounts as `NUMERIC(12,2)`.

## Categorization layers (in priority order)

1. Manual change of a single transaction.
2. Owner's rules.
3. Merchant memory (consistent category in history).
4. ML classifier (description embedding + amount, weekday, type, account), calibrated probabilities.
5. Local LLM for low confidence (stage 2).
6. Below the confidence threshold: the review queue.

## Privacy model

- Real bank files live only in `data/` (gitignored). Claude Code is blocked from reading it.
- Claude Code works only with synthetic files in `backend/tests/fixtures/`, generated in the exact ING format.
- The owner runs validation on real files in a separate terminal. The `inspect` command prints only stats (counts, totals, warnings, column names), never rows, and only that output may be pasted into Claude Code.
- No cloud LLM keys in the app.

## Decisions

| Decision | Reason |
| --- | --- |
| CSV import only, no aggregators | No consent to share bank data with third parties |
| Immutable transactions, changes in `allocations` | Receipt splits, full change history, reproducible settlements |
| Postgres as source of truth, DuckDB for analytics | Postgres for the app, DuckDB convenient in notebooks |
| Ollama outside Docker | Simplest GPU access on Windows |
| React instead of Streamlit | Nicer UI, future parent accounts, learning frontend |
| Gmail draft instead of auto-send in the MVP | Control over what reaches the parents |
| MVP with ING only | mBank returns in stage 2 |
| UI and reports in Polish, code and docs in English | Users are Polish; repo is a public portfolio and English saves tokens |
