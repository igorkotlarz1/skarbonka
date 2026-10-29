# Skarbonka

Local-first app that imports ING bank CSV exports, categorizes transactions (rules → ML → local LLM), lets the owner mark personal spending, and produces a settlement (PDF + Excel + Gmail draft) for the owner's parents. Goals: `docs/goals.md`. Domain, CSV format, decisions: `docs/context.md` (read only when you need domain knowledge). Session plan: `docs/plan-sesji.md`. Progress log: `docs/progress.md`.

## Hard rules

- NEVER read, grep, list, or print anything under `data/`. It holds real bank exports. If you need real-data facts, ask the user to run a command in their own terminal and paste the aggregated output.
- Tests and fixtures use only synthetic data from `tests/fixtures/` (generated in the exact ING format). Never copy real values into code, tests, or docs.
- No cloud LLM APIs or keys in the app. All models run locally via Ollama.
- Money is `Decimal` in Python and `NUMERIC(12,2)` in Postgres. Never `float` for amounts. Timezone `Europe/Warsaw`.
- Bank transactions are immutable. Category, personal flag, and splits live in `allocations`.
- Do not name any directory or module `data` (the privacy hook blocks paths containing `data/`).

## Stack

Python 3.12, uv, FastAPI, Pydantic v2, SQLAlchemy 2.0 (typed, `Mapped[...]`), Alembic, PostgreSQL 17 + pgvector, pytest, Ruff, mypy (strict). Frontend: React + TypeScript (strict), Vite, TanStack Query/Router, shadcn/ui, Tailwind, ECharts. Reports: Jinja2 + WeasyPrint, XlsxWriter. Docker Compose for db and services; Ollama runs natively on the Windows host (`host.docker.internal:11434`).

## Layout

- `backend/src/skarbonka/` — `api/`, `importers/` (bank parsers, pure functions), `domain/` (models, services), `categorization/`, `settlements/`, `reports/`, `db/` (SQLAlchemy models, Alembic)
- `backend/tests/` — mirrors `src`; fixtures in `backend/tests/fixtures/`
- `frontend/` — Vite app
- `docs/` — goals, context, session plan, progress log

## Commands (run from `backend/` unless noted)

- Tests: `uv run pytest -q path/to/test_file.py` (run only what you touched; full suite at the end of a session)
- Lint and format: `uv run ruff check --fix . && uv run ruff format .`
- Types: `uv run mypy src`
- DB: `docker compose up -d db` (repo root), migrations `uv run alembic upgrade head`
- Frontend (in `frontend/`): `npm run dev`, `npm run lint`, `npm run build`

## Conventions

- Code, comments, commit messages, and README in English. UI strings in Polish.
- Conventional commits (`feat:`, `fix:`, `test:`, `chore:`, `docs:`).
- Parsers and money logic: write the test first, keep functions pure and small.
- Ask before adding a new dependency. Prefer the standard library and what the stack already has.
- Stay in the scope of the current session task. Note unrelated issues in `docs/progress.md` instead of fixing them.

## Working style (token budget)

- One session = one task from `docs/plan-sesji.md`. Start with a short plan, wait for approval, then implement.
- Read only the files the task needs. Do not scan the whole repo; use targeted search.
- Do not paste long test or build output back; summarize failures (first error, file, line).
- When the task is ambiguous, ask one concise question instead of guessing.

## Compact instructions

When compacting, keep: the current session task and its acceptance criteria, files changed so far, failing tests and their errors, and decisions made. Drop exploration output.
