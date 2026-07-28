"""Canon **C3** — a matching run id is not, by itself, evidence of a note.

``build`` appends one completion per split under a STICKY run id
(``: "${SHIPWRIGHT_RUN_ID:=…}"``, assign-only-if-unset). Split 1 writes the
marker; split 2 completes and skips the marker write. Both entries carry the same
id, so a bare id match calls the second one a pass — which is
iterate-2026-07-27-c3-phase-content-key's silent pass wearing a new costume, and
``--preserve-canon-marker`` widens the window it lives in.

So when ONE run recorded several completions, the note must also not predate the
last of them. Two properties keep that from becoming a false accusation:

* **Scope.** Where a run recorded exactly one completion, the id already
  identifies it and the clock is never consulted. That is every phase except
  build's splits and a re-run under a sticky id.
* **One clock.** The comparison is marker ``timestamp`` vs. the completion's
  ``event_at``, both stamped from ``latest_event_dt``. Comparing the marker
  against the completion's wall-clock ``at`` instead — which is always later,
  because the canon block records the event, writes the marker, THEN appends —
  accused every re-run of skipping its own C3 step. ``test_completion_writers``
  drives the real tools through that exact sequence.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts" / "tools"))

import pytest  # noqa: E402

from _c3_fixtures import (  # noqa: E402
    EARLY,
    LATE,
    MID,
    RUN,
    write_handoff,
    write_run_config,
)
from verifiers.handoff_phase_canon import (  # noqa: E402
    check_c3_session_handoff_fresh_after_phase as check_c3,
)


def _anchored(*entries: tuple[str, str]) -> list[dict]:
    """Completions in the shape the writer emits: an `event_at` anchor plus the
    wall-clock keys. The anchor is what C3 reads; `at` deliberately differs from
    it so a test can never accidentally pass by comparing the wrong one."""
    return [
        {"run_id": run_id, "outcome": "completed", "event_at": anchor,
         "at": anchor.replace("+00:00", "") + ".900000+00:00", "date": anchor[:10]}
        for run_id, anchor in entries
    ]


def _splits(root: Path, *, marker_ts: str, entries: list[dict]) -> Path:
    """One phase, one marker, N recorded completions."""
    write_handoff(root, phase="build", run_id=RUN, timestamp=marker_ts)
    write_run_config(root, {"build": entries})
    return root


# --- the defect -----------------------------------------------------------

def test_a_later_split_that_skipped_the_marker_write_is_caught(tmp_path):
    """HIGH-2. Split 1 wrote the marker at its own anchor and completed; split 2
    completed at a NEWER anchor and wrote nothing. The ids match; the note does
    not."""
    _splits(tmp_path, marker_ts=EARLY, entries=_anchored((RUN, EARLY), (RUN, LATE)))

    result = check_c3(tmp_path, "build")

    assert result.ok is False, result.detail
    assert "predates that run's last recorded completion" in result.detail
    assert "re-run its C3 step" in result.detail


def test_the_split_that_did_re_write_the_marker_passes(tmp_path):
    """The same two completions, with the marker refreshed by the second — so
    the marker's anchor EQUALS the latest completion's, which is what a correct
    canon block produces."""
    _splits(tmp_path, marker_ts=LATE, entries=_anchored((RUN, EARLY), (RUN, LATE)))

    result = check_c3(tmp_path, "build")

    assert result.ok is True, result.detail


def test_a_single_stale_completion_is_caught_too(tmp_path):
    """The gate is the ANCHOR's existence, not a count of entries.

    An earlier version required a run to have recorded two completions before it
    would look at the clock. That reasoning does not hold for `iterate`, whose
    ledger is one FILE per run id: F5c rewrites that single entry in place, so
    the count is pinned at one forever and a rewritten completion with a skipped
    F5b passed on a bare id match — the vacuous key this iterate exists to remove.
    """
    _splits(tmp_path, marker_ts=EARLY, entries=_anchored((RUN, LATE)))

    result = check_c3(tmp_path, "build")

    assert result.ok is False, result.detail
    assert "predates that run's last recorded completion" in result.detail


# --- the false positives the rule must not create -------------------------

def test_a_completion_with_no_anchor_never_consults_the_clock(tmp_path):
    """Entries written before `event_at` existed have no value on the marker's
    clock. Comparing their wall clock to a marker is exactly the defect, so the
    run id is allowed to be the whole answer for them."""
    _splits(tmp_path, marker_ts=EARLY, entries=[
        {"run_id": RUN, "at": LATE, "date": LATE[:10]},
    ])

    result = check_c3(tmp_path, "build")

    assert result.ok is True, result.detail


def test_a_rerun_under_a_sticky_id_with_no_new_event_passes(tmp_path):
    """The reproduced regression. `record_event` dedups `phase_completed`
    first-wins, so a re-run appends NO event: the marker is rewritten but
    re-derives the same anchor, and the new completion records that same anchor.
    Equal anchors mean "written by this block", not "you skipped a step"."""
    _splits(tmp_path, marker_ts=EARLY, entries=_anchored((RUN, EARLY), (RUN, EARLY)))

    result = check_c3(tmp_path, "build")

    assert result.ok is True, result.detail


def test_the_wall_clock_at_is_never_what_gets_compared(tmp_path):
    """Directly pins the defect's mechanism: every `at` here is LATER than the
    marker, and every `event_at` equals it. Reading `at` warns; reading
    `event_at` passes."""
    entries = _anchored((RUN, EARLY), (RUN, EARLY))
    assert all(e["at"] > e["event_at"] for e in entries), "fixture must model the skew"
    _splits(tmp_path, marker_ts=EARLY, entries=entries)

    assert check_c3(tmp_path, "build").ok is True


# --- what it cannot settle, it says -----------------------------------------

def test_a_day_precision_legacy_entry_is_not_compared_to_the_marker(tmp_path):
    """A bare `date` is a wall clock AND day-precision. Neither is comparable
    with the marker, so the id answers alone rather than a guess being made."""
    _splits(tmp_path, marker_ts=EARLY, entries=[
        {"run_id": RUN, "date": EARLY[:10]},
        {"run_id": RUN, "date": EARLY[:10]},
    ])

    assert check_c3(tmp_path, "build").ok is True


def test_an_anchor_that_is_present_but_unreadable_is_stated(tmp_path):
    """Absent and unreadable are DIFFERENT states. No `event_at` is a pre-change
    entry, where the run id is legitimately the whole answer. An `event_at` that
    is there and will not parse is a malformed record — taking the run-id
    fallback there would disable the stale-note check on exactly the input least
    deserving of the benefit of the doubt."""
    _splits(tmp_path, marker_ts=MID, entries=[
        {"run_id": RUN, "event_at": "2026-07-27T10:00:00+00:00"},
        {"run_id": RUN, "event_at": "nonsense", "at": LATE},
    ])

    result = check_c3(tmp_path, "build")

    assert result.ok is False, result.detail
    assert "cannot be read" in result.detail


def test_a_marker_pinning_only_a_day_cannot_settle_it_either(tmp_path):
    """The note's own timestamp gets the same treatment as a completion's: a bare
    date pins a DAY, and reading it as midnight is the fabrication HIGH-1 removed
    everywhere else. The marker was the one place it would have survived."""
    _splits(tmp_path, marker_ts=EARLY[:10], entries=_anchored((RUN, EARLY)))

    result = check_c3(tmp_path, "build")

    assert result.ok is False, result.detail
    assert "no usable timestamp" in result.detail


@pytest.mark.parametrize("marker_ts", ["", "not-a-date", "(no events)"])
def test_an_unusable_marker_timestamp_is_stated_when_the_completion_is_anchored(
    tmp_path, marker_ts
):
    """`(no events)` is real: `marker_timestamp` writes it on a project with an
    empty event log. Once the completion carries an anchor the marker's own time
    is needed, and an absent one must not fall back to the bare id match."""
    _splits(tmp_path, marker_ts=marker_ts, entries=_anchored((RUN, EARLY), (RUN, LATE)))

    result = check_c3(tmp_path, "build")

    assert result.ok is False
    assert "no usable timestamp" in result.detail
