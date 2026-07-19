"""Event-log record-boundary recovery in the boundary-coverage report (site 8).

Split out of ``test_boundary_coverage_report.py``: that module is at its bloat
baseline, and these cases are a different concern anyway — the report's EVENT-LOG
reader, not its markdown/spec parsing.

``_load_events`` used the pre-fix idiom — a bare per-line ``json.loads`` under an
``except json.JSONDecodeError`` that skips the WHOLE physical line — so two
records sharing one line were BOTH discarded. It also appended without an
``isinstance`` guard, so a bare JSON scalar entered the list as a non-dict and
crashed the first downstream ``.get()``. Found by the Stage-2 code review; the
brief's site enumeration did not include it.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
_BCR_PATH = PLUGIN_ROOT / "scripts" / "tools" / "boundary_coverage_report.py"
_spec = importlib.util.spec_from_file_location("boundary_coverage_report", _BCR_PATH)
bcr = importlib.util.module_from_spec(_spec)
sys.modules["boundary_coverage_report"] = bcr
_spec.loader.exec_module(bcr)  # noqa: E402


def test_load_events_recovers_records_sharing_one_physical_line(tmp_path: Path) -> None:
    """The EIGHTH event-log read site, found by the Stage-2 code review.

    ``_load_events`` used the pre-fix idiom — bare ``json.loads(line)`` under an
    ``except json.JSONDecodeError`` that skips the WHOLE physical line — so two
    records sharing a line were BOTH discarded. It now delegates to the shared
    record-boundary SSoT.
    """
    a = {"id": "evt-a", "type": "work_completed", "description": "first"}
    b = {"id": "evt-b", "type": "work_completed", "description": "second"}
    log = tmp_path / "shipwright_events.jsonl"
    log.write_text(json.dumps(a) + json.dumps(b) + "\n", encoding="utf-8")

    assert [e["id"] for e in bcr._load_events(log)] == ["evt-a", "evt-b"]


def test_load_events_returns_only_json_objects(tmp_path: Path) -> None:
    """A bare scalar previously entered the list as a non-dict and crashed the
    first downstream ``.get()`` — this site had no ``isinstance`` guard."""
    log = tmp_path / "shipwright_events.jsonl"
    log.write_text('5\n{"id": "evt-a"}\n', encoding="utf-8")

    events = bcr._load_events(log)
    assert all(isinstance(e, dict) for e in events)
    assert [e["id"] for e in events] == ["evt-a"]


def test_load_events_missing_log_is_empty(tmp_path: Path) -> None:
    assert bcr._load_events(tmp_path / "nope.jsonl") == []
