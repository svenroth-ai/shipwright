"""append_event_idempotent's deduplicate_by_commit branch is type-scoped.

Split out of ``test_record_event.py`` rather than added there (bloat baseline
anti-ratchet, 883 LOC) — a fresh, coherent, single-purpose file rather than
growing an already-large one.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from scripts.tools.record_event import append_event, append_event_idempotent, read_events


@pytest.fixture
def project(tmp_path):
    return tmp_path


class TestByCommitDedupIsTypeScoped:
    def test_by_commit_dedup_is_scoped_to_work_completed(self, project):
        """A grade_snapshot sharing a work_completed's commit is not its duplicate.

        Root cause: the deduplicate_by_commit branch gated on
        `event.get("commit")` being present, not on `event.get("type") ==
        "work_completed"` — so any other event type carrying a commit field
        (grade_snapshot, since #537 added --commit to that build_event branch)
        collided with an unrelated work_completed record sharing the same sha.
        """
        append_event(project, {
            "v": 1, "id": "evt-wc00001", "ts": "T",
            "type": "work_completed", "source": "iterate", "commit": "abc123",
        })
        event_id, skip = append_event_idempotent(
            project,
            {"v": 1, "id": "evt-gs00001", "ts": "T", "type": "grade_snapshot",
             "grade": "B", "score": 88.0, "commit": "abc123"},
            deduplicate_by_commit=True,
        )
        assert skip is None, (
            "the by-commit rule must not treat a grade_snapshot as a "
            "duplicate of an unrelated work_completed event"
        )
        assert event_id is not None
        assert len(read_events(project)) == 2
