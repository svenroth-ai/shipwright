"""record_event ``grade_snapshot`` support (M-Pre-3,
iterate-2026-07-10-grade-snapshot-events).

Lives in a NEW file because the two existing ``test_record_event.py`` modules
are baseline-capped (anti-ratchet would block appending to them — same reason
``test_record_event_lifecycle_integrity.py`` was created).

``grade_snapshot`` is the M-Pre-3 event the compliance dashboard appends once
per Control-Grade regen so the WebUI Ship's-Log can trend the grade. These
tests pin the producer side: the type is an accepted ``--type`` choice, its
``build_event`` branch serialises ``grade``/``score``/optional ``commit``, and
the event round-trips through ``append_event`` → ``read_events``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_TOOLS = Path(__file__).resolve().parents[1] / "scripts" / "tools"
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

from record_event import (  # noqa: E402
    append_event,
    build_event,
    main,
    parse_args,
    read_events,
)


class TestGradeSnapshotTypeAccepted:
    """The closed ``--type`` registry accepts grade_snapshot (drift protection)."""

    def test_cli_accepts_and_lands(self, tmp_path, capsys):
        rc = main([
            "--project-root", str(tmp_path),
            "--type", "grade_snapshot",
            "--grade", "A",
            "--score", "95.5",
        ])
        assert rc == 0
        out = json.loads(capsys.readouterr().out)
        assert out["success"] is True
        assert out["type"] == "grade_snapshot"

        events = read_events(tmp_path)
        assert len(events) == 1
        event = events[0]
        assert event["type"] == "grade_snapshot"
        assert event["grade"] == "A"
        assert event["score"] == 95.5
        assert event["ts"]  # generic timestamp populated
        assert event["id"].startswith("evt-")
        # No --commit supplied → the optional key is omitted (clean wire shape).
        assert "commit" not in event


class TestGradeSnapshotBuildEvent:
    def test_shape_with_commit(self):
        args = parse_args([
            "--project-root", ".",
            "--type", "grade_snapshot",
            "--grade", "B",
            "--score", "82",
            "--commit", "deadbeef",
        ])
        event = build_event(args)
        assert event["type"] == "grade_snapshot"
        assert event["grade"] == "B"
        assert event["score"] == 82.0  # --score is a float
        assert event["commit"] == "deadbeef"

    def test_score_is_float(self):
        args = parse_args([
            "--project-root", ".",
            "--type", "grade_snapshot",
            "--grade", "D", "--score", "63",
        ])
        event = build_event(args)
        assert isinstance(event["score"], float)


class TestGradeSnapshotRoundTrip:
    """Producer → shipwright_events.jsonl → reader round-trip (io boundary)."""

    def test_append_then_read(self, tmp_path):
        args = parse_args([
            "--project-root", str(tmp_path),
            "--type", "grade_snapshot",
            "--grade", "C", "--score", "71.0",
        ])
        event = build_event(args)
        returned = append_event(tmp_path, event)
        assert returned == event["id"]

        back = read_events(tmp_path)
        assert [e["id"] for e in back] == [event["id"]]
        assert back[0]["type"] == "grade_snapshot"
        assert back[0]["grade"] == "C"
        assert back[0]["score"] == 71.0
