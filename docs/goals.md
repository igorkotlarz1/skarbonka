# Skarbonka: goals

> Local-first AI for settling household expenses. Every model runs locally; no financial data goes to the cloud.

## Problem

I buy groceries for the household and settle up with my parents: I pay everything upfront, and every week, two weeks or month I email them a PDF summary and an Excel list, and they refund 100%. Today this runs in a Jupyter notebook (`tracker.ipynb`) that needs hand-cleaned ING CSV files, drops personal purchases by row index, and categorizes with regexes.

## Product goals

1. **Painless settlement.** From an ING CSV to a Gmail draft with PDF and Excel in minutes, with no manual cleaning and no code edits.
2. **Trustworthy categories.** Rules, ML and a local LLM assign categories with a confidence score. The owner reviews only the uncertain ones, and the system learns from corrections.
3. **Personal kept apart.** One click marks a transaction (or a part of a split receipt) as personal, so it stays out of the settlement.
4. **Spending insight.** Dashboard with category shares, multi-year trends, and next-month forecasts with uncertainty intervals.
5. **Assistant.** Ask about spending in Polish; the assistant answers from the data and performs tasks (recategorize, draft a settlement) after approval.

## Learning goals

- Containerize the whole system (Docker Compose) on Windows with WSL2.
- Local LLMs on an RTX 2070 8 GB: Ollama, model selection and evaluation, structured output, tool calling.
- MCP, a tool-using agent, safe read-only text-to-SQL.
- Task queues (Celery + Redis), monitoring (Prometheus + Grafana), MLflow.
- Frontend in React + TypeScript (first time, with Claude Code's help).
- Time-series forecasting with conformal intervals and hierarchical reconciliation.

## Portfolio goals

- Public repository with synthetic data only, a demo mode, and green CI.
- README with an architecture diagram, screenshots, and model evaluation results (categorization, forecasts, assistant).
- Shows data science craft (metrics, calibration, backtesting) and engineering craft (tests, migrations, containers).

## MVP success metrics

- An ING file imports without manual fixes; row count and total match the bank's summary.
- Re-importing the same period adds 0 duplicates.
- The classifier beats the notebook's regexes on an owner-reviewed test set.
- Reviewing a week or month takes under 5 minutes.
- The settlement total matches a manual calculation to the grosz.
- PDF and Excel land as a Gmail draft.
- Everything starts with `docker compose up`.

## Stages

| Stage | Scope |
| --- | --- |
| MVP | ING CSV import and cleaning, deduplication, merchants, rules, ML classifier, review with receipt splits and personal flag, settlement, PDF + Excel, Gmail draft, basic dashboard |
| 2 Intelligence | LLM categorization layer, Celery + Redis, retraining from corrections, MLflow and analytics section, watched folder, mBank import |
| 3 Analytics | Trends, anomalies, per-category forecasts, external features, backtests, Grafana |
| 4 Assistant | MCP server, text-to-SQL agent, approved actions, email summary, voice |
| 5 Portfolio and parents | Demo data generator, README, public repo, login with a parent role, Tailscale, backups to a Raspberry Pi, receipt scanning |

## Non-goals

- Bank APIs or PSD2 aggregators (decision: CSV only, no data leaks).
- Cloud LLMs in the app (OpenAI, Anthropic, or others).
- A mobile app (desktop web for now).
- Currencies other than the PLN amount reported by the bank.
- mBank in the MVP (returns in stage 2).
