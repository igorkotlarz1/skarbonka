# Milestones: pytest gates and hard parts

Used by `/milestone-skarbonka N`. Milestone MN = task `## SN.` in `docs/session-plan.md`. Each section lists:

- **Gate**: behaviours that `backend/tests/milestones/test_mNN_*.py` must prove. All gates M1..MN stay green afterwards (regression bracket).
- **Hard parts**: where the docs are optimistic and practice usually bites. Plan for them up front.
- **Owner**: steps only the owner can do (real data, accounts, eyes on output).

Gate rules: synthetic fixtures only; no `skip` for a missing service (a missing Postgres is a failure with a clear message); never weaken a gate to get green.

---

## M1. Repository skeleton

**Gate**
- `GET /health` returns 200 and `{"status": "ok"}` (FastAPI `TestClient`).
- Settings load from env with `SKARBONKA_` prefix; a missing required value raises a clear error.
- Privacy guard: `.gitignore` ignores `data/x.csv` and `*.csv` outside `backend/tests/fixtures/` (check with `git check-ignore`); the hook `.claude/hooks/block_raw_data.py` exits 2 for a tool input containing `data/` and 0 for `metadata/` (run it as a subprocess with JSON on stdin).
- DB smoke: an engine from settings runs `SELECT 1` and `CREATE EXTENSION IF NOT EXISTS vector` on the compose Postgres.

**Hard parts**
- Docker Engine in WSL without Docker Desktop: needs systemd and the `docker` group. `permission denied on /var/run/docker.sock` means the terminal was not reopened after `usermod`.
- Use the `pgvector/pgvector:pg17` image. Plain `postgres:17` has no `vector` extension.
- mypy strict with Pydantic and SQLAlchemy needs the `pydantic.mypy` plugin; SQLAlchemy 2 typing works without the old stubs (do not install `sqlalchemy-stubs`).
- `.env` is denied to Claude Code: commit `.env.example` and read settings through pydantic-settings only.
- CI has no compose: add a `services: postgres` job with the pgvector image and pass the URL by env.
- The repo must live in the WSL filesystem (`~/projects/skarbonka`), not `/mnt/c`, or tests and Docker volumes get slow and file watching breaks.

**Owner**: `docker compose up -d db` works on the laptop; CI is green on GitHub after the push.

## M2. Synthetic ING generator

**Gate**
- Generated file parses back with the stdlib `csv` module: metadata count and total equal the generated rows (Decimal, to the grosz).
- Deterministic: same seed → byte-identical file.
- Encodings: cp1250 and UTF-8 with BOM both round-trip Polish characters (`ąćęłńóśźż`).
- The 4 fixtures exist under `backend/tests/fixtures/ing/` and are tracked by git (not ignored).
- The malformed fixture really has one row with a wrong column count.

**Hard parts**
- The real export has trailing `;` and empty columns (22 fields against a 21-field header in the sample). The generator must reproduce this, or the parser will be tested against a cleaner file than reality.
- Declared `Liczba transakcji` and the present rows did not match in the anonymized sample (29 vs 16). Decide whether that was the anonymization or a real bank quirk; the owner checks on a fresh file.
- Card holds (`Kwota blokady`) may have an empty main amount. Ask the owner to confirm with column counts only.
- Fixtures must contain no real merchants with real store numbers or addresses from the owner's file. Use plausible invented ones.

**Owner**: compare one fixture with a real export side by side in your own editor (structure only) and report differences as a list of facts, without values.

## M3. ING parser and `inspect`

**Gate**
- All 4 fixtures parse: row count and total match metadata; amounts are `Decimal`; dates are `date`.
- Encoding detection: tries `utf-8-sig` strictly, then `cp1250`. Never fall back to `latin-1` (it never fails, so it hides broken characters).
- Header is found by column names, not by line number (a fixture with extra metadata lines still parses).
- Malformed row goes to quarantine with a reason; the rest still imports.
- A count or total mismatch produces a warning, not a crash.
- `skarbonka inspect <fixture>` prints counts, total, date range, operation types and warnings, and **no** counterparty names or titles (assert that no fixture merchant string appears in the output).

