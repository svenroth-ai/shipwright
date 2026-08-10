"""Unit coverage for the phase-scoped test-evidence provenance contract."""

from __future__ import annotations

import json
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from test_evidence_phase_source import (  # noqa: E402
    PhaseRunSource,
    latest_phase_source,
    parse_phase_source,
    stamp_phase_source,
)


def _event(run_id: str | None, ts: str) -> dict:
    detail = {"runId": run_id} if run_id is not None else {}
    return {
        "type": "phase_started",
        "phase": "test",
        "ts": ts,
        "detail": json.dumps(detail),
    }


def test_latest_phase_source_uses_latest_matching_phase_event():
    source = latest_phase_source([
        _event("test-run-old", "2026-08-10T08:00:00Z"),
        _event("test-run-current", "2026-08-10T09:00:00Z"),
    ], "test")
    assert source == PhaseRunSource("test", "test-run-current")


def test_latest_malformed_event_does_not_fall_back_to_old_identity():
    assert latest_phase_source([
        _event("test-run-old", "2026-08-10T08:00:00Z"),
        _event(None, "2026-08-10T09:00:00Z"),
    ], "test") is None


def test_equal_timestamp_later_legacy_event_does_not_fall_back():
    assert latest_phase_source([
        _event("test-run-old", "2026-08-10T09:00:00Z"),
        _event(None, "2026-08-10T09:00:00Z"),
    ], "test") is None


def test_stamp_is_parseable_and_replaces_an_old_marker(tmp_path: Path):
    path = tmp_path / "test-evidence.md"
    path.write_text(
        "# Evidence\nGenerated: now\nSource-State: run=all-work\n"
        "Test-Evidence-Phase: phase=test run=old\n\nbody\n",
        encoding="utf-8",
    )
    expected = PhaseRunSource("test", "test-run-current")
    stamp_phase_source(path, expected)
    text = path.read_text(encoding="utf-8")
    assert text.count("Test-Evidence-Phase:") == 1
    assert parse_phase_source(text) == expected


def test_stamp_preserves_identity_markers_for_other_phases(tmp_path: Path):
    path = tmp_path / "test-evidence.md"
    path.write_text("# Evidence\nGenerated: now\n\nbody\n", encoding="utf-8")
    build = PhaseRunSource("build", "build-run-current")
    test = PhaseRunSource("test", "test-run-current")
    stamp_phase_source(path, build)
    stamp_phase_source(path, test)
    text = path.read_text(encoding="utf-8")
    assert parse_phase_source(text, "build") == build
    assert parse_phase_source(text, "test") == test
