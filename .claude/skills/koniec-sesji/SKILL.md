---
name: koniec-sesji
description: Close the current coding session: verify, log progress, propose a commit.
disable-model-invocation: true
---

Close the session.

1. Run the full checks from CLAUDE.md (tests, ruff, mypy; frontend lint and build if frontend changed). Report only pass/fail and the first error of each failure.
2. Append an entry to `docs/progress.md` (newest at the bottom), max 10 lines:
   `## <date> S<n>: <title>` then: done, not done, decisions, issues noticed out of scope, next step.
3. Show `git status` and propose one conventional commit message. Do not commit until the user confirms.
