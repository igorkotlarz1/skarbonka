"""Print the API's OpenAPI schema, so the frontend can generate its types without a running server.

Usage (from `backend/`): `uv run python -m skarbonka.api.openapi > ../frontend/openapi.json`
"""

import json
from typing import Any

from skarbonka.api.main import create_app


def schema() -> dict[str, Any]:
    return create_app().openapi()


def render() -> str:
    return json.dumps(schema(), indent=1, ensure_ascii=False) + "\n"


if __name__ == "__main__":
    print(render(), end="")
