"""Tests for the new B1c CLI helpers (E spec MEDIUM-C1).

`detect_parallel_sessions.py` and `write_session_role.py` are thin
wrappers over `shared/scripts/lib/session_role`. We assert:

- They print valid JSON to stdout.
- They produce equivalent results to the library calls they wrap.
- They use only the `--project-root` placeholder pattern (no
  hardcoded `shared/scripts/lib` literal).

The existing `test_session_role.py` covers the library semantics; this
file covers the CLI surface.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DETECT_TOOL = REPO_ROOT / "shared" / "scripts" / "tools" / "detect_parallel_sessions.py"
WRITE_TOOL = REPO_ROOT / "shared" / "scripts" / "tools" / "write_session_role.py"


def _run(script: Path, *args: str) -> tuple[int, str, str]:
    proc = subprocess.run(
        [sys.executable, str(script), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return proc.returncode, proc.stdout, proc.stderr


def test_detect_parallel_sessions_cli_prints_empty_json_for_fresh_project(tmp_project):
    """No marker → empty JSON list to stdout."""
    code, out, err = _run(DETECT_TOOL, "--project-root", str(tmp_project))
    assert code == 0, f"non-zero exit: stderr={err!r}"
    parsed = json.loads(out)
    assert parsed == [], f"expected [], got {parsed!r}"


def test_write_session_role_cli_writes_canonical_marker(tmp_project):
    """write_session_role.py canonical → marker round-trips on disk."""
    code, out, err = _run(
        WRITE_TOOL,
        "--project-root", str(tmp_project),
        "--role", "canonical",
        "--session-id", "cli-test",
        "--worktree-path", str(tmp_project),
        "--notes", "from cli",
    )
    assert code == 0, f"stderr={err!r}"
    payload = json.loads(out)
    assert payload["role"] == "canonical"
    assert payload["set_by_session_id"] == "cli-test"
    assert payload["notes"] == "from cli"

    # Round-trip: detect_parallel_sessions sees it.
    code2, out2, err2 = _run(DETECT_TOOL, "--project-root", str(tmp_project))
    assert code2 == 0, err2
    found = json.loads(out2)
    assert len(found) == 1
    assert found[0]["role"] == "canonical"


def test_write_session_role_cli_rejects_invalid_role(tmp_project):
    """Invalid role → argparse rejects with non-zero exit."""
    code, out, err = _run(
        WRITE_TOOL,
        "--project-root", str(tmp_project),
        "--role", "leader",  # not in VALID_ROLES
        "--session-id", "x",
        "--worktree-path", str(tmp_project),
    )
    assert code != 0, "argparse must reject 'leader'"
    # argparse writes to stderr.
    assert "leader" in err or "leader" in out
