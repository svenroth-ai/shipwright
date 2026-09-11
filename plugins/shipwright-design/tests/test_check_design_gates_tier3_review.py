"""Regression tests for the external Tier-3 PR-review finding on
`check-design-gates.py`'s `--round` handling, iterate-2026-09-11-e1-checks-
plan-design. Split out from `test_check_design_gates.py` to stay under
that file's own size budget.
"""

import json
import subprocess
import sys
from pathlib import Path

SCRIPT = str(
    Path(__file__).resolve().parent.parent / "scripts" / "checks" / "check-design-gates.py"
)


def _git(cwd, *args):
    return subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True, check=True)


def test_a_relative_round_path_resolves_against_project_root_not_cwd(tmp_path):
    """A relative ``--round`` path used to resolve against the process's
    cwd instead of ``--project-root``: invoked from an unrelated directory,
    the round file was reported "absent" and the flagged-screen check
    silently no-op'd, instead of failing on the untouched screen."""
    project = tmp_path / "project"
    (project / ".shipwright" / "designs" / "screens").mkdir(parents=True)
    (project / ".shipwright" / "designs" / "screens" / "01-login.html").write_text(
        "<!-- Requirements: FR-01.01 -->\n<html><body>Login</body></html>", encoding="utf-8"
    )
    project.joinpath("design-feedback-round1.md").write_text(
        "# Design Feedback — Round 1\n\n## 01-auth\n\n"
        "### #1 Login — CHANGES\n\n**File:** screens/01-login.html  \n"
        "**FRs:** FR-01.01\n\n---\n\n",
        encoding="utf-8",
    )
    _git(project, "init", "-q")
    _git(project, "config", "user.email", "test@test.invalid")
    _git(project, "config", "user.name", "Test")
    _git(project, "add", "-A")
    _git(project, "commit", "-q", "-m", "init")

    unrelated_cwd = tmp_path / "somewhere-else"
    unrelated_cwd.mkdir()
    cmd = [
        sys.executable, SCRIPT, "--project-root", str(project), "--gate", "iteration",
        "--round", "design-feedback-round1.md",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", cwd=str(unrelated_cwd))
    assert proc.returncode == 1, f"stdout={proc.stdout!r} stderr={proc.stderr!r}"
    out = json.loads(proc.stdout)
    problems = next(g for g in out["gates"] if g["gate"] == "iteration")["problems"]
    assert "01-login.html" in problems[0]


def test_an_explicit_iteration_gate_without_round_is_a_usage_error(tmp_path):
    """External code review, iterate-2026-09-11-e1-checks-plan-design: an
    explicit --gate iteration used to silently no-op without --round,
    bypassing the flagged-screen check instead of failing the usage."""
    project = tmp_path / "project"
    project.mkdir()
    cmd = [sys.executable, SCRIPT, "--project-root", str(project), "--gate", "iteration"]
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 2, f"stdout={proc.stdout!r} stderr={proc.stderr!r}"
    out = json.loads(proc.stdout)
    assert out["error"] == "round_required"


def test_gate_all_still_no_ops_without_round(tmp_path):
    """--gate all has no round file at Option A finalization time — unlike
    the explicit iteration gate above, that must stay a silent no-op. Other
    gates in --gate all may still fail on this bare project; only the
    iteration row is under test here."""
    project = tmp_path / "project"
    project.mkdir()
    cmd = [sys.executable, SCRIPT, "--project-root", str(project), "--gate", "all"]
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    out = json.loads(proc.stdout)
    row = next(g for g in out["gates"] if g["gate"] == "iteration")
    assert row["ok"] and "no feedback round" in row["detail"]


def test_a_round_path_that_does_not_exist_is_a_usage_error(tmp_path):
    """A GIVEN but wrong ``--round`` path (bad round number, not yet
    written) used to collapse into the same silent no-op as omitting
    ``--round`` entirely — the same bypass class round_required closes,
    reached through a different input (code review, PR #726 round 6)."""
    project = tmp_path / "project"
    project.mkdir()
    cmd = [
        sys.executable, SCRIPT, "--project-root", str(project), "--gate", "iteration",
        "--round", "design-feedback-round9.md",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 2, f"stdout={proc.stdout!r} stderr={proc.stderr!r}"
    out = json.loads(proc.stdout)
    assert out["error"] == "round_not_found"
