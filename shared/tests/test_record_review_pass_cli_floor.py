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

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _review_cli_harness import EXTERNAL_REVIEW_OUTPUT, SELF_REVIEW_REPLY, payload  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))

from lib.review_payloads import CANONICAL_PAYLOAD_BASENAMES  # noqa: E402
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


def _record_self(project: Path) -> None:
    """The one pass every complexity owes (U3) — recorded before closing the rest."""
    result = subprocess.run(
        [sys.executable, TOOL, "record", "--review-type", "self", "--status", "completed",
         "--from", "self-review", "--payload-file", payload(
             project, CANONICAL_PAYLOAD_BASENAMES["self"], SELF_REVIEW_REPLY),
         "--project-root", str(project), "--run-id", RUN_ID],
        capture_output=True, text=True, encoding="utf-8",
    )
    assert result.returncode == 0, result.stdout + result.stderr


def _close_missing(project: Path, *, code: str | None = "diff-below-threshold",
                   record_self: bool = True) -> int:
    if record_self:
        _record_self(project)
    result = subprocess.run(
        [sys.executable, TOOL, "close-missing", "--status", "not_run",
         "--disposition", DISPOSITION, *(["--reason-code", code] if code else []),
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
    """At small, `self` plus a coded close-missing still unblocks — the floor is medium+ only."""
    _set_complexity(project, "small")

    assert _close_missing(project) == 0
    assert check_review_record(project, RUN_ID).ok


@pytest.mark.covers("FR-01.11")
def test_trivial_closes_with_self_plus_the_one_default_code(project: Path):
    """U3: at trivial `self` + ONE `close-missing --reason-code trivial-auto` is the record."""
    _set_complexity(project, "trivial")

    assert _close_missing(project, code="trivial-auto") == 0
    assert check_review_record(project, RUN_ID).ok


@pytest.mark.covers("FR-01.11")
@pytest.mark.parametrize("complexity", ["trivial", "small", "medium", "large"])
def test_an_all_not_run_record_fails_at_every_complexity(project: Path, complexity: str):
    """U3: closing EVERY type not_run — `self` included — is a change nobody
    reviewed, and no complexity waves it through any more."""
    _set_complexity(project, complexity)

    assert _close_missing(project, code="trivial-auto" if complexity == "trivial"
                          else "diff-below-threshold", record_self=False) == 0
    result = check_review_record(project, RUN_ID)
    assert result.is_failure
    assert "`self` is 'not_run'" in result.detail


@pytest.mark.covers("FR-01.11")
@pytest.mark.parametrize("complexity", ["trivial", "small"])
def test_free_text_closures_fail_below_medium(project: Path, complexity: str):
    """U3: a disposition alone is not a reason any more — not even at trivial."""
    _set_complexity(project, complexity)

    assert _close_missing(project, code=None) == 0
    result = check_review_record(project, RUN_ID)
    assert result.is_failure and "without a reason_code" in result.detail


@pytest.mark.covers("FR-01.11")
def test_trivial_auto_is_refused_above_trivial(project: Path):
    """U3: from `small` up each type names its OWN code; the trivial default is not one."""
    _set_complexity(project, "small")

    assert _close_missing(project, code="trivial-auto") == 0
    result = check_review_record(project, RUN_ID)
    assert result.is_failure and "'trivial-auto' at small" in result.detail


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
         "--from", "external-review-json", "--provider", "openrouter", "--force",
         "--payload-file", payload(
             project, CANONICAL_PAYLOAD_BASENAMES["external_code"], EXTERNAL_REVIEW_OUTPUT),
         "--project-root", str(project), "--run-id", RUN_ID],
        capture_output=True, text=True, encoding="utf-8",
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert check_review_record(project, RUN_ID).ok


def test_an_evidence_free_repair_is_rejected_before_write(project: Path):
    """A completed external marker without its reviewer payload is not a
    review and cannot be written as one."""
    _close_missing(project)

    result = subprocess.run(
        [sys.executable, TOOL, "record", "--review-type", "external_code",
         "--status", "completed", "--marker-status", "completed",
         "--from", "none", "--force",
         "--project-root", str(project), "--run-id", RUN_ID],
        capture_output=True, text=True, encoding="utf-8",
    )
    assert result.returncode == 2, result.stdout + result.stderr

    outcome = check_review_record(project, RUN_ID)
    assert outcome.is_failure
    assert "no code review ran" in outcome.detail.lower()


def test_a_non_canonical_payload_basename_is_rejected(project: Path):
    """trg-3b206c08: a payload file must use its kind's ONE canonical name —
    the producer-side half of a family that had 40+ ad-hoc basenames on
    origin/main. A wrong name is a usage error, not silently accepted."""
    result = subprocess.run(
        [sys.executable, TOOL, "record", "--review-type", "external_code",
         "--status", "completed", "--marker-status", "completed",
         "--from", "external-review-json", "--provider", "openrouter",
         "--payload-file", payload(
             project, "external-code-review.json", EXTERNAL_REVIEW_OUTPUT),
         "--project-root", str(project), "--run-id", RUN_ID],
        capture_output=True, text=True, encoding="utf-8",
    )
    assert result.returncode == 2, result.stdout + result.stderr
    assert "external-code-review-raw.json" in result.stdout
    assert check_review_record(project, RUN_ID).ok is False
