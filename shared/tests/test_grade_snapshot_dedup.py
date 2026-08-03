"""Producer-side dedup for ``grade_snapshot`` (iterate-2026-08-01-grade-snapshot-dedup).

The emitter used to append one snapshot per compliance regen unconditionally, on
the documented premise that "a regen is an explicit act". Measurement falsified
it: 234 of 695 events in this repo's log were grade snapshots, and 2026-07-27
alone produced 47 identical ``('F', 49.0)`` records from 20 different sessions.

These tests pin the replacement contract, whose whole subtlety is *what may be
compared with what*:

* the comparator is the most recent preceding snapshot **of the same lineage
  class**, so an alternating ``main``/``branch`` sequence still dedups;
* sameness of tree must be ESTABLISHED — a lineage outside ``{main, branch}``
  (absent, null, ``""``, ``"unknown"``, ``"MAIN"``) is never comparable, and two
  equally-unresolvable records are not thereby equal;
* the comparison NEVER raises, because it runs while holding the append lock and
  reads durable, union-merged, amendable data. A raise there costs the emitter
  its event (``update_compliance`` swallows emitter failures), which is strictly
  worse than the duplicate this change removes;
* dedup is OPT-IN, so the manual/replay ``record_event.py`` CLI is unaffected.

The third bullet — "never raises" — has its own module,
``test_grade_snapshot_dedup_never_raises.py``: it is a large parametrized
cluster in its own right, and splitting it keeps both files under the 300-line
guideline rather than incurring a new crossing inside a change whose own
rationale was to avoid ratcheting one (Stage-3 doubt review).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
# The fixtures module is a sibling, not a package member — same convention as
# test_grade_snapshot_event.py / _tree_lineage_fixtures.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _grade_snapshot_dedup_fixtures import _append, _snap, _snaps, _write  # noqa: E402
from tools.record_event import append_event_idempotent, last_grade_snapshot  # noqa: E402


class TestTheDedupItself:
    def test_an_unchanged_grade_is_suppressed(self, tmp_path):
        _write(tmp_path, _snap())
        event_id, skip = _append(tmp_path, _snap())
        assert event_id is None
        assert skip == {"reason": "unchanged_grade", "grade": "B", "score": 88.0}
        assert len(_snaps(tmp_path)) == 1

    @pytest.mark.parametrize("grade,score", [("A", 88.0), ("B", 89.0), ("A", 94.7)])
    def test_a_changed_grade_or_score_appends(self, tmp_path, grade, score):
        _write(tmp_path, _snap())
        event_id, skip = _append(tmp_path, _snap(grade=grade, score=score))
        assert skip is None and event_id is not None
        assert len(_snaps(tmp_path)) == 2

    def test_an_int_and_a_float_score_are_the_same_score(self, tmp_path):
        # json.loads gives int for `95`, float for `95.0`. The wire carries both.
        _write(tmp_path, _snap(score=95))
        _, skip = _append(tmp_path, _snap(score=95.0))
        assert skip == {"reason": "unchanged_grade", "grade": "B", "score": 95.0}

    def test_the_first_snapshot_in_an_empty_log_appends(self, tmp_path):
        event_id, skip = _append(tmp_path, _snap())
        assert skip is None and event_id is not None


class TestWhatMayBeComparedWithWhat:
    """The heart of the contract: sameness of tree is established, never assumed."""

    def test_the_same_value_from_a_different_lineage_class_appends(self, tmp_path):
        _write(tmp_path, _snap(lineage="branch"))
        _, skip = _append(tmp_path, _snap(lineage="main"))
        assert skip is None, "a branch point must never suppress a main point"

    def test_alternating_lineage_classes_still_dedup(self, tmp_path):
        # The comparator scans back for the most recent snapshot OF THIS CLASS.
        # Comparing against the absolute-last snapshot instead would dedup
        # nothing here, because every record's neighbour is the other class.
        _write(tmp_path, _snap(lineage="main"), _snap(lineage="branch"))
        _, skip = _append(tmp_path, _snap(lineage="main"))
        assert skip is not None, "an interleaved branch point must not shield main"

    def test_a_real_transition_is_never_swallowed(self, tmp_path):
        _write(tmp_path, _snap(grade="F", score=49.0), _snap(grade="B", score=88.0))
        _, skip = _append(tmp_path, _snap(grade="F", score=49.0))
        assert skip is None, "F -> B -> F is three points, not one"

    def test_an_amended_predecessor_preserves_the_effective_transition(self, tmp_path):
        predecessor = _snap()
        amendment = {
            "v": 1, "id": "evt-amend-grade", "ts": "2026-08-01T00:00:01+00:00",
            "type": "event_amended", "amends": predecessor["id"],
            "fields": {"grade": "A", "score": 90.0},
        }
        _write(tmp_path, predecessor, amendment)

        event_id, skip = _append(tmp_path, _snap())

        assert event_id is not None and skip is None, "effective A/90 -> B/88 must append"
        assert len(_snaps(tmp_path)) == 2

    def test_intervening_events_of_other_types_do_not_defeat_dedup(self, tmp_path):
        _write(
            tmp_path, _snap(),
            {"v": 1, "id": "evt-w1", "ts": "2026-08-01T00:00:01+00:00",
             "type": "work_completed", "commit": "abc"},
        )
        _, skip = _append(tmp_path, _snap())
        assert skip is not None, "the comparator is the last SNAPSHOT, not the last line"

    @pytest.mark.parametrize(
        "lineage", [..., None, "", "unknown", "MAIN", "Branch", "trunk", 7, ["main"]],
        ids=["absent", "null", "empty", "unknown", "wrongcase", "wrongcase2",
             "unknown-word", "int", "list"],
    )
    def test_an_unresolvable_lineage_is_never_comparable(self, tmp_path, lineage):
        # Both sides carry the SAME unresolvable value — which still does not
        # establish that they are the same tree.
        _write(tmp_path, _snap(lineage=lineage))
        _, skip = _append(tmp_path, _snap(lineage=lineage))
        assert skip is None, f"lineage={lineage!r} must not establish sameness"


class TestDedupIsOptIn:
    def test_the_replay_route_still_appends_an_identical_snapshot(self, tmp_path):
        # record_event.py --type grade_snapshot is the documented manual/replay
        # CLI. "A regen is an explicit act" is false for an automatic regen and
        # TRUE for a hand-run replay, so the flag defaults off.
        _write(tmp_path, _snap())
        event_id, skip = append_event_idempotent(tmp_path, _snap())
        assert skip is None and event_id is not None
        assert len(_snaps(tmp_path)) == 2

    def test_the_flag_does_not_apply_grade_semantics_to_other_types(self, tmp_path):
        other = {"v": 1, "id": "evt-o1", "ts": "2026-08-01T00:00:00+00:00",
                 "type": "hook_warning", "grade": "B", "score": 88.0,
                 "lineage": "branch"}
        _write(tmp_path, other)
        _, skip = _append(tmp_path, dict(other, id="evt-o2"))
        assert skip is None, "the branch is gated on type == grade_snapshot"

    def test_other_dedup_branches_are_unaffected(self, tmp_path):
        phase = {"v": 1, "id": "evt-p1", "ts": "2026-08-01T00:00:00+00:00",
                 "type": "phase_completed", "phase": "build"}
        _write(tmp_path, phase)
        _, skip = _append(tmp_path, dict(phase, id="evt-p2"))
        assert skip == {"reason": "duplicate_phase", "phase": "build"}

    def test_record_event_reader_monkeypatch_seam_is_preserved(self, tmp_path, monkeypatch):
        import tools.record_event as record_event

        events = [
            {"type": "work_completed", "commit": "abc", "section": "s1"},
            {"type": "phase_completed", "phase": "build", "splitId": "p1"},
        ]
        monkeypatch.setattr(record_event, "read_events", lambda _root: events)

        assert record_event.has_commit(tmp_path, "abc", section="s1") is True
        assert record_event.has_phase_event(tmp_path, "build", "p1") is True


class TestTheScanIsBoundToTheFileTheLockProtects:
    def test_the_dedup_scan_and_the_append_share_one_lock(self, tmp_path, monkeypatch):
        """Deterministic proof the grade scan sits AFTER lock acquisition.

        Clones the ``_InjectingLock`` pattern that pins the same invariant for
        ``phase_completed`` (``test_record_event_lifecycle_integrity``): a
        competing snapshot is written the instant the lock is entered, so a scan
        positioned inside the ``with _FileLock(...)`` body observes it and skips,
        while a scan positioned before the lock would miss it and double-append.
        That ordering is the deep-audit F14 lesson; this test is what stops the
        new branch from quietly regressing it.
        """
        import tools.record_event as record_event
        from lib.events_log import resolve_events_path

        events_path = resolve_events_path(tmp_path)
        injected = json.dumps(_snap()) + "\n"
        real_lock = record_event._FileLock

        class _InjectingLock(real_lock):
            def __enter__(self):
                ctx = super().__enter__()
                with open(events_path, "a", encoding="utf-8") as fp:
                    fp.write(injected)
                return ctx

        monkeypatch.setattr(record_event, "_FileLock", _InjectingLock)

        event_id, skip = _append(tmp_path, _snap())
        assert event_id is None, "the scan must observe the in-lock injection"
        assert skip == {"reason": "unchanged_grade", "grade": "B", "score": 88.0}
        assert len(_snaps(tmp_path)) == 1, "our duplicate must not have landed"

    def test_last_grade_snapshot_reads_the_events_it_is_given(self):
        # AC4's invariant is encoded in the signature: the helper takes the
        # already-parsed events read INSIDE the lock, not a project root it
        # would re-resolve and re-read outside it.
        events = [
            _snap(grade="A", score=90.0, lineage="main"),
            _snap(grade="B", score=88.0, lineage="branch"),
            _snap(grade="C", score=70.0, lineage="main"),
        ]
        assert last_grade_snapshot(events, "main")["grade"] == "C"
        assert last_grade_snapshot(events, "branch")["grade"] == "B"
        assert last_grade_snapshot(events, "unknown") is None
        assert last_grade_snapshot([], "main") is None


class TestTheKnownLimit:
    def test_a_stale_tree_still_appends_a_value_recorded_elsewhere(self, tmp_path):
        """AC4's residual, pinned so it reads as a known limit, not an assumption.

        ``resolve_events_path`` is a literal per-tree join: two worktrees are two
        files and two locks. A tree whose log predates a snapshot merged
        elsewhere cannot see it and will append its own copy. Deduplicating
        across trees would need one authoritative log and a shared lock; out of
        scope, and stated rather than quietly implied.
        """
        merged, stale = tmp_path / "merged", tmp_path / "stale"
        merged.mkdir(), stale.mkdir()
        _write(merged, _snap())
        _write(stale)  # same repo, older checkout: the snapshot is not here yet

        _, skip = _append(stale, _snap())
        assert skip is None, "a stale tree has nothing to compare against"
        assert len(_snaps(stale)) == 1
