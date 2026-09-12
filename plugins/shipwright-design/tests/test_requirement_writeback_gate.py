"""FR-01.04/AC11, via the real commands ``review-loop.md`` Option B/Option A
tell the design phase to run.

``test_skill_writeback_rules.py`` pins that the design skill's OWN prompt
correctly instructs invoking this mechanism (the runtime-prompt half that
cannot be unit-tested). This file proves the mechanism itself: a feedback
round that changes what a screen or flow *does* is only accepted as declared
when the requirement it belongs to was actually corrected — not merely
asserted — and a round that skips that correction is refused, fail-closed.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_TOOLS = _REPO_ROOT / "shared" / "scripts" / "tools"
_RECORD_CLI = _TOOLS / "record_requirement_impact.py"
_CHECK_CLI = _TOOLS / "check_design_round_declarations.py"
SPEC = ".shipwright/planning/01-checkout/spec.md"
RUN_ID = "design-run-2026-09-12"


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True,
                    capture_output=True, text=True)


def _write(repo: Path, rel: str, text: str) -> None:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _record(project: Path, *extra: str) -> tuple[int, dict]:
    proc = subprocess.run(
        [sys.executable, str(_RECORD_CLI), "--project-root", str(project),
         "--run-id", RUN_ID, "--phase", "design", "--scope", "round-2", *extra],
        capture_output=True, text=True, encoding="utf-8",
    )
    return proc.returncode, json.loads(proc.stdout)


def _check(project: Path) -> tuple[int, dict]:
    proc = subprocess.run(
        [sys.executable, str(_CHECK_CLI), "--project-root", str(project),
         "--run-id", RUN_ID],
        capture_output=True, text=True, encoding="utf-8",
    )
    return proc.returncode, json.loads(proc.stdout)


@pytest.fixture
def project(tmp_path: Path) -> Path:
    """A project whose requirement describes a one-step checkout."""
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "config", "user.email", "t@t")
    _git(tmp_path, "config", "user.name", "t")
    _write(tmp_path, SPEC,
           "# Checkout\n\n"
           "| FR-01.09 | Checkout | Must | The customer pays in one step. |\n\n"
           "### FR-01.09\n"
           "- (E) Given a basket, when the customer checks out, then they pay "
           "in one step.\n")
    _write(tmp_path, ".shipwright/designs/screens/03-checkout.html", "<html>one step</html>")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "base")
    return tmp_path


@pytest.mark.covers("FR-01.04/AC11")
def test_declaring_a_behaviour_change_without_correcting_the_requirement_is_refused(project):
    """FR-01.04/AC11: a round cannot claim its feedback changed what the flow
    DOES (``--impact modify``) unless the requirement it names was actually
    edited — asserting it is not enough, fail-closed."""
    code, out = _record(project, "--snapshot-baseline")
    assert code == 0, out

    # The screen changes (a confirm step is added) but spec.md is left alone.
    _write(project, ".shipwright/designs/screens/03-checkout.html",
           "<html>review, then confirm</html>")

    code, out = _record(project, "--impact", "modify", "--fr", "FR-01.09", "--worktree")
    assert code == 1
    assert out["success"] is False
    assert out["error"] == "requirement_impact_no_spec_touched"


@pytest.mark.covers("FR-01.04/AC11")
def test_declaring_a_behaviour_change_after_correcting_the_requirement_is_accepted(project):
    """FR-01.04/AC11: once the requirement is actually corrected to describe
    the new behaviour, the round's declaration is accepted, and finalization
    sees this round as declared rather than silent."""
    code, out = _record(project, "--snapshot-baseline")
    assert code == 0, out

    _write(project, ".shipwright/designs/screens/03-checkout.html",
           "<html>review, then confirm</html>")
    _write(project, SPEC,
           "# Checkout\n\n"
           "| FR-01.09 | Checkout | Must | The customer reviews the order, "
           "then confirms payment. |\n\n"
           "### FR-01.09\n"
           "- (E) Given a basket, when the customer checks out, then they "
           "review the order and confirm before paying.\n")

    code, out = _record(project, "--impact", "modify", "--fr", "FR-01.09", "--worktree")
    assert code == 0, out
    assert out["success"] is True
    assert out["touch_check"] != "skipped"

    code, out = _check(project)
    assert code == 0, out
