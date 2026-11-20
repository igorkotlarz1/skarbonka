---
name: milestone-skarbonka
description: Build one Skarbonka milestone M1–M13 end to end (plan, approval, pytest gate first, implementation, checks, Polish brief). Also status and brief.
disable-model-invocation: true
argument-hint: "[N | status | brief N]  e.g. 3"
---

Arguments: `$ARGUMENTS`

- A number `N` → run milestone MN (sections below).
- `status` → print a 6-line status: last `docs/progress.md` entry, which milestone gates pass (`uv run pytest -q tests/milestones` from `backend/`, summary line only), the next milestone, and open owner actions from the last brief. Stop.
- `brief N` → re-print `docs/briefs/MNN.md` (zero-padded, e.g. `M03.md`). Stop.

Milestone MN is section `## SN.` in `docs/session-plan.md` (task) plus section `## MN.` in `docs/milestones.md` (pytest gate, known hard parts, owner actions). Architecture and decisions are fixed in `CLAUDE.md` and `docs/context.md`; do not redesign them. If reality forces a change, stop and ask (step 4).

## Privacy (applies to every step)

`CLAUDE.md` hard rules always win. Never touch `data/`. When a step needs real data (comparing a fixture, `inspect`, training, evaluation), write the exact command for the owner to run **in a separate terminal**, never via `!`, and wait for the pasted aggregated output. Never ask for raw rows.

## 1. Load context (cheap)

Read only:
- the last entry of `docs/progress.md`;
- `## SN.` in `docs/session-plan.md`, e.g. `sed -n '/^## SN\./,/^## /p'`;
- `## MN.` in `docs/milestones.md`, the same way;
- `docs/context.md` sections only if the task names them.

Then run the existing gates: `cd backend && uv run pytest -q tests/milestones` (skip if `backend/` does not exist yet). Every earlier milestone gate must be green before starting. If one is red, report it and ask whether to fix it first.

## 2. Plan → APPROVAL GATE 1

Show, in at most 25 lines:
- the goal and its "Done when", in 2 lines;
- the gate tests you will write (file `backend/tests/milestones/test_mNN_<slug>.py`, one line per test: name → what it proves), covering every gate item in `## MN.`;
- files to create or change;
- new dependencies, each with one line on why (each needs approval);
- hard parts from `## MN.` that apply, plus any you foresee, and how you will handle them;
- at most 3 questions.

Then **stop and wait**. Continue only on an explicit "ok", "tak", "działaj" or a correction.

## 3. Gate tests first (red)

1. Write `backend/tests/milestones/test_mNN_<slug>.py`. Gate tests are black-box tests of the milestone's key behaviour (public functions, CLI, HTTP endpoints, DB state), using only synthetic fixtures from `backend/tests/fixtures/`. Add normal unit tests next to the code as usual. Gate tests are the bracket, not the whole suite.
2. Each test has a one-line docstring naming the gate item it proves.
3. Run them and show the red summary (count and the first failure reason). They must fail for the right reason (missing feature), not because of import or setup errors in the test itself.
4. Gate tests never `skip` because a service is missing. If Postgres is down, the test fails with a clear message (`docker compose up -d db`). A skipped gate counts as red.

## 4. Implement in small steps

- Loop: smallest change → run the gate file and the touched unit tests → next.
- Follow `CLAUDE.md`: Decimal for money, pure parser functions, test first for money logic, Polish UI strings.
- **Stop and ask** (do not work around it) when:
  - a new dependency is needed that was not approved in step 2;
  - the architecture, schema or a decision in `docs/context.md` would have to change;
  - a gate test seems wrong. Never weaken, skip or delete a gate test to get green; propose the change and wait;
  - the same failure survives 3 attempts;
  - real data is needed (Privacy section).
- Keep a running **hard-parts list** as you go: anything that was harder in practice than the docs suggested (format surprises, library quirks, WSL or Docker issues, ambiguous requirements, performance, flaky tests). For each: what happened, impact, what you did, and whether it is resolved. This list goes into the brief.

## 5. Close the gate

From `backend/`, report only pass/fail plus the first error of each failure:
1. `uv run pytest -q tests/milestones` (all gates M1..MN, regression);
2. `uv run pytest -q` (full suite), with coverage for M13;
3. `uv run ruff check . && uv run ruff format --check .`;
4. `uv run mypy src`;
5. if `frontend/` changed: `npm run lint && npm run build` in `frontend/`.

If anything is red, go back to step 4 unless the cause is outside scope; then say so in the brief.

## 6. Record

1. Append to `docs/progress.md` (English, max 10 lines): `## <YYYY-MM-DD> M<N>: <title>`, then done, not done, decisions, hard parts, next step.
2. If a hard part is likely to bite again (a format quirk, a library limit), add one line to `## Known issues` at the bottom of `docs/milestones.md`.
3. Write the brief to `docs/briefs/MNN.md` (template below) and print it in full.

## 7. Commit and PR → APPROVAL GATE 2

Show `git status --short` and one conventional commit message (e.g. `feat(importers): ING parser with metadata validation (M3)`). Do not commit, push or open a PR until the owner says so. Then push a branch `feat/mN-<slug>` and open one PR per milestone, with an English description in this shape:

- `## 🐷 MN · <Title>`, then a 2–3 sentence lead: what this unlocks;
- `### ✨ What's inside`: a table of Area → what you get;
- `### 🧪 Milestone gate`: the gate file and one bullet per behaviour it proves;
- `### 🚀 Try it`: copy-paste commands;
- `### 🌰 Lessons from practice`: the hard-parts list, honestly;
- `### 👀 Needs your eyes`: owner actions, if any;
- `### ✅ Checks`: a checklist with real results;
- a link to the Polish brief.

The owner reviews and merges. Never merge yourself. After the PR is open, remind them of the owner actions from the brief.

## Brief template (Polish; this is the only Polish document in docs/)

```markdown
# 🐷 Skarbonka · M<N>: <tytuł po polsku>
<data> · status: ✅ gotowe | ⚠️ gotowe z uwagami | ❌ niegotowe

## W skrócie
<2–3 zdania: co teraz działa, czego jeszcze nie ma>

## Bramka pytest
| Test | Sprawdza | Wynik |
| --- | --- | --- |
| test_... | ... | ✅ / ❌ |
Wszystkie bramki M1–M<N>: <x> passed, <y> failed · cały pakiet: <z> passed · ruff ✅ · mypy ✅

## Orzechy do zgryzienia
- **<problem>**: co się stało → wpływ → co zrobiłem → ✅ rozwiązane / ⚠️ obejście / ❌ otwarte
(„Brak” tylko wtedy, gdy naprawdę nic nie zaskoczyło.)

## Decyzje, które podjąłem
- <decyzja> (dlaczego)

## Twoja kolej
- [ ] <czynność właściciela, np. komenda do uruchomienia w osobnym terminalu, ze ścieżką>
- [ ] Zatwierdź commit: `<message>`

## Dalej
M<N+1>: <tytuł>. <1 zdanie: na co uważać>
```

Keep the brief under 45 lines. Write it plainly and honestly: a red test or an open problem goes in the brief, never smoothed over.