**Hard parts**
- Operation types beyond `TR.KART` (BLIK, transfers, refunds, holds) are unconfirmed. Unknown types must pass through with their raw code and `operation_kind="unknown"`, and be counted in `inspect`, not rejected.
- Polish number formats: `-1 234,56` may contain a non-breaking space as a thousands separator.
- Whether `Suma obciążeń` includes holds is unknown. Validate debits and credits separately and report both.
- Two `Waluta` columns with the same name: address columns by position after header detection, not by name.

**Owner**: run `uv run skarbonka inspect data/<file>.csv` in a separate terminal on 2–3 real exports and paste only the output. Unknown types and mismatches feed back into the generator (M2) as new fixtures.

## M3.5. Revolut travel import and currency conversion

Travel spending from Revolut, summarised in PLN and EUR. It never enters the parents' settlement (settlements stay ING-only).

**Gate**
- Revolut fixtures (EUR, GBP, PLN, SEK, DKK, NOK, CZK, plus USD for subscriptions) parse: columns by name, amounts as `Decimal` in the account currency, `Started`/`Completed` dates as `date`, fee separate from amount.
- Only `COMPLETED` rows are imported; `PENDING`, `REVERTED` and `DECLINED` are counted in a warning, not imported.
- Exchanges between own pockets and top-ups are flagged `internal` and excluded from spending totals (an exchange appears as two rows, one per currency).
- NBP client: for a transaction date, the rate is table A mid from the **last business day before** that date (weekends and Polish holidays roll back). Tested on recorded JSON responses; the test suite makes no network calls.
- The rate cache lives outside the repo (`~/.cache/skarbonka/fx/`), is reused offline, and one request covers a range (≤ 93 days per NBP query).
- Conversion: PLN amount = original × rate, rounded half-up to the grosz **per transaction**, then summed. EUR view = PLN amount ÷ EUR rate of the same day (NBP cross rate). The original amount and currency are never overwritten.
- Trip classification: every Revolut spending row counts as travel **except recurring subscriptions** (e.g. AI and API credits in EUR or USD), detected by a vendor list plus a monthly-repeat rule; subscriptions are reported separately, never in a trip total.
- `skarbonka trip-summary` prints per-currency totals, PLN total, EUR total, fees, internal transfers excluded, and the rate dates used, but no counterparty or description.
- `inspect` recognizes a Revolut file and prints Revolut stats; the ING path is unchanged (M3 gate stays green).

**Hard parts**
- **No API for personal accounts.** Revolut's API is for Business accounts; Open Banking access needs a licensed third party (an aggregator), which the CSV-only decision rules out. CSV export from the app is the way.
- **The CSV has no FX rate.** Since 2021 the export no longer includes the exchange rate of converted card payments. Revolut's own rate can only be inferred from an exchange pair or a card payment charged in another pocket; the NBP rate is the reference, and the difference is not reconstructable from the file.
- **One file per currency pocket** (or a combined export with a `Currency` column): the format must be confirmed. Balances per pocket must not be mixed.
- **Double counting with ING.** A Revolut top-up from ING appears in both banks (ING outgoing transfer, Revolut `TOPUP`). Both legs are internal, never spending.
- **Which date converts.** `Started Date` is when you paid; `Completed Date` is when it settled. Use `Started Date` for the rate and the trip window, state it in the summary.
- **Card refunds and reversals** can complete days later with a slightly different PLN value. Keep them as separate rows linked by description and amount, not merged.
- **NBP gaps.** No table on weekends and holidays; a trip starting on a Saturday needs Friday's (or earlier) rate. A missing currency in table A (all seven here are in table A) would need table B.
- **Rounding.** Converting per row and summing differs from converting the sum by a few grosze. The gate fixes per-row rounding; the summary shows it.
- **Schema impact on M4.** Transactions must carry `currency` and the original amount from the start; PLN and EUR values are derived (computed or cached), never stored as the only amount.

**Owner**: export one real Revolut statement (all pockets) and run `uv run skarbonka inspect ../data/<file>.csv` in your own terminal; paste only the output. Decided 2026-11-20: EUR view uses NBP rates (one source); all Revolut spending is travel except recurring subscriptions, and vendor names drive the split. Still open: grouping travel rows into named trips (proposal: gaps of several days without foreign spending split trips; the owner can rename and adjust).

