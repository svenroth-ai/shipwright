"""Tests for context_cost_statusline.py — Claude Code statusLine.command contract.

Not auto-registered by anything in this repo (a plugin cannot write a user's
personal ~/.claude/settings.json, the same constraint as the readiness
check's autoCompactWindow report) — an operator points their own
statusLine.command at this script. These tests exercise the script directly.
"""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

import scripts.tools.context_cost_statusline as mod


def _session_path(project_root: Path, session_id: str) -> Path:
    return project_root / ".shipwright" / "compliance" / "context-cost" / f"{session_id}.json"


def _mark_as_project(project_root: Path) -> None:
    project_root.mkdir(parents=True, exist_ok=True)
    (project_root / "shipwright_run_config.json").write_text("{}", encoding="utf-8")


def test_prints_calls_and_cost_when_data_exists(tmp_path, capsys, monkeypatch):
    _mark_as_project(tmp_path)
    monkeypatch.setenv("SHIPWRIGHT_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setenv("SHIPWRIGHT_SESSION_ID", "sess-1")
    summary = {"calls": 5, "context_tokens": 500, "cost_usd": 1.2345,
               "unpriced_calls": 0, "cost_complete": True, "by_phase": {}}
    path = _session_path(tmp_path, "sess-1")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary), encoding="utf-8")

    payload = {"session_id": "sess-1", "workspace": {"current_dir": str(tmp_path)}}
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))

    rc = mod.main()

    assert rc == 0
    out = capsys.readouterr().out.strip()
    assert "5" in out
    assert "1.23" in out


def test_incomplete_cost_is_marked_with_a_plus(tmp_path, capsys, monkeypatch):
    _mark_as_project(tmp_path)
    monkeypatch.setenv("SHIPWRIGHT_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setenv("SHIPWRIGHT_SESSION_ID", "sess-1")
    summary = {"calls": 2, "context_tokens": 200, "cost_usd": 0.50,
               "unpriced_calls": 1, "cost_complete": False, "by_phase": {}}
    path = _session_path(tmp_path, "sess-1")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary), encoding="utf-8")

    payload = {"session_id": "sess-1", "workspace": {"current_dir": str(tmp_path)}}
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))

    rc = mod.main()

    assert rc == 0
    out = capsys.readouterr().out.strip()
    assert "+" in out


def test_missing_data_prints_a_placeholder_not_a_crash(tmp_path, capsys, monkeypatch):
    _mark_as_project(tmp_path)
    monkeypatch.setenv("SHIPWRIGHT_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setenv("SHIPWRIGHT_SESSION_ID", "sess-never-stopped")
    payload = {"session_id": "sess-never-stopped", "workspace": {"current_dir": str(tmp_path)}}
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))

    rc = mod.main()

    assert rc == 0
    out = capsys.readouterr().out.strip()
    assert out  # never empty — always renders something


def test_malformed_stdin_never_crashes(tmp_path, monkeypatch, capsys):
    _mark_as_project(tmp_path)
    monkeypatch.setenv("SHIPWRIGHT_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setattr(sys, "stdin", io.StringIO("not json"))

    rc = mod.main()

    assert rc == 0


def test_reader_prefers_payload_session_id_over_env(tmp_path, capsys, monkeypatch):
    """Same process class as the Stop hook's own parity test: a subprocess
    Claude Code spawns directly for statusLine.command does not reliably
    inherit SHIPWRIGHT_SESSION_ID (see context_cost_core.resolve_session_id's
    docstring) — the payload is the reliable channel here, so it must win,
    matching track_context_cost.py's writer-side precedence exactly."""
    _mark_as_project(tmp_path)
    monkeypatch.setenv("SHIPWRIGHT_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setenv("SHIPWRIGHT_SESSION_ID", "env-var-says-this-one")
    summary = {"calls": 7, "context_tokens": 70, "cost_usd": 0.07,
               "unpriced_calls": 0, "cost_complete": True, "by_phase": {}}
    _session_path(tmp_path, "payload-says-this-one").parent.mkdir(parents=True, exist_ok=True)
    _session_path(tmp_path, "payload-says-this-one").write_text(
        json.dumps(summary), encoding="utf-8"
    )

    payload = {"session_id": "payload-says-this-one", "workspace": {"current_dir": str(tmp_path)}}
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))

    rc = mod.main()

    assert rc == 0
    out = capsys.readouterr().out.strip()
    assert "7" in out
    assert "no data yet" not in out


def test_reader_falls_back_to_env_when_payload_has_no_session_id(tmp_path, capsys, monkeypatch):
    _mark_as_project(tmp_path)
    monkeypatch.setenv("SHIPWRIGHT_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setenv("SHIPWRIGHT_SESSION_ID", "env-var-says-this-one")
    summary = {"calls": 3, "context_tokens": 30, "cost_usd": 0.03,
               "unpriced_calls": 0, "cost_complete": True, "by_phase": {}}
    _session_path(tmp_path, "env-var-says-this-one").parent.mkdir(parents=True, exist_ok=True)
    _session_path(tmp_path, "env-var-says-this-one").write_text(
        json.dumps(summary), encoding="utf-8"
    )

    payload = {"workspace": {"current_dir": str(tmp_path)}}
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))

    rc = mod.main()

    assert rc == 0
    out = capsys.readouterr().out.strip()
    assert "3" in out
    assert "no data yet" not in out
