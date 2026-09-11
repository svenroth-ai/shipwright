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
    out = json.loads(proc.stdout)
    assert proc.returncode == 1, out
    problems = next(g for g in out["gates"] if g["gate"] == "iteration")["problems"]
    assert "01-login.html" in problems[0]
