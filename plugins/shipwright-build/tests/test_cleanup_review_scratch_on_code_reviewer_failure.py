"""Tests for the review-scratch failure-path safety-net SubagentStop hook.

Root cause (PR #676 external-review finding on iterate-2026-09-03-review-
scratch-path): `code-review-protocol.md` Step 6b writes the review-scratch
diff and deliberately leaves cleanup to Step 6c, which reuses the same file
on a normal completion. If the code-reviewer subagent crashes or returns no
parseable review, 6c is never reached the intended way and the diff would
otherwise linger. This hook is the failure-path backstop: it only acts when
the subagent's own transcript does NOT end in a parseable review payload.
"""
from __future__ import annotations

import importlib.util
import io
import json
from pathlib import Path
from unittest.mock import MagicMock

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
HOOK_PATH = PLUGIN_ROOT / "scripts" / "hooks" / "cleanup-review-scratch-on-code-reviewer-failure.py"


def _load_hook():
    spec = importlib.util.spec_from_file_location(
        "cleanup_review_scratch_on_code_reviewer_failure", HOOK_PATH
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


hook = _load_hook()

SESSION_ID = "sess-abc123"


def _transcript(tmp_path: Path, lines: list[dict]) -> str:
    p = tmp_path / "transcript.jsonl"
    p.write_text("\n".join(json.dumps(x) for x in lines), encoding="utf-8")
    return str(p)


def _ok_cleanup_mock() -> MagicMock:
    return MagicMock(return_value=MagicMock(returncode=0, stderr=""))


def _run_hook(monkeypatch, payload, *, session_id=SESSION_ID, plugin_root=str(PLUGIN_ROOT)):
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
    err = io.StringIO()
    monkeypatch.setattr("sys.stderr", err)
    if session_id is not None:
        monkeypatch.setenv("SHIPWRIGHT_SESSION_ID", session_id)
    else:
        monkeypatch.delenv("SHIPWRIGHT_SESSION_ID", raising=False)
    monkeypatch.setenv("SHIPWRIGHT_PLUGIN_ROOT", plugin_root)
    rc = hook.main([])
    return rc, err.getvalue()


def test_noop_when_no_session_id(monkeypatch):
    rc, err = _run_hook(monkeypatch, {"transcript_path": "/nonexistent"}, session_id=None)
    assert rc == 0
    assert "no SHIPWRIGHT_SESSION_ID" in err


def test_noop_when_reviewer_returned_a_parseable_review(tmp_path, monkeypatch):
    transcript = _transcript(tmp_path, [
        {"role": "user", "content": "Review this diff."},
        {"role": "assistant", "content": '```json\n{"section": "auth", "review": []}\n```'},
    ])
    called = MagicMock()
    monkeypatch.setattr(hook.subprocess, "run", called)
    rc, err = _run_hook(monkeypatch, {"transcript_path": transcript})
    assert rc == 0
    called.assert_not_called()
    assert "no-op" in err


def test_cleans_up_when_reviewer_reply_is_not_parseable(tmp_path, monkeypatch):
    transcript = _transcript(tmp_path, [
        {"role": "user", "content": "Review this diff."},
        {"role": "assistant", "content": "I was unable to complete the review — tool error."},
    ])
    called = _ok_cleanup_mock()
    monkeypatch.setattr(hook.subprocess, "run", called)
    rc, err = _run_hook(monkeypatch, {"transcript_path": transcript})
    assert rc == 0
    called.assert_called_once()
    args = called.call_args.args[0]
    assert args[:2] == ["uv", "run"]
    assert "cleanup" in args
    assert "--run-id" in args
    assert args[args.index("--run-id") + 1] == SESSION_ID
    assert "cleaned up scratch diff" in err


def test_cleans_up_when_transcript_is_not_valid_utf8(tmp_path, monkeypatch):
    # PR #676 round-6: a malformed/non-UTF-8 transcript must not raise
    # UnicodeDecodeError and crash the hook before cleanup runs.
    transcript = tmp_path / "transcript.jsonl"
    transcript.write_bytes(b'{"role": "assistant", "content": "\xff\xfe not utf-8"}')
    called = _ok_cleanup_mock()
    monkeypatch.setattr(hook.subprocess, "run", called)
    rc, err = _run_hook(monkeypatch, {"transcript_path": str(transcript)})
    assert rc == 0
    called.assert_called_once()
    assert "cleaned up scratch diff" in err


def test_cleans_up_when_transcript_is_missing_entirely(tmp_path, monkeypatch):
    called = _ok_cleanup_mock()
    monkeypatch.setattr(hook.subprocess, "run", called)
    rc, _err = _run_hook(monkeypatch, {"transcript_path": str(tmp_path / "nope.jsonl")})
    assert rc == 0
    called.assert_called_once()


def test_cleans_up_when_reply_is_valid_json_but_not_review_shaped(tmp_path, monkeypatch):
    # A reply that parses as JSON but isn't {"section": ..., "review": [...]}
    # (null, {}, a bare string, an unrelated object) must still be treated as
    # a failed review, not silently accepted as success (PR #676 round-3).
    for body in ["null", "{}", '"unable to review"', '{"error": "tool crashed"}']:
        transcript = _transcript(tmp_path, [
            {"role": "assistant", "content": f"```json\n{body}\n```"},
        ])
        called = _ok_cleanup_mock()
        monkeypatch.setattr(hook.subprocess, "run", called)
        rc, err = _run_hook(monkeypatch, {"transcript_path": transcript})
        assert rc == 0
        called.assert_called_once()
        assert "cleaned up scratch diff" in err


def test_logs_failure_when_cleanup_subprocess_exits_nonzero(tmp_path, monkeypatch):
    transcript = _transcript(tmp_path, [
        {"role": "assistant", "content": "I was unable to complete the review — tool error."},
    ])
    failed = MagicMock(return_value=MagicMock(returncode=1, stderr="boom: permission denied"))
    monkeypatch.setattr(hook.subprocess, "run", failed)
    rc, err = _run_hook(monkeypatch, {"transcript_path": transcript})
    assert rc == 0
    failed.assert_called_once()
    assert "cleanup command FAILED" in err
    assert "boom: permission denied" in err
    assert "cleaned up scratch diff" not in err


def test_noop_when_plugin_root_unresolvable(tmp_path, monkeypatch):
    transcript = _transcript(tmp_path, [
        {"role": "assistant", "content": "crashed"},
    ])
    called = MagicMock()
    monkeypatch.setattr(hook.subprocess, "run", called)
    rc, err = _run_hook(monkeypatch, {"transcript_path": transcript}, plugin_root="")
    assert rc == 0
    called.assert_not_called()
    assert "could not resolve shared_root" in err


def test_bad_stdin_never_blocks(monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO("not json"))
    err = io.StringIO()
    monkeypatch.setattr("sys.stderr", err)
    monkeypatch.setenv("SHIPWRIGHT_SESSION_ID", SESSION_ID)
    rc = hook.main([])
    assert rc == 0
