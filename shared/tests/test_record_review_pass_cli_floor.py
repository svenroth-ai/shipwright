"""`close-missing` versus the medium+ code-review floor.

Split out of ``test_record_review_pass_cli.py`` rather than appended to it: that
file was already 496 lines against a 300-line limit before this change, and
growing an oversize file is a ratchet regardless of whether a baseline entry
happens to exist for it. The pre-existing crossing is left alone — it is not
this change's to fix — but this change does not add to it.

What is pinned here is the narrowing of AC10. ``close-missing`` was the
documented one-command route out for a run already past its review phases when
the record landed; at medium+ it no longer makes such a run green, because a
record in which nothing was reviewed is exactly what the floor exists to catch.
Ruled by the operator, and de-risked by measurement: the migration window that
escape hatch was built for is closed (all 25 medium+ runs on record already
satisfy the floor), so nothing real is trapped.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))

from tools.verifiers.review_record_check import check_review_record  # noqa: E402

TOOL = str(REPO_ROOT / "shared" / "scripts" / "tools" / "record_review_pass.py")
RUN_ID = "iterate-2026-07-21-review-record"
DISPOSITION = "predates the per-run review record"


@pytest.fixture
def project(tmp_path: Path) -> Path:
    """A project whose iterate entry says `medium` — the floored complexity."""
    iterates = tmp_path / ".shipwright" / "agent_docs" / "iterates"
    iterates.mkdir(parents=True)
    (iterates / f"{RUN_ID}.json").write_text(json.dumps({
        "run_id": RUN_ID, "date": "2026-07-21T00:00:00+00:00", "type": "feature",
        "complexity": "medium", "branch": "iterate/review-record",
        "tests_passed": True,
    }), encoding="utf-8")
    (tmp_path / ".shipwright" / "planning" / "iterate").mkdir(parents=True)
    return tmp_path


def _close_missing(project: Path) -> int:
    result = subprocess.run(
        [sys.executable, TOOL, "close-missing", "--status", "not_run",
         "--disposition", DISPOSITION,
         "--project-root", str(project), "--run-id", RUN_ID],
        capture_output=True, text=True, encoding="utf-8",
    )
    return result.returncode


def _set_complexity(project: Path, complexity: str) -> None:
    entry = project / ".shipwright" / "agent_docs" / "iterates" / f"{RUN_ID}.json"
    data = json.loads(entry.read_text(encoding="utf-8"))
    data["complexity"] = complexity
    entry.write_text(json.dumps(data), encoding="utf-8")


def test_close_missing_does_not_satisfy_the_floor_at_medium(project: Path):
    """Closing everything as not_run must NOT green-light a medium+ run.

    Before the floor this command was a one-line route from "no reviews at all"
    to a passing F11 — the hole being closed.
    """
    assert _close_missing(project) == 0

    result = check_review_record(project, RUN_ID)
    assert result.ok is False
    assert "no code review ran" in result.detail


def test_close_missing_still_unblocks_a_small_run(project: Path):
    """At small the escape hatch is untouched — the floor is medium+ only."""
    _set_complexity(project, "small")

    assert _close_missing(project) == 0
    assert check_review_record(project, RUN_ID).ok


def test_close_missing_still_unblocks_a_trivial_run(project: Path):
    _set_complexity(project, "trivial")

    assert _close_missing(project) == 0
    assert check_review_record(project, RUN_ID).ok


def test_recording_one_real_review_clears_the_floor(project: Path):
    """The repair path the failure message names must actually work.

    A gate that blocks without a working way forward is a trap, so the
    remediation is exercised rather than asserted.

    `--provider` is not decoration here. The floor now asks whether a review
    HAPPENED, so the row must carry one of the four traces a real recording
    leaves; `--from none` with no payload produces exactly the evidence-free
    shape the floor rejects, and using it would have exercised a repair path
    that no longer repairs anything.
    """
    _close_missing(project)
    assert check_review_record(project, RUN_ID).ok is False

    result = subprocess.run(
        [sys.executable, TOOL, "record", "--review-type", "external_code",
         "--status", "completed", "--marker-status", "completed",
         "--from", "none", "--provider", "openrouter", "--force",
         "--project-root", str(project), "--run-id", RUN_ID],
        capture_output=True, text=True, encoding="utf-8",
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert check_review_record(project, RUN_ID).ok


def test_an_evidence_free_repair_does_not_clear_the_floor(project: Path):
    """The control for the test above: without `--provider` the same command
    writes a row indistinguishable from one nobody earned, and the floor says
    so instead of greening (`trg-51a57370`)."""
    _close_missing(project)

    result = subprocess.run(
        [sys.executable, TOOL, "record", "--review-type", "external_code",
         "--status", "completed", "--marker-status", "completed",
         "--from", "none", "--force",
         "--project-root", str(project), "--run-id", RUN_ID],
        capture_output=True, text=True, encoding="utf-8",
    )
    assert result.returncode == 0, result.stdout + result.stderr

    outcome = check_review_record(project, RUN_ID)
    assert outcome.is_failure
    assert "evidence" in outcome.detail.lower()
