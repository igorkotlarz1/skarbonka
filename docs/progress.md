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
