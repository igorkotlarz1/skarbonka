"""The frontend's types are generated from `frontend/openapi.json`; it must match the API."""

from pathlib import Path

from skarbonka.api.openapi import render

SNAPSHOT = Path(__file__).resolve().parents[3] / "frontend" / "openapi.json"


def test_frontend_openapi_snapshot_is_current() -> None:
    assert SNAPSHOT.read_text(encoding="utf-8") == render(), (
        "API changed: run `npm run api:types` in frontend/ and commit the result"
    )
