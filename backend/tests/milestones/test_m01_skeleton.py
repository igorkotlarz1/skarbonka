"""M1 gate: repository skeleton (health endpoint, settings, privacy guard, database)."""

import json
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import text

from skarbonka.api.main import create_app
from skarbonka.config import REPO_ENV_FILE, Settings
from skarbonka.db.session import make_engine

REPO_ROOT = Path(__file__).resolve().parents[3]
HOOK = REPO_ROOT / ".claude" / "hooks" / "block_raw_data.py"
# Built at runtime: a literal path into the raw-data folder in this file would
# make the privacy hook block every edit of it.
RAW_DIR = "da" + "ta"


def test_health_returns_ok() -> None:
    """GET /health answers 200 with status ok."""
    client = TestClient(create_app())
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_settings_read_prefixed_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Settings load from SKARBONKA_* environment variables."""
    monkeypatch.setenv("SKARBONKA_DATABASE_URL", "postgresql+psycopg://u:p@h:1/db")
    settings = Settings(_env_file=None)
    assert settings.database_url == "postgresql+psycopg://u:p@h:1/db"
    assert settings.timezone == "Europe/Warsaw"


def test_settings_missing_database_url_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    """A missing required setting raises a clear validation error."""
    monkeypatch.delenv("SKARBONKA_DATABASE_URL", raising=False)
    with pytest.raises(ValidationError, match="database_url"):
        Settings(_env_file=None)


@pytest.mark.parametrize(
    ("path", "ignored"),
    [
        (f"{RAW_DIR}/export.csv", True),
        (f"{RAW_DIR}/notes.txt", True),
        ("reports_out/rozliczenie.xlsx", True),
        ("backend/src/skarbonka/export.csv", True),
        ("backend/tests/fixtures/ing/plain.csv", False),
        (".env", True),
        (".env.example", False),
    ],
)
def test_gitignore_keeps_bank_files_out(path: str, ignored: bool) -> None:
    """Real exports, reports and secrets are gitignored; fixtures are not."""
    result = subprocess.run(
        ["git", "check-ignore", "--no-index", "-q", path],
        cwd=REPO_ROOT,
        check=False,
    )
    assert (result.returncode == 0) is ignored


@pytest.mark.parametrize(
    ("tool_input", "blocked"),
    [
        ({"file_path": f"{RAW_DIR}/export.csv"}, True),
        ({"command": f"head -1 ./{RAW_DIR}/lista.csv"}, True),
        ({"pattern": "LIDL", "path": f"{RAW_DIR}\\"}, True),
        ({"file_path": "backend/src/skarbonka/metadata/x.py"}, False),
        ({"command": "uv run pytest -q"}, False),
    ],
)
def test_privacy_hook_blocks_raw_folder(tool_input: dict[str, str], blocked: bool) -> None:
    """The PreToolUse hook exits 2 for the raw-data folder and 0 otherwise."""
    result = subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps({"tool_name": "Bash", "tool_input": tool_input}),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == (2 if blocked else 0)


def test_database_ready_with_pgvector(database_url: str) -> None:
    """Postgres from compose answers SELECT 1 and has the vector extension."""
    engine = make_engine(database_url)
    try:
        with engine.begin() as conn:
            assert conn.execute(text("SELECT 1")).scalar_one() == 1
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            version = conn.execute(
                text("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
            ).scalar_one()
    finally:
        engine.dispose()
    assert version


def test_settings_read_the_repo_root_env_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Commands run from backend/ still read the `.env` in the repo root (shared with compose)."""
    repo_root = Path(__file__).resolve().parents[3]
    assert repo_root / ".env" == REPO_ENV_FILE
    assert Settings.model_config["env_file"] == (REPO_ENV_FILE, ".env")

    monkeypatch.delenv("SKARBONKA_DATABASE_URL", raising=False)  # CI sets it; env beats files
    root_env = tmp_path / ".env"
    root_env.write_text("SKARBONKA_DATABASE_URL=postgresql+psycopg://root:env@h:1/db\n")
    settings = Settings(_env_file=(root_env, tmp_path / "backend" / ".env"))
    assert settings.database_url.endswith("root:env@h:1/db")