## M4. Schema and import (Opus)

**Gate**
- `alembic upgrade head` on an empty database, then `downgrade base`, then `upgrade head` again all succeed.
- Importing a fixture creates N transactions, each with exactly one allocation whose amount equals the transaction amount.
- Re-importing the same file adds 0 transactions; an overlapping file adds only the new ones.
- Two identical purchases on the same day (same amount, same merchant, no transaction number) are both kept.
- `POST /imports` with 2 files returns per-file stats; `GET /imports` lists the history.
- Amount columns are `NUMERIC(12,2)` (inspect the DB schema).

**Hard parts**
- **Holds become bookings.** A card hold and its later booked transaction can have different numbers and dates. Without handling, a re-import after the booking double-counts. Decide: skip holds, or match hold → booking by amount, card and date window.
- Rows without a transaction number need a fingerprint that includes an occurrence index within the file, or legitimate duplicates collapse.
- Alembic autogenerate does not know the pgvector type without importing `pgvector.sqlalchemy` in `env.py`.
- Integration tests need an isolated database: create `skarbonka_test` and wrap each test in a rolled-back transaction, or the tests leak state into each other.

**Owner**: approve the schema before the migration is written.

## M5. Merchants and rules

**Gate**
- Lidl, Biedronka and Auchan variants from the fixtures each map to one merchant.
- `POLOmarket` stays `POLOmarket`; the country code is stripped only at the end of the field.
- `BP` matches only as a whole word (not inside `BPH` or `UBP`).
- Rules apply in priority order; a higher-priority rule wins over a lower one.
- The notebook rules from `docs/context.md` reproduce the notebook categories on a fixture.
- Rule preview returns the count and a sample of affected history without changing anything.
- A transfer between two own accounts is flagged internal and never lands in a settlement.

**Hard parts**
- The counterparty field mixes name, street and city separated by double spaces, but not always: some merchants have only a name, some have a payment processor prefix (`BKG*`, `PAYU*`, `SumUp *`).
- Store numbers and city changes create endless aliases. Keep the alias table and let the owner merge merchants rather than chasing a perfect normalizer.
- JSONB rule conditions are easy to write and hard to validate: keep a Pydantic schema for conditions and reject unknown keys.

## M6. ML classifier (Opus)

**Gate**
- Training on a synthetic labelled set runs end to end and writes a model plus a metrics JSON to a temporary `models/` directory.
- The evaluation uses a split grouped by merchant (no merchant in both train and test).
- Predicted probabilities are calibrated: the outputs sum to 1 and each class has a probability.
- Pipeline priority: manual > rule > merchant memory > ML > review queue (one test per layer on crafted transactions).
- Below the threshold, a transaction goes to the review queue.

**Hard parts**
- Historical labels come from the notebook regexes, so they are not ground truth. Without the owner's ~300 hand-confirmed transactions, "beats the regexes" cannot be measured honestly.
- Heavy dependencies: `sentence-transformers` pulls in torch. Use the CPU wheel index in uv or the install takes gigabytes. Start with a small model (e.g. `multilingual-e5-small`) and download it once into a local cache outside the repo.
- Class imbalance (Inne, Zakupy spożywcze dominate): report macro-F1 and per-class numbers, not accuracy.
- Merchant memory already solves most repeat purchases; ML matters mainly for new merchants, so evaluate it on those separately.

**Owner**: label the gold set (a CSV in `data/`, never shown to Claude Code), run training and evaluation in a separate terminal, and paste only the metrics.

## M7. Frontend skeleton and transaction list

**Gate** (backend side, pytest)
- `GET /transactions` filters by period, category, merchant, personal, needs-review and text, and paginates.
- `PATCH` on an allocation toggles personal and writes an audit_log row.
- A bulk category change updates all selected allocations in one database transaction.
- Frontend: `npm run build` and `npm run lint` pass (checked in the close step, not in pytest).

