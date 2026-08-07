"""CLI-invocation-shape regression: write_decision_log.py with no PYTHONPATH.

Split out of ``test_write_decision_log.py`` (bloat-gate crossing) — a real
seam, not a budgetary one: this is a subprocess/CLI-shape test, distinct from
that file's in-process unit tests of ``append_decision``/``format_entry``.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "tools" / "write_decision_log.py"


def test_cli_runs_with_no_pythonpath_set(tmp_project):
    """The documented CLI form sets no PYTHONPATH (module docstring, build
    SKILL.md Step 9). Without its own sys.path bootstrap, the lazy
    `from lib.decision_log_index import refresh_best_effort` raises
    ModuleNotFoundError AFTER the ADR row is already written — this must not
    happen; a bare `uv run .../write_decision_log.py ...` must exit 0."""
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    proc = subprocess.run(
        [
            sys.executable, str(_SCRIPT), "--project-root", str(tmp_project),
            "--section", "Build — x", "--commit", "abc123",
            "--context", "why", "--decision", "what", "--consequences", "impact",
        ],
        capture_output=True, text=True, encoding="utf-8", env=env,
    )
    assert proc.returncode == 0, proc.stderr
    index = tmp_project / ".shipwright" / "agent_docs" / "decision_log_index.md"
    assert index.is_file()
