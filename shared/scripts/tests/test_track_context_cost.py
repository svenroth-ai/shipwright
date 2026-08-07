"""Tests for the track_context_cost.py Stop hook.

Additive registration, full-recompute-and-overwrite (never append), and
never-blocks-shutdown are the three load-bearing properties established by
the two external review rounds on iterate-2026-08-07-context-cost-meter.
"""

from __future__ import annotations

import io
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from hooks import track_context_cost  # noqa: E402

_T0 = datetime(2026, 8, 7, 12, 0, 0, tzinfo=timezone.utc)


def _write_transcript(path: Path) -> None:
    record = {
        "type": "assistant",
        "requestId": "req-1",
        "timestamp": _T0.isoformat(),
        "message": {"model": "claude-sonnet-5", "usage": {"input_tokens": 1000}},
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record) + "\n", encoding="utf-8")


def _run_hook(monkeypatch, project_root: Path, transcript_path: Path, session_id: str) -> int:
    payload = {"session_id": session_id, "transcript_path": str(transcript_path)}
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
    monkeypatch.setenv("SHIPWRIGHT_PROJECT_ROOT", str(project_root))
    monkeypatch.setenv("SHIPWRIGHT_SESSION_ID", session_id)
    monkeypatch.delenv("SHIPWRIGHT_RUN_ID", raising=False)
    (project_root / "shipwright_run_config.json").parent.mkdir(parents=True, exist_ok=True)
    (project_root / "shipwright_run_config.json").write_text("{}", encoding="utf-8")
    return track_context_cost.main()


def _out_path(project_root: Path, session_id: str) -> Path:
    return project_root / ".shipwright" / "compliance" / "context-cost" / f"{session_id}.json"


def test_hook_writes_a_summary_for_the_session(tmp_path, monkeypatch):
    transcript = tmp_path / "transcript.jsonl"
    _write_transcript(transcript)

    rc = _run_hook(monkeypatch, tmp_path, transcript, "sess-1")

    assert rc == 0
    out = _out_path(tmp_path, "sess-1")
    assert out.exists()
    summary = json.loads(out.read_text(encoding="utf-8"))
    assert summary["calls"] == 1


def test_repeated_firing_overwrites_with_identical_result(tmp_path, monkeypatch):
    transcript = tmp_path / "transcript.jsonl"
    _write_transcript(transcript)

    _run_hook(monkeypatch, tmp_path, transcript, "sess-1")
    first = json.loads(_out_path(tmp_path, "sess-1").read_text(encoding="utf-8"))
    _run_hook(monkeypatch, tmp_path, transcript, "sess-1")
    second = json.loads(_out_path(tmp_path, "sess-1").read_text(encoding="utf-8"))

    assert first == second
    assert second["calls"] == 1  # never doubled


def test_missing_transcript_path_is_a_silent_no_op(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({"session_id": "sess-1"})))
    monkeypatch.setenv("SHIPWRIGHT_PROJECT_ROOT", str(tmp_path))
    (tmp_path / "shipwright_run_config.json").write_text("{}", encoding="utf-8")

    rc = track_context_cost.main()

    assert rc == 0
    assert not _out_path(tmp_path, "sess-1").exists()


def test_malformed_stdin_never_blocks_the_hook(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "stdin", io.StringIO("not json"))
    monkeypatch.setenv("SHIPWRIGHT_PROJECT_ROOT", str(tmp_path))

    rc = track_context_cost.main()

    assert rc == 0


def test_broken_transcript_path_never_blocks_the_hook(tmp_path, monkeypatch):
    missing = tmp_path / "does-not-exist.jsonl"
    rc = _run_hook(monkeypatch, tmp_path, missing, "sess-1")
    assert rc == 0
    assert not _out_path(tmp_path, "sess-1").exists()


def test_missing_transcript_on_a_later_firing_preserves_the_prior_summary(tmp_path, monkeypatch):
    # Deepseek external-review finding: a missing transcript is not "zero
    # calls" -- compute_summary would happily return an empty-but-valid
    # summary for it, and writing THAT would silently destroy this
    # session's already-recorded cost data on the very next Stop after a
    # transient path/race issue. The hook must skip the write instead and
    # leave the last durably-recorded summary in place.
    transcript = tmp_path / "transcript.jsonl"
    _write_transcript(transcript)
    _run_hook(monkeypatch, tmp_path, transcript, "sess-1")
    before = json.loads(_out_path(tmp_path, "sess-1").read_text(encoding="utf-8"))
    assert before["calls"] == 1

    transcript.unlink()
    rc = _run_hook(monkeypatch, tmp_path, transcript, "sess-1")

    assert rc == 0
    after = json.loads(_out_path(tmp_path, "sess-1").read_text(encoding="utf-8"))
    assert after == before  # untouched, not overwritten with a zero-call summary