**Hard parts**
- First frontend for the owner: keep components few and explain the structure in the brief.
- shadcn/ui and Tailwind versions move fast; follow the current shadcn install guide for Vite rather than older examples.
- API types: generate TypeScript types from the FastAPI OpenAPI schema (a dependency that needs approval) instead of writing them by hand.
- Use a Vite dev proxy to avoid CORS during development.

## M8. Review queue and splits

**Gate**
- Splitting a transaction into parts that sum exactly to the amount succeeds; a part sum off by 0.01 is rejected.
- Signs are consistent (debits negative in every part).
- A split replaces the single allocation; the original transaction row is unchanged.
- Every change writes audit_log in the same database transaction (simulate a failure → nothing is written).
- After a manual correction, the API returns a rule suggestion.
- A transaction with an unknown merchant gets an ML or local LLM proposal in `allocations.suggested_category_id`; the owner accepts it with one click (becomes `manual`, optionally remembered for the merchant) or picks another category. Nothing is applied without the click.

**Hard parts**
- A split of an already settled transaction must be refused or create a correction. Decide which before coding.
- Keyboard shortcuts clash with browser and input defaults. Keep them inactive while an input has focus.

## M9. Settlements

**Gate**
- A settlement for a period includes only non-personal ING allocations not in another settlement, and the total matches a hand calculation to the grosz.
- The default period starts the day after the previous settlement.
- After `sent`, its allocations cannot be edited (the API returns 409).
- An incoming transfer equal to the total is matched as the refund; a near amount is suggested, not matched.
- Refunds from shops (positive card transactions) reduce the settlement total.

**Hard parts**
- Transaction date or booking date for period boundaries: pick transaction date, state it in the report, and test the boundary days in `Europe/Warsaw`.
- A late-booked transaction from an already sent period: put it in the next settlement and show it as late.
- Parents may pay in two transfers or round the amount; matching must allow manual linking.

## M10. PDF and Excel

**Gate**
- The PDF builds, has the expected number of pages, and its text (via `pypdf`) contains the total and Polish characters intact.
- The Excel file reproduces the notebook layout (columns Data, Sklep, Kategoria, Kwota; per-category sums; `SUMA`), with the filename pattern `rozliczenie_d.m-d.m.yyyy.xlsx`, and the cell values are numbers with currency format.
- Sums in the Excel file equal the settlement total.

**Hard parts**
- WeasyPrint needs Pango and fonts at system level: build it in the Docker image and install a font with Polish glyphs (e.g. DejaVu), or characters break.
- ECharts is JavaScript and cannot render in WeasyPrint. Render the report charts server-side (e.g. matplotlib to SVG), which may need an approved dependency.
- Write values, not formulas, to the Excel file (or both); formulas show as 0 in some previews and in tests without a recalculation engine.

**Owner**: open the PDF on your phone and confirm it reads well.

## M11. Gmail draft

**Gate** (Gmail API mocked)
- Builds a MIME message with both attachments, the correct filenames and the template body.
- Calls `drafts.create` and never `messages.send` (assert on the mock).
- The token path is outside the repo and is never logged.

**Hard parts**
- A Google Cloud app in "Testing" status issues refresh tokens that expire after 7 days. Expect re-authorization weekly unless the app is published (verification may not be needed for personal use; check the current Google rules).
- OAuth from WSL: the browser opens on Windows and the localhost redirect must reach WSL. WSL2 forwards localhost by default; if not, use the console flow.
- Use the narrowest scope (`gmail.compose`).

**Owner**: create the Google Cloud project and OAuth client by following `docs/gmail.md`, run the first authorization yourself, and check that the draft appears.

## M12. Dashboard

**Gate**
- The aggregation endpoint returns per-category totals for a period that sum to the period total.
- "Change vs previous period" is computed on equal-length periods.
- Tiles: needs-review count and amount awaiting refund match the database.

**Hard parts**
- Keep aggregation in SQL, not in Python loops, or it slows down with years of history.
- Chart colours must stay readable in light and dark mode.

## M13. MVP acceptance

