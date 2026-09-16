"""Tests for context_cost_summary.py `show` — reads the per-session cost file
written by the Stop hook and prints it; no aggregation logic of its own."""

from __future__ import annotations

import contextlib
import io
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

import scripts.tools.context_cost_summary as mod
from scripts.hooks import track_context_cost  # noqa: E402
from scripts.lib import iterate_phase_groups as ipg  # noqa: E402
from scripts.lib import worktree_isolation  # noqa: E402


def _session_path(project_root: Path, session_id: str) -> Path:
    return project_root / ".shipwright" / "compliance" / "context-cost" / f"{session_id}.json"


@pytest.mark.covers("FR-01.20/AC04")
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


@pytest.mark.covers("FR-01.20/AC04")
def test_show_breaks_the_running_total_down_by_phase_on_demand(tmp_path, capsys):
    """FR-01.20/AC04, second clause — "given the same running session, when
    its per-phase breakdown is asked for directly, then it is shown broken
    down by phase on demand, without waiting for the session to end." The
    session is not stopped (no work_completed event, no F5b fold) — `show`
    is invoked directly against the live per-session file the Stop hook
    keeps current, and the phase buckets it wrote are what comes back."""
    summary = {
        "calls": 7, "context_tokens": 700, "cost_usd": 0.42,
        "unpriced_calls": 0, "cost_complete": True,
        "by_phase": {
            "scope": {"calls": 2, "cost_usd": 0.10},
            "build": {"calls": 5, "cost_usd": 0.32},
        },
    }
    path = _session_path(tmp_path, "sess-running")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary), encoding="utf-8")

    rc = mod.main(["show", "--project-root", str(tmp_path), "--session-id", "sess-running"])

    assert rc == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["by_phase"]["scope"]["calls"] == 2
    assert printed["by_phase"]["build"]["calls"] == 5


@pytest.mark.covers("FR-01.20/AC04")
def test_the_real_hook_writes_phase_buckets_show_then_actually_prints(tmp_path, monkeypatch):
    """End-to-end version of the test above (external code review, glm,
    medium: the prior test only proves `show` echoes a HAND-AUTHORED dict —
    it does not prove the live per-session file the real Stop hook writes
    ever contains `by_phase` in the first place). This one drives the real
    pipeline: a run pointer + phase marks + a transcript with calls before
    and after a mark, through the ACTUAL `track_context_cost.py` Stop hook
    (the same one that runs in production), then reads the resulting
    ON-DISK file back through `show` — no dict is authored by the test."""
    run_id = "iterate-2026-08-07-context-cost-meter"
    session_id = "sess-e2e"
    t0 = datetime(2026, 8, 7, 12, 0, 0, tzinfo=timezone.utc)

    # A live run pointer is what makes the hook resolve a real run_id instead
    # of None (which would collapse everything into "unphased" and prove
    # nothing about phase attribution surviving to the printed output).
    worktree_isolation.write_run_pointer(
        tmp_path, run_id=run_id, slug="context-cost-e2e", branch="iterate/e2e",
        worktree_path=tmp_path, session_id=session_id,
    )
    ipg.append_mark(tmp_path, run_id, "scope", ts=(t0).isoformat())
    ipg.append_mark(tmp_path, run_id, "build", ts=(t0 + timedelta(minutes=5)).isoformat())

    transcript = tmp_path / "transcript.jsonl"
    records = [
        {"type": "assistant", "requestId": "req-scope", "timestamp": t0.isoformat(),
         "message": {"model": "claude-sonnet-5", "usage": {"input_tokens": 100}}},
        {"type": "assistant", "requestId": "req-build",
         "timestamp": (t0 + timedelta(minutes=6)).isoformat(),
         "message": {"model": "claude-sonnet-5", "usage": {"input_tokens": 200}}},
    ]
    transcript.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")

    payload = {"session_id": session_id, "transcript_path": str(transcript)}
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
    monkeypatch.setenv("SHIPWRIGHT_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setenv("SHIPWRIGHT_SESSION_ID", session_id)
    (tmp_path / "shipwright_run_config.json").write_text("{}", encoding="utf-8")

    hook_rc = track_context_cost.main()
    assert hook_rc == 0

    on_disk = json.loads(_session_path(tmp_path, session_id).read_text(encoding="utf-8"))
    assert set(on_disk["by_phase"]) == {"scope", "build"}

    def _run_show():
        return mod.main(["show", "--project-root", str(tmp_path), "--session-id", session_id])

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        show_rc = _run_show()
    assert show_rc == 0
    printed = json.loads(buf.getvalue())
    assert printed["by_phase"]["scope"]["calls"] == 1
    assert printed["by_phase"]["build"]["calls"] == 1


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
