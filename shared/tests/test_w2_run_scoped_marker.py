"""W2 must judge the run-scoped marker, not merely notice it (AC7).

`record_review_pass.py` dual-writes `external_*review_state.json`: once at the
historic shared path and once under `<run_id>/`. The run-scoped copy is the
run-SPECIFIC evidence W2 has wanted since it labelled the shared file
"run-agnostic" — but crediting it by existence alone would have made W2's status
logic dead code for every run recorded through the new tool, so a marker with an
empty or garbage status would PASS where the identical content at the shared
path FAILs.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from tools.verifiers import iterate_compliance  # noqa: E402

RUN_ID = "iterate-2026-07-21-review-record"


@pytest.fixture
def proj(tmp_path: Path) -> Path:
    (tmp_path / ".shipwright" / "agent_docs" / "iterates").mkdir(parents=True)
    (tmp_path / ".shipwright" / "agent_docs" / "iterates" / f"{RUN_ID}.json").write_text(
        json.dumps({
            "run_id": RUN_ID, "date": "2026-07-21T00:00:00+00:00", "type": "feature",
            "complexity": "medium", "branch": "iterate/x", "tests_passed": True,
        }), encoding="utf-8")
    planning = tmp_path / ".shipwright" / "planning" / "iterate"
    (planning / RUN_ID).mkdir(parents=True)
    (planning / f"{RUN_ID}.md").write_text("# spec\n", encoding="utf-8")
    return tmp_path


def _run_scoped(proj: Path, marker: dict) -> None:
    path = proj / ".shipwright" / "planning" / "iterate" / RUN_ID / "external_review_state.json"
    path.write_text(json.dumps(marker), encoding="utf-8")


def _shared(proj: Path, marker: dict) -> None:
    path = proj / ".shipwright" / "planning" / "iterate" / "external_review_state.json"
    path.write_text(json.dumps(marker), encoding="utf-8")


def _check(proj: Path):
    return iterate_compliance.check_w2_external_review_marker(proj, RUN_ID)


def test_a_completed_run_scoped_marker_passes(proj):
    _run_scoped(proj, {"status": "completed", "provider": "openrouter"})
    assert _check(proj)["status"] == "PASS"


def test_a_skipped_run_scoped_marker_passes_with_its_reason(proj):
    _run_scoped(proj, {"status": "skipped_user_opt_out", "reason": "offline demo"})
    finding = _check(proj)
    assert finding["status"] == "PASS"
    assert "offline demo" in json.dumps(finding)


def test_a_run_scoped_marker_with_a_garbage_status_does_not_pass(proj):
    _run_scoped(proj, {"status": "complete"})  # typo — not the vocabulary
    assert _check(proj)["status"] == "FAIL"


def test_a_run_scoped_marker_with_no_status_does_not_pass(proj):
    _run_scoped(proj, {"provider": "openrouter"})
    assert _check(proj)["status"] == "FAIL"


def test_a_malformed_run_scoped_marker_fails(proj):
    path = proj / ".shipwright" / "planning" / "iterate" / RUN_ID / "external_review_state.json"
    path.write_text("{not json", encoding="utf-8")
    assert _check(proj)["status"] == "FAIL"


def test_a_bad_run_scoped_marker_is_not_laundered_by_a_good_shared_one(proj):
    """Run-specific evidence decides alone. Falling back to the run-agnostic
    shared file after rejecting it would launder a bad marker into a pass."""
    _run_scoped(proj, {"status": "complete"})
    _shared(proj, {"status": "completed"})
    assert _check(proj)["status"] == "FAIL"


def test_the_shared_marker_still_works_when_there_is_no_run_scoped_one(proj):
    """No regression for runs on the historic layout."""
    _shared(proj, {"status": "completed"})
    assert _check(proj)["status"] == "PASS"