**Gate**
- Coverage of `importers/` and `settlements/` is at least 90%.
- Regression: on a fixture, the settlement total equals the total the old notebook produced for the same fixture (the expected value is stored in the test).
- Every MVP success metric in `docs/goals.md` maps to at least one gate test or an owner check listed in the brief.
- `docker compose up` from a clean clone starts the stack (smoke test of `/health` through the compose network).

**Hard parts**
- The notebook expects real-file quirks. Running it on a fixture may need small edits; the owner runs it and pastes the total.

**Owner**: run the old notebook on the regression fixture and paste the total; do your first real settlement without the notebook.

---

## M14. Home server deployment

**Gate**
- The LLM URL guard accepts loopback, RFC 1918, 100.64.0.0/10 and `*.ts.net` hosts and rejects public hosts and names; the app fails to start with a public URL.
- The production compose file publishes no Postgres port and binds the API to a configurable interface (parsed from the compose file in the test).
- Backup script round trip on the test DB: dump, encrypt, decrypt, restore into a scratch DB, row counts equal.

**Hard parts**
- The LLM URL points straight at the GPU PC (decided); a LiteLLM URL must not be configured, because the guard cannot see where LiteLLM routes.
- Docker on a host with Tailscale: binding to the tailnet IP before `tailscaled` is up fails at boot; needs a startup order or binding to the LAN IP.

**Owner**: install Ubuntu Server, Docker and Tailscale on the OptiPlex; run the deploy; open the app from the phone; pick and test the backup target.

---

## Known issues

Appended by `/milestone-skarbonka` when a hard part is likely to bite again. One line each: date, milestone, issue, workaround.

- 2026-11-20 M1: the privacy hook scans every tool input, including file contents written by Edit/Write. Never write the raw-folder name followed by a slash literally in code, tests or docs that Claude Code edits; build it at runtime (`"da" + "ta"`) or the edit is blocked.
- 2026-11-20 M1: Starlette's TestClient warns that `httpx` is deprecated in favour of `httpx2`. Harmless for now; switch only after checking the package and approving the dependency.
- 2026-11-20 M1: `alembic -x url=...` must come before the subcommand (`alembic -x url=... upgrade head`).
- 2026-11-20 M2: fixtures are byte-exact (CRLF, cp1250). `.gitattributes` marks `backend/tests/fixtures/**` as `-text`, so git with `core.autocrlf=true` (Windows) does not rewrite them. If the in-sync gate fails after a checkout on Windows, check this first.
- 2026-11-20 M2: the metadata block layout, the operation codes other than `TR.KART`, and the newest-first row order are ASSUMPTIONS in `synthetic_ing.py` until the owner checks a real export.
- 2026-11-20 M3: the "22 fields vs 21-field header" quirk may come from the owner's anonymization, not the bank (see the earlier sample notes). The parser does not count fields: a row is valid when its last filled cell is `Konto`, so both shapes parse. Confirm on a real export before relying on it anywhere else.
- 2026-11-20 M3: an export without Polish characters is valid UTF-8 and is reported as `utf-8`, not `cp1250`. Harmless (the text is identical), but do not treat the reported encoding as proof of the bank's encoding.
- 2026-11-20 M3: rows with only a hold amount are imported with `amount = hold` and counted under "Holds" in `inspect`. Whether the bank's totals include them is unknown; check the warnings on a real file with holds.
- 2026-11-21 M4: hold-only rows are skipped at import (counted as `holds_skipped`), unlike `inspect`, which still counts them as "Holds" with their hold amount. A bank summary that includes holds will then show a debit mismatch warning; that is expected, not a bug.
- 2026-11-21 M4: tests create and drop the databases `skarbonka_test` and `skarbonka_migrations` on the server from `SKARBONKA_TEST_DATABASE_URL`, so that user needs CREATEDB (the compose user is a superuser). Never point the test URL at a server holding real data you care about under those names.
- 2026-11-21 M4: an existing local database needs `uv run alembic upgrade head` once after pulling M4.
- 2026-11-21 M5: after pulling M5 run `uv run alembic upgrade head` and `uv run skarbonka seed`. Editing `backend/src/skarbonka/categorization/categories.toml` needs another `seed`; renaming a category in TOML creates a new one (the old stays, rules move to the new name).
