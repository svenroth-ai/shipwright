"""Canon **C3** — a DIFFERENT phase owns the note. Which of the two acted last?

Split out of ``test_c3_handoff_freshness.py`` at the 300-LOC limit; that file
keeps the same-phase rows and the module guards.

This is the branch that decides supersession, and it is the branch both
regressions of this check have lived in:

* **#467** passed a phase that skipped its step, because a shared run id matched.
* **This iterate's own round-2 draft** compared the two phases by the marker's
  EVENT anchor. ``record_event`` dedups ``phase_completed`` on ``(phase, splitId)``
  permanently, so a phase completing a second time inherits whatever anchor was
  newest — routinely the note owner's. Ordered by that the two read as
  simultaneous, and the phase that ran LATER was reported as superseded by the
  EARLIER one. A silent SKIP, in the exact shape the iterate exists to remove.

So the two phases are ordered against EACH OTHER on wall clock. Both completions
come from one producer calling ``datetime.now()``, which makes them mutually
comparable; a completion and a marker are not.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts" / "tools"))

from _c3_fixtures import (  # noqa: E402
    DAWN,
    EARLY,
    LATE,
    MID,
    OLDER,
    RUN,
    history_entries as _hist,
    write_handoff,
    write_run_config,
)

OTHER_RUN = "deploy-20260727-1200-later"
from verifiers.handoff_phase_canon import (  # noqa: E402
    check_c3_session_handoff_fresh_after_phase as check_c3,
)


def _project(root: Path, *, marker_phase: str, marker_run: str, marker_ts: str,
             history: dict) -> Path:
    write_handoff(root, phase=marker_phase, run_id=marker_run, timestamp=marker_ts)
    write_run_config(root, history)
    return root


# --- the regression this iterate exists for ----------------------------------

def test_a_phase_that_skipped_its_step_is_caught(tmp_path):
    """DEFECT 1 from #467, and the reason this iterate exists.

    build wrote the note. `test` completed AFTERWARDS and skipped its own C3
    step. Because both share one run id (the `:=` idiom), the predecessor's
    run-key comparison MATCHED and passed it. It must warn.
    """
    _project(tmp_path, marker_phase="build", marker_run=RUN, marker_ts=EARLY,
             history={"build": _hist((RUN, EARLY)), "test": _hist((RUN, LATE))})

    result = check_c3(tmp_path, "test")

    assert result.ok is False, result.detail
    assert "left no note of its own" in result.detail
    assert "build" in result.detail


def test_the_marker_timestamp_does_not_decide_a_cross_phase_verdict(tmp_path):
    """The round-2 defect, pinned. Both phases carry the SAME event anchor —
    which is what `record_event`'s permanent dedup produces — and only their
    wall clocks tell them apart. changelog ran last and owes a note."""
    _project(tmp_path, marker_phase="deploy", marker_run="deploy-1", marker_ts=EARLY,
             history={
                 "deploy": [{"run_id": "deploy-1", "event_at": EARLY, "at": EARLY}],
                 "changelog": [{"run_id": "cl-2", "event_at": EARLY, "at": LATE}],
             })

    result = check_c3(tmp_path, "changelog")

    assert result.ok is False, result.detail
    assert not result.is_skipped, "a later phase must not read as superseded"
    assert "left no note of its own" in result.detail


def test_a_day_precision_completion_never_silently_supersedes(tmp_path):
    """The shape the producer wrote until this iterate: `date` alone. Read as
    midnight UTC it lost every same-day comparison, so the phase that skipped its
    step got a SKIP whose text was flatly untrue. A day it cannot resolve inside
    must be SAID, never resolved by inventing an instant."""
    _project(tmp_path, marker_phase="build", marker_run=RUN, marker_ts=EARLY,
             history={"build": _hist((RUN, EARLY)),
                      "test": [{"run_id": RUN, "date": LATE[:10]}]})

    result = check_c3(tmp_path, "test")

    assert result.ok is False, result.detail
    assert not result.is_skipped
    assert "cannot tell" in result.detail


def test_the_owner_completing_again_after_the_note_hides_nothing(tmp_path):
    """The round-3 defect, pinned. `deploy` wrote the note at DAWN and completed
    again at LATE without re-writing it; `build` completed at MID and skipped its
    C3 step. Ordering against deploy's LATEST completion (LATE) reads build as
    superseded — a silent SKIP excusing a skipped step, and reachable on its own:
    `finalize_bundle` runs F5c then F5b, and F5b can `_abort`, leaving a phase's
    record a run ahead of the note it wrote.

    The note names a run, so the owner's completion FOR THAT RUN is what it must
    be ordered against."""
    _project(tmp_path, marker_phase="deploy", marker_run=RUN, marker_ts=DAWN,
             history={"deploy": _hist((RUN, DAWN)) + _hist((OTHER_RUN, LATE)),
                      "build": _hist((RUN, MID))})

    result = check_c3(tmp_path, "build")

    assert result.ok is False, result.detail
    assert not result.is_skipped, "a skipped C3 step must not read as superseded"
    assert "left no note of its own" in result.detail


def test_an_owner_with_no_completion_under_the_notes_run_is_stated(tmp_path):
    """The note names a run the owner's record does not hold, so the two cannot
    be ordered. Stated — never resolved by falling back to the owner's latest,
    which is what made the defect above silent."""
    _project(tmp_path, marker_phase="deploy", marker_run="deploy-ghost", marker_ts=DAWN,
             history={"deploy": _hist((RUN, LATE)), "build": _hist((RUN, MID))})

    result = check_c3(tmp_path, "build")

    assert result.ok is False
    assert not result.is_skipped
    assert "under the run the note names" in result.detail


# --- supersession is decided by time, not by pipeline order -------------------

def test_a_later_phases_note_supersedes_and_is_a_named_skip(tmp_path):
    """Auditing a finished pipeline: deploy wrote the note AFTER build finished,
    so build's own note is legitimately gone. Undeterminable, not a verdict."""
    _project(tmp_path, marker_phase="deploy", marker_run=RUN, marker_ts=LATE,
             history={"build": _hist((RUN, EARLY)), "deploy": _hist((RUN, LATE))})

    result = check_c3(tmp_path, "build")

    assert result.is_skipped
    assert result.ok is not True
    assert "superseded" in result.detail and "deploy" in result.detail


