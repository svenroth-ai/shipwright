"""F21 regression (deep-audit 2026-06-10 WP3).

``check_s4_fr_preservation`` built its 6-line context window via
``"\n".join(lines[i:i+6] for ...)`` — the generator yields *lists*, so
``str.join`` raised ``TypeError: sequence item 0: expected str instance,
list found`` on the first matching line, aborting the whole spec category.

The trigger needs ``truly_removed`` non-empty (an FR heading deleted, so
its id is in the diff '-' lines but NOT in the '+' lines) AND that same id
still present in the current spec body on an unchanged context line, so
``if fr_id in line`` matches and the buggy join executes.

Lives in its own module rather than ``test_spec_checks.py`` because that
file already sits at its grandfathered bloat-baseline ceiling.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from lib import phase_quality as pq  # noqa: E402
from tools.verifiers import spec_checks as sc  # noqa: E402


def _init_git_repo(proj: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=str(proj), check=False)
    subprocess.run(["git", "config", "user.email", "t@test"], cwd=str(proj), check=False)
    subprocess.run(["git", "config", "user.name", "Tester"], cwd=str(proj), check=False)
    subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=str(proj), check=False)


def _commit_all(proj: Path, msg: str) -> None:
    subprocess.run(["git", "add", "-A"], cwd=str(proj), check=False)
    subprocess.run(
        ["git", "commit", "-q", "--allow-empty", "-m", msg], cwd=str(proj), check=False,
    )


def _write_spec(proj: Path, content: str) -> None:
    (proj / ".shipwright" / "agent_docs" / "spec.md").write_text(content, encoding="utf-8")


def _setup_removed_fr_still_referenced(tmp_path: Path) -> None:
    """FR-3 heading deleted, but an FR-3 reference survives on an unchanged
    context line — the exact shape that drove the buggy join into a crash.
    """
    _init_git_repo(tmp_path)
    (tmp_path / ".shipwright" / "agent_docs").mkdir(parents=True, exist_ok=True)
    _write_spec(tmp_path, (
        "## FR-1: first\nSee also FR-3 below for context.\n"
        "status: deprecated\n**Acceptance Criteria:** b\n"
        "## FR-3: third\n**Description:** c\n**Acceptance Criteria:** d\n"
    ))
    _commit_all(tmp_path, "add specs")
    _write_spec(tmp_path, (
        "## FR-1: first\nSee also FR-3 below for context.\n"
        "status: deprecated\n**Acceptance Criteria:** b\n"
    ))
    _commit_all(tmp_path, "remove FR-3 heading, keep reference")


def test_s4_no_typeerror_when_removed_fr_still_referenced(tmp_path: Path):
    """Must return (not raise); deprecated marker near the surviving ref -> PASS."""
    _setup_removed_fr_still_referenced(tmp_path)
    f = sc.check_s4_fr_preservation(tmp_path)
    assert f["status"] == pq.STATUS_PASS


def test_s4_sibling_checks_unaffected(tmp_path: Path):
    """S4 returning cleanly lets the rest of the iterate spec dispatch run."""
    _setup_removed_fr_still_referenced(tmp_path)
    findings = sc.run("iterate", tmp_path, "iterate-x")
    ids = {f["id"] for f in findings}
    assert {"S2", "S3", "S4", "S5", "S9", "S10"}.issubset(ids)
