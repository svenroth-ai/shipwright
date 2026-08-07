"""Tests for context_cost_summary.py `show` — reads the per-session cost file
written by the Stop hook and prints it; no aggregation logic of its own."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

import scripts.tools.context_cost_summary as mod


def _session_path(project_root: Path, session_id: str) -> Path:
    return project_root / ".shipwright" / "compliance" / "context-cost" / f"{session_id}.json"


def test_show_prints_the_existing_summary(tmp_path, capsys):
    summary = {"calls": 3, "context_tokens": 300, "cost_usd": 0.03,
               "unpriced_calls": 0, "cost_complete": True, "by_phase": {}}
    path = _session_path(tmp_path, "sess-1")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary), encoding="utf-8")

    rc = mod.main(["show", "--project-root", str(tmp_path), "--session-id", "sess-1"])

    assert rc == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["calls"] == 3


def test_show_reports_no_data_gracefully_when_no_stop_has_fired(tmp_path, capsys):
    rc = mod.main(["show", "--project-root", str(tmp_path), "--session-id", "sess-never-stopped"])

    assert rc == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["calls"] == 0
    assert printed.get("no_data") is True


def test_read_summary_treats_a_non_object_json_file_as_no_data(tmp_path):
    # Valid JSON, wrong shape (e.g. truncated write, unrelated file) -- must
    # never raise AttributeError on the .get() calls callers rely on.
    path = _session_path(tmp_path, "sess-list")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("[1, 2, 3]", encoding="utf-8")

    summary = mod.read_summary(tmp_path, "sess-list")

    assert summary.get("no_data") is True


def test_read_and_fold_into_event_survives_a_malformed_summary(tmp_path):
    path = _session_path(tmp_path, "sess-bad")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("not json", encoding="utf-8")
    event = {"type": "work_completed"}

    result = mod.read_and_fold_into_event(event, tmp_path, "sess-bad")

    assert result is event
    assert "context_cost" not in result


def test_session_summary_path_rejects_an_id_containing_a_path_separator(tmp_path):
    # External-review finding: Path(session_id).name alone strips directory
    # components (blocks traversal) but does not stop two distinct ids from
    # collapsing onto the same basename -- "other-session/victim" and
    # "victim" must NOT both resolve to victim.json.
    assert mod.session_summary_path(tmp_path, "other-session/victim") is None
    assert mod.session_summary_path(tmp_path, "../escape") is None


def test_read_summary_treats_an_unsafe_session_id_as_no_data(tmp_path):
    # A legitimate session "victim" already has a file; a crafted id that
    # would collide with it must read back as no-data, never that file's
    # contents.
    victim = _session_path(tmp_path, "victim")
    victim.parent.mkdir(parents=True, exist_ok=True)
    victim.write_text(json.dumps({"calls": 42, "unpriced_calls": 0,
                                   "context_tokens": 0, "cost_usd": 0.0,
                                   "cost_complete": True, "by_phase": {}}),
                       encoding="utf-8")

    summary = mod.read_summary(tmp_path, "other-session/victim")

    assert summary.get("no_data") is True
    assert summary.get("calls") == 0


def test_no_data_default_includes_unpriced_models():
    summary = mod.read_summary(Path("does-not-exist"), "sess-never-stopped")
    assert summary["unpriced_models"] == []
