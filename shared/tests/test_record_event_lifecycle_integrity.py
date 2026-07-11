"""record_event lifecycle-integrity tests (deep-audit F14 + F15).

Lives in a NEW file because the two existing ``test_record_event.py`` modules
are baseline-capped (anti-ratchet would block appending to them).

F15 — ``phase_failed`` / ``stale_stop_rejected`` are accepted ``--type`` choices
       and land in the log (the Stop hook emitted them; argparse used to reject
       them → exit 2 → the failure events were silently lost).
F14 — the dedup scan and the append share ONE ``_FileLock`` critical section, so
       a writer that wins the lock sees a prior append and skips (no duplicate
       ``phase_completed`` under concurrency).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_TOOLS = Path(__file__).resolve().parents[1] / "scripts" / "tools"
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

import record_event  # noqa: E402


def _events(project_root: Path) -> list[dict]:
    return record_event.read_events(project_root)


# ---------------------------------------------------------------------------
# F15 — failure event types are first-class and land
# ---------------------------------------------------------------------------

class TestFailureEventTypesAccepted:
    def test_phase_failed_accepted_and_lands(self, tmp_path, capsys):
        rc = record_event.main([
            "--project-root", str(tmp_path),
            "--type", "phase_failed",
            "--phase", "build",
            "--detail", json.dumps({"phaseTaskId": "ptk-1", "reason": "boom"}),
        ])
        assert rc == 0
        out = json.loads(capsys.readouterr().out)
        assert out["success"] is True and out["type"] == "phase_failed"
        events = _events(tmp_path)
        assert len(events) == 1
        assert events[0]["type"] == "phase_failed"
        assert events[0]["phase"] == "build"
        assert "boom" in events[0]["detail"]

    def test_stale_stop_rejected_accepted_and_lands(self, tmp_path, capsys):
        rc = record_event.main([
            "--project-root", str(tmp_path),
            "--type", "stale_stop_rejected",
            "--phase", "plan",
            "--detail", json.dumps({"reason": "stale_version"}),
        ])
        assert rc == 0
        events = _events(tmp_path)
        assert len(events) == 1
        assert events[0]["type"] == "stale_stop_rejected"
        assert events[0]["phase"] == "plan"

    def test_failure_types_not_phase_deduped(self, tmp_path):
        # phase_completed is deduped per-phase; the failure types are diagnostics
        # that may legitimately recur, so two phase_failed for one phase both land.
        for _ in range(2):
            record_event.main([
                "--project-root", str(tmp_path),
                "--type", "phase_failed", "--phase", "build",
            ])
        failed = [e for e in _events(tmp_path) if e["type"] == "phase_failed"]
        assert len(failed) == 2


# ---------------------------------------------------------------------------
# F14 — dedup scan + append are atomic (one lock)
# ---------------------------------------------------------------------------

def _phase_completed(phase: str, eid: str) -> dict:
    return {"v": 1, "id": eid, "ts": "T", "type": "phase_completed", "phase": phase}


class TestIdempotentAppend:
    def test_appends_new_event(self, tmp_path):
        eid, skipped = record_event.append_event_idempotent(
            tmp_path, _phase_completed("build", "evt-aaaa1111"),
        )
        assert skipped is None and eid == "evt-aaaa1111"
        assert len(_events(tmp_path)) == 1

    def test_skips_duplicate_phase(self, tmp_path):
        record_event.append_event(tmp_path, _phase_completed("build", "evt-first001"))
        eid, skipped = record_event.append_event_idempotent(
            tmp_path, _phase_completed("build", "evt-second02"),
        )
        assert eid is None
        assert skipped == {"reason": "duplicate_phase", "phase": "build"}
        # Only the first event remains — the duplicate was NOT written.
        assert len(_events(tmp_path)) == 1

    def test_different_split_ids_not_deduped(self, tmp_path):
        """AC1 — same phase, different splitId: both ends persist (per-split facts)."""
        e1 = {**_phase_completed("build", "evt-split0001"), "splitId": "01"}
        e2 = {**_phase_completed("build", "evt-split0002"), "splitId": "02"}
        eid1, skip1 = record_event.append_event_idempotent(tmp_path, e1)
        eid2, skip2 = record_event.append_event_idempotent(tmp_path, e2)
        assert skip1 is None and skip2 is None
        assert eid1 == "evt-split0001" and eid2 == "evt-split0002"
        assert len(_events(tmp_path)) == 2

    def test_same_split_id_deduped_with_split_in_skip(self, tmp_path):
        """AC2 — same (phase, splitId): second skipped; skip payload carries splitId."""
        e1 = {**_phase_completed("build", "evt-split0001"), "splitId": "01"}
        e2 = {**_phase_completed("build", "evt-split0002"), "splitId": "01"}
        record_event.append_event(tmp_path, e1)
        eid, skipped = record_event.append_event_idempotent(tmp_path, e2)
        assert eid is None
        assert skipped == {"reason": "duplicate_phase", "phase": "build", "splitId": "01"}
        assert len(_events(tmp_path)) == 1

    def test_split_tagged_and_untagged_are_distinct(self, tmp_path):
        """A split-tagged end and a phase-only (splitId=None) end don't collide."""
        e_split = {**_phase_completed("build", "evt-split0001"), "splitId": "01"}
        e_none = _phase_completed("build", "evt-none00001")  # no splitId
        _, s1 = record_event.append_event_idempotent(tmp_path, e_split)
        _, s2 = record_event.append_event_idempotent(tmp_path, e_none)
        assert s1 is None and s2 is None
        assert len(_events(tmp_path)) == 2

    def test_skips_duplicate_commit_when_flag_set(self, tmp_path):
        record_event.append_event(tmp_path, {
            "v": 1, "id": "evt-wc000001", "ts": "T", "type": "work_completed",
            "source": "build", "commit": "abc123",
        })
        eid, skipped = record_event.append_event_idempotent(
            tmp_path,
            {"v": 1, "id": "evt-wc000002", "ts": "T", "type": "work_completed",
             "source": "build", "commit": "abc123"},
            deduplicate_by_commit=True,
        )
        assert eid is None and skipped["reason"] == "duplicate_commit"
        assert len(_events(tmp_path)) == 1

    def test_dedup_scan_runs_inside_the_lock(self, tmp_path, monkeypatch):
        """Deterministic proof the scan is positioned AFTER lock acquisition.

        A competing duplicate is injected the instant the lock is entered. The
        F14 fix scans inside the ``with _FileLock(...)`` body, so it sees the
        injected line and skips. The pre-fix design scanned BEFORE acquiring the
        lock — it would have missed the injection and double-appended.
        """
        from lib.events_log import resolve_events_path

        events_path = resolve_events_path(tmp_path)
        injected = json.dumps(_phase_completed("build", "evt-injected1")) + "\n"

        real_lock = record_event._FileLock

        class _InjectingLock(real_lock):
            def __enter__(self):
                ctx = super().__enter__()
                # Simulate a concurrent writer that won the lock first: its
                # append is on disk by the time our in-lock scan runs.
                with open(events_path, "a", encoding="utf-8") as fp:
                    fp.write(injected)
                return ctx

        monkeypatch.setattr(record_event, "_FileLock", _InjectingLock)

        eid, skipped = record_event.append_event_idempotent(
            tmp_path, _phase_completed("build", "evt-mine00001"),
        )
        assert eid is None, "scan-under-lock must observe the injected duplicate"
        assert skipped == {"reason": "duplicate_phase", "phase": "build"}
        # Exactly the injected event — our duplicate was NOT appended.
        events = _events(tmp_path)
        assert len(events) == 1 and events[0]["id"] == "evt-injected1"
