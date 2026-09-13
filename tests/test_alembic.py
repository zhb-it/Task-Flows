"""Offline validation that Alembic is initialized correctly.

Runs `alembic history` (no database connection needed) as a subprocess to
confirm `alembic.ini` parses, `migrations/env.py` imports cleanly, and the
versions directory is discoverable. Generating or applying real migrations
requires a running PostgreSQL and is covered later (TASK-009 / TASK-012).
"""

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ALEMBIC_INI = PROJECT_ROOT / "alembic.ini"


def test_alembic_history_runs_offline() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(ALEMBIC_INI), "history"],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    # Alembic lists the tracked revisions without a DB connection. After
    # TASK-012 the initial `users` migration exists and must appear here.
    assert "create users" in result.stdout, result.stdout
