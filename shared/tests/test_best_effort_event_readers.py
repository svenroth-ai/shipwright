"""Best-effort event readers must skip pathological JSON lines, not crash."""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(_SCRIPTS))

from lib import campaign_status, context_cost_core, iterate_phase_groups, iterate_timings


def _deep_line() -> str:
    return "[" * 10_000 + "]" * 10_000


def test_campaign_status_skips_deeply_nested_event_line():
    projected, warnings = campaign_status._project_events([_deep_line()], "campaign")
    assert projected == {} and warnings == ["1 corrupt/unparseable event line(s) skipped"]


def test_phase_groups_skips_deeply_nested_mark(tmp_path):
    run_id = "iterate-2026-08-08-reader-guard"
    path = iterate_phase_groups.sidecar_path(tmp_path, run_id)
    path.parent.mkdir(parents=True)
    path.write_text(_deep_line() + "\n", encoding="utf-8")
    assert iterate_phase_groups.read_marks(tmp_path, run_id) == []


def test_iterate_timings_skips_deeply_nested_record(tmp_path):
    path = tmp_path / "events.jsonl"
    path.write_text(_deep_line() + "\n", encoding="utf-8")
    assert iterate_timings._tolerant_read_lines(path) == []


def test_context_cost_skips_deeply_nested_transcript_record(tmp_path):
    path = tmp_path / "transcript.jsonl"
    path.write_text(_deep_line() + "\n", encoding="utf-8")
    assert list(context_cost_core._iter_transcript_records(path)) == []