def test_a_stale_later_phase_note_does_not_excuse_a_rerun(tmp_path):
    """The hole a PIPELINE_PHASES ordering would have left (external plan
    review, openai R1): deploy's note is OLD, build was re-run afterwards and
    wrote nothing. Phase order says 'deploy is later, superseded'. Time says
    build ran last and owes a note."""
    _project(tmp_path, marker_phase="deploy", marker_run=OLDER, marker_ts=EARLY,
             history={"deploy": _hist((OLDER, EARLY)), "build": _hist((RUN, LATE))})

    result = check_c3(tmp_path, "build")

    assert result.ok is False, result.detail
    assert "left no note of its own" in result.detail


# --- what it cannot settle, it says -------------------------------------------

def test_a_marker_without_a_phase_cannot_be_ordered_against(tmp_path):
    """A marker that names no phase names no completion record either, so there
    is nothing to order this phase against. It must WARN, not skip: an
    unidentifiable owner is not evidence that this phase was superseded."""
    _project(tmp_path, marker_phase="", marker_run=RUN, marker_ts=LATE,
             history={"build": _hist((RUN, EARLY))})

    result = check_c3(tmp_path, "build")

    assert result.ok is False
    assert "(unnamed)" in result.detail


def test_an_owner_with_no_completion_record_is_stated(tmp_path):
    """The note names deploy, but deploy has no recorded completion — so which
    of the two acted last is unknowable. Stated, never assumed either way."""
    _project(tmp_path, marker_phase="deploy", marker_run=RUN, marker_ts=LATE,
             history={"build": _hist((RUN, EARLY))})

    result = check_c3(tmp_path, "build")

    assert result.ok is False
    assert "cannot tell" in result.detail


def test_an_unusable_completion_timestamp_is_stated_not_guessed(tmp_path):
    root = _project(tmp_path, marker_phase="deploy", marker_run=RUN, marker_ts=LATE,
                    history={})
    (root / "shipwright_run_config.json").write_text(
        json.dumps({"phase_history": {
            "build": [{"run_id": RUN, "at": "nonsense"}],
            "deploy": _hist((RUN, LATE)),
        }}),
        encoding="utf-8",
    )

    result = check_c3(root, "build")

    assert result.ok is False
    assert "cannot tell" in result.detail
