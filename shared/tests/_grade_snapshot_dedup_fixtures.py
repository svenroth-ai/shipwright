"""Shared helpers for the ``grade_snapshot`` dedup tests.

Underscore-prefixed so pytest does not collect it, matching the sibling
``_tree_lineage_fixtures.py`` convention. Imported by
``test_grade_snapshot_dedup.py`` and ``test_grade_snapshot_dedup_never_raises.py``,
which were split so neither crosses the 300-line guideline.
"""

from __future__ import annotations

import itertools
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from tools.record_event import append_event_idempotent  # noqa: E402

SNAP = "grade_snapshot"

#: Event ids only need to be distinct, and a counter keeps them so without
#: hashing the payload — some tests deliberately pass unhashable values.
_ids = itertools.count(1)


def _snap(grade="B", score=88.0, lineage="branch", **extra) -> dict:
    """A grade_snapshot. Pass ``lineage=...`` (Ellipsis) to omit the key entirely."""
    event = {
        "v": 1, "id": f"evt-{next(_ids):08d}",
        "ts": "2026-08-01T00:00:00+00:00", "type": SNAP, "grade": grade, "score": score,
    }
    if lineage is not ...:
        event["lineage"] = lineage
    event.update(extra)
    return event


def _write(root: Path, *events: dict) -> None:
    (root / "shipwright_events.jsonl").write_text(
        "".join(json.dumps(e) + "\n" for e in events), encoding="utf-8",
    )


def _snaps(root: Path) -> list[dict]:
    path = root / "shipwright_events.jsonl"
    if not path.exists():
        return []
    # One parse per line, and skips anything unparseable, so a test that
    # deliberately corrupts the log can still use the suite's own reader.
    out = []
    for ln in path.read_text(encoding="utf-8").splitlines():
        if not ln.strip():
            continue
        try:
            event = json.loads(ln)
        except ValueError:
            continue
        if event.get("type") == SNAP:
            out.append(event)
    return out


def _append(root: Path, event: dict):
    """Append with the dedup rule ENABLED — the compliance emitter's route."""
    return append_event_idempotent(root, event, deduplicate_grade_snapshot=True)
