"""PreToolUse hook: keep real bank exports out of Claude Code's context.

Blocks any tool call whose input mentions the top-level `data/` directory
(real ING exports live there). Exit code 2 blocks the call and shows the
message to Claude.
"""

import json
import re
import sys

# `data/` not preceded by a word character, so `metadata/` is allowed.
BLOCKED = re.compile(r"(?<![\w-])data[/\\]")


def strings(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for v in value.values() for s in strings(v)]
    if isinstance(value, list):
        return [s for v in value for s in strings(v)]
    return []


def main() -> int:
    event = json.load(sys.stdin)
    if any(BLOCKED.search(s) for s in strings(event.get("tool_input", {}))):
        print(
            "Blocked: data/ holds real bank exports and must not enter the "
            "conversation. Use synthetic fixtures in backend/tests/fixtures/, "
            "or ask the user to run the command in their own terminal and paste "
            "only aggregated output.",
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