def test_session_id_containing_a_path_separator_skips_the_write(tmp_path, monkeypatch):
    # External-review finding: two distinct ids could collapse onto the same
    # basename via Path(session_id).name (e.g. "other/victim" -> "victim.json"),
    # letting one session's write silently clobber another's file. The hook
    # must skip the write entirely for an id that fails the allowlist, not
    # derive a basename and write under it.
    transcript = tmp_path / "transcript.jsonl"
    _write_transcript(transcript)

    rc = _run_hook(monkeypatch, tmp_path, transcript, "other-session/victim")

    assert rc == 0
    assert not _out_path(tmp_path, "victim").exists()
    assert not (tmp_path / ".shipwright" / "compliance" / "context-cost"
                / "other-session" / "victim.json").exists()


def test_writer_prefers_payload_session_id_over_env(tmp_path, monkeypatch):
    # This hook runs as a Stop subprocess Claude Code spawns directly -- the
    # SAME process class bloat_gate_on_stop.py's own _session_id docstring
    # documents as NOT reliably inheriting SHIPWRIGHT_SESSION_ID (env-first
    # pooled every session into one shared file until fixed 2026-05-29). The
    # payload is this process's reliable channel, so it must win -- and the
    # statusline (context_cost_statusline.py), which shares this exact
    # process class, resolves the same way via the same
    # context_cost_core.resolve_session_id function, so the two can never
    # diverge from each other. A plain Bash-tool-invoked script (
    # finalize_iterate.py, estimate_context_pressure.py) has no payload at
    # all and reads the env var directly -- a different process class with
    # its own reliable channel, not this one.
    transcript = tmp_path / "transcript.jsonl"
    _write_transcript(transcript)
    payload = {"session_id": "payload-says-this-one", "transcript_path": str(transcript)}
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
    monkeypatch.setenv("SHIPWRIGHT_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setenv("SHIPWRIGHT_SESSION_ID", "env-var-says-this-one")
    monkeypatch.delenv("SHIPWRIGHT_RUN_ID", raising=False)
    (tmp_path / "shipwright_run_config.json").write_text("{}", encoding="utf-8")

    rc = track_context_cost.main()

    assert rc == 0
    assert _out_path(tmp_path, "payload-says-this-one").exists()
    assert not _out_path(tmp_path, "env-var-says-this-one").exists()


def test_writer_falls_back_to_env_when_payload_has_no_session_id(tmp_path, monkeypatch):
    transcript = tmp_path / "transcript.jsonl"
    _write_transcript(transcript)
    payload = {"transcript_path": str(transcript)}
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
    monkeypatch.setenv("SHIPWRIGHT_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setenv("SHIPWRIGHT_SESSION_ID", "env-var-says-this-one")
    monkeypatch.delenv("SHIPWRIGHT_RUN_ID", raising=False)
    (tmp_path / "shipwright_run_config.json").write_text("{}", encoding="utf-8")

    rc = track_context_cost.main()

    assert rc == 0
    assert _out_path(tmp_path, "env-var-says-this-one").exists()
    assert not _out_path(tmp_path, "payload-says-this-one").exists()


def test_hook_skips_the_write_when_neither_payload_nor_env_has_a_session_id(
    tmp_path, monkeypatch
):
    # External-review finding: resolve_session_id used to fall back to the
    # literal "unknown" when both sources were absent, pooling every such
    # firing into one shared file -- exactly the failure class this whole
    # payload-first design exists to route around. Must skip the write
    # entirely instead of guessing a shared placeholder name.
    transcript = tmp_path / "transcript.jsonl"
    _write_transcript(transcript)
    payload = {"transcript_path": str(transcript)}
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
    monkeypatch.setenv("SHIPWRIGHT_PROJECT_ROOT", str(tmp_path))
    monkeypatch.delenv("SHIPWRIGHT_SESSION_ID", raising=False)
    monkeypatch.delenv("SHIPWRIGHT_RUN_ID", raising=False)
    (tmp_path / "shipwright_run_config.json").write_text("{}", encoding="utf-8")

    rc = track_context_cost.main()

    assert rc == 0
    assert not (tmp_path / ".shipwright" / "compliance" / "context-cost").exists()


# Worktree-aware end-to-end tests moved to test_track_context_cost_worktree.py
# (300-line size guideline).
