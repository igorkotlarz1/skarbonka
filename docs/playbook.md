# Working with Claude Code on this project

## Privacy: the one rule that matters

Claude Code runs in Anthropic's cloud: everything it reads (files, command output) is sent to the model. So:

- Real CSVs live only in `data/` (gitignored).
- `.claude/settings.json` denies reading `data/`, and the hook `.claude/hooks/block_raw_data.py` blocks any tool (Bash, Read, Grep, Glob, Edit, Write) whose arguments point at `data/`. Grep and Glob also skip gitignored files.
- Run commands on real data (`uv run skarbonka inspect data/...`, model training) in a **separate terminal**, not via `!` in Claude Code, because `!` output goes into the conversation. Paste only stats.
- The hook needs `python3`, so run Claude Code inside WSL2, where the repo lives.

Check the guard: ask Claude Code to "show the first line of a file in data". You should see "Blocked: data/ holds real bank exports…". `/hooks` shows the hook is active.

## Session rhythm

1. `/clear` (fresh context; the old conversation costs nothing).
2. `/start-session N`: reads only the last entry of `docs/progress.md` and section SN of `docs/session-plan.md`, proposes a plan, and waits.
3. Approve the plan or fix it in one sentence.
4. Work in small steps: test, code, test. If Claude goes the wrong way, press `Esc` right away; `Esc Esc` (or `/rewind`) restores an earlier point.
5. `/end-session`: tests, lint, progress entry, commit message proposal. You commit.

## Saving tokens

| Habit | Why |
| --- | --- |
| `/clear` between sessions and unrelated tasks | Every message resends the whole conversation |
| `/rename` before `/clear`, then `/resume` | Return to an old session without keeping it open |
| After a long break, prefer a new session | The first message after a break reprocesses the whole context (cache expired) |
| Plan mode (`Shift+Tab`) at the start of a task | Cheaper than fixing code written in the wrong direction |
| Sonnet by default, Opus only in S4 and S6 (`/model`) | Sonnet handles most code and costs less |
| Lower `/effort` for simple tasks | Fewer thinking tokens |
| Specific prompts with file names | Claude doesn't search the whole repo |
| Single-file tests with `-q` | Short output, less context |
| `/compact` with instructions when a session grows | e.g. `/compact keep the task, changed files and test errors` |
| Check `/usage` and `/context` now and then | See what eats your limit and context |
| Disable unused MCP servers (`/mcp`) | Each adds to the context |
| No subagents or agent teams on this project | Each agent is a separate context and separate cost |
| Short CLAUDE.md (about 50 lines) | Loaded every session; domain knowledge lives in `docs/context.md`, read only when needed |

## Skills

A skill is a folder with a `SKILL.md` file. Claude sees only its description and loads the full text when it's used, so it costs little until invoked. Invoke one by typing `/name`, or Claude picks it up when it fits the task (unless the skill sets `disable-model-invocation: true`, like our two).

Where they live: project skills in `.claude/skills/<name>/SKILL.md` (in the repo), personal ones in `~/.claude/skills/`, and plugin skills installed with `/plugin`. Type `/` in Claude Code to see the full list.

### Project skills (in the starter pack)

| Skill | When |
| --- | --- |
| `/start-session N` | Start of every planned session |
| `/end-session` | End of every session |

### Built-in skills worth using

| Skill | When on this project |
| --- | --- |
| `/code-review` | Before merging bigger changes, especially the parser and settlements |
| `/simplify` | After finishing a feature, to simplify without bug hunting |
| `/security-review` | Before making the repo public (stage 5) and after adding Gmail API and text-to-SQL (stage 4) |
| `/debug` | When something breaks and the cause isn't obvious |
| `/fewer-permission-prompts` | After a few sessions: adds safe commands to the allow list |

Skip `/init`: `CLAUDE.md` already exists.

### From plugins (optional)

- `skill-creator` (`/plugin install skill-creator@claude-plugins-official`): helps write your own skills. Useful in stage 2 for a "new bank" skill when adding mBank.
- Browse the rest with `/plugin`. Install only what you actually use, because every skill's description is in context on every message. `/skill-doctor` shows which skills are costly or unused.

### Your own skills, later

- `new-migration`: model change, Alembic migration, upgrade and downgrade test.
- `new-bank` (stage 2): checklist for adding a bank parser (fixture generator, parser, `inspect`, tests).
- `evaluate-model` (stages 2–3): run evaluation, log to MLflow, compare with the active model.
