"""Tests for shared/scripts/checks/check_session_role.py.

Exit-code contract:
- 0 — no marker (default permissive)
- 0 — role canonical
- 0 — role secondary + SHIPWRIGHT_SECONDARY_PUSH_AUTH=1
- 1 — role secondary + no env override

Invocation: subprocess (matches how F11 / pre-push hooks call it).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from lib.session_role import write_role


_REPO_ROOT = Path(__file__).resolve().parents[2]
_CHECK_SCRIPT = (
    _REPO_ROOT / "shared" / "scripts" / "checks" / "check_session_role.py"
)


def _run(project_root: Path, env_override: bool = False) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env.pop("SHIPWRIGHT_SECONDARY_PUSH_AUTH", None)
    if env_override:
        env["SHIPWRIGHT_SECONDARY_PUSH_AUTH"] = "1"
    return subprocess.run(
        [
            sys.executable,
            str(_CHECK_SCRIPT),
            "--project-root",
            str(project_root),
            "--json",
        ],
        env=env,
        capture_output=True,
        text=True,
    )


def test_check_script_exists():
    assert _CHECK_SCRIPT.exists(), (
        f"check_session_role.py missing at {_CHECK_SCRIPT}"
    )


def test_missing_marker_exits_zero(tmp_project):
    """Default permissive: no marker → push allowed."""
    result = _run(tmp_project, env_override=False)
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["decision"] == "allow"
    assert payload["reason"] == "no_marker"


def test_canonical_role_exits_zero(tmp_project):
    write_role(
        tmp_project,
        role="canonical",
        session_id="sess-1",
        worktree_path=str(tmp_project),
    )
    result = _run(tmp_project, env_override=False)
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["decision"] == "allow"
    assert payload["reason"] == "canonical"


def test_canonical_role_exits_zero_even_with_env(tmp_project):
    """Env override is no-op when role is already canonical."""
    write_role(
        tmp_project,
        role="canonical",
        session_id="sess-1",
        worktree_path=str(tmp_project),
    )
    result = _run(tmp_project, env_override=True)
    assert result.returncode == 0


def test_secondary_no_env_blocks(tmp_project):
    write_role(
        tmp_project,
        role="secondary",
        session_id="sess-1",
        worktree_path=str(tmp_project),
    )
    result = _run(tmp_project, env_override=False)
    assert result.returncode == 1, (
        "secondary without override must exit 1"
    )
    payload = json.loads(result.stdout)
    assert payload["decision"] == "block"
    assert payload["reason"] == "secondary_no_override"


def test_secondary_with_env_allows(tmp_project):
    write_role(
        tmp_project,
        role="secondary",
        session_id="sess-1",
        worktree_path=str(tmp_project),
    )
    result = _run(tmp_project, env_override=True)
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["decision"] == "allow"
    assert payload["reason"] == "secondary_with_override"


def test_human_readable_output_when_no_json_flag(tmp_project):
    """Default output: BLOCK or ALLOW prefix on stdout, detail on stderr."""
    write_role(
        tmp_project,
        role="secondary",
        session_id="sess-1",
        worktree_path=str(tmp_project),
    )
    env = os.environ.copy()
    env.pop("SHIPWRIGHT_SECONDARY_PUSH_AUTH", None)
    result = subprocess.run(
        [
            sys.executable,
            str(_CHECK_SCRIPT),
            "--project-root",
            str(tmp_project),
        ],
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "BLOCK" in result.stdout
    assert "secondary" in result.stderr.lower()


@pytest.mark.parametrize(
    "role,env_override,expected_exit",
    [
        ("canonical", False, 0),
        ("canonical", True, 0),
        ("secondary", False, 1),
        ("secondary", True, 0),
    ],
)
def test_decision_matrix(tmp_project, role, env_override, expected_exit):
    """Parametrized matrix covering all four corners of the decision."""
    write_role(
        tmp_project,
        role=role,
        session_id="sess-matrix",
        worktree_path=str(tmp_project),
    )
    result = _run(tmp_project, env_override=env_override)
    assert result.returncode == expected_exit, (
        f"role={role} env_override={env_override} expected exit "
        f"{expected_exit}, got {result.returncode}: {result.stderr}"
    )
