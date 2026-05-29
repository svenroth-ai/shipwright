"""Session-id source for the bloat wave: stdin payload, not env-only.

Bug (found 2026-05-29): both ``check_file_size.py`` (PostToolUse, marker writer)
and ``bloat_gate_on_stop.py`` (Stop, gate) derived the per-session marker name
from the ``SHIPWRIGHT_SESSION_ID`` *env var*, which is NOT set in those hook
processes. Every session therefore pooled into one shared
``bloat_pending.unknown.json`` bucket — so an oversize file edited in session A
(or another worktree) blocked session B's Stop. Claude Code passes the canonical
``session_id`` in the hook *stdin payload* (same value across PostToolUse + Stop
of one session); these hooks must read it there, falling back to env then
``"unknown"``.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

HOOKS_DIR = Path(__file__).resolve().parent.parent / "scripts" / "hooks"
_CFS = HOOKS_DIR / "check_file_size.py"
_GATE = HOOKS_DIR / "bloat_gate_on_stop.py"


def _env(sid: str | None) -> dict:
    env = os.environ.copy()
    env.pop("SHIPWRIGHT_SESSION_ID", None)
    if sid is not None:
        env["SHIPWRIGHT_SESSION_ID"] = sid
    return env


def _run(script: Path, cwd: Path, payload: dict, *, env_sid: str | None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(script)],
        input=json.dumps(payload), capture_output=True, text=True,
        encoding="utf-8", errors="replace", cwd=str(cwd), env=_env(env_sid),
    )


def _marker(cwd: Path, sid: str) -> Path:
    return cwd / ".shipwright" / "locks" / f"bloat_pending.{sid}.json"


def _seed_marker(cwd: Path, sid: str, entries: list[dict]) -> None:
    mp = _marker(cwd, sid)
    mp.parent.mkdir(parents=True, exist_ok=True)
    mp.write_text(json.dumps({"version": 1, "entries": entries}), encoding="utf-8")


def _crossing(path: str) -> dict:
    import time
    return {
        "path": path, "now": 420, "limit": 300, "classification": "source",
        "was_in_allowlist": False, "delta": "crossing",
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def _decision(result) -> dict | None:
    raw = result.stdout.strip()
    return json.loads(raw) if raw else None


# --- check_file_size.py (marker writer) ------------------------------------

def test_marker_keyed_by_payload_session_id(tmp_path):
    """Payload session_id (env UNSET) → marker is bloat_pending.<sid>.json."""
    f = tmp_path / "big.py"
    f.write_text("x\n" * 420, encoding="utf-8")
    payload = {"tool_name": "Write", "session_id": "S-A",
               "tool_input": {"file_path": str(f)}}
    _run(_CFS, tmp_path, payload, env_sid=None)
    assert _marker(tmp_path, "S-A").is_file(), "marker must be keyed off payload session_id"
    assert not _marker(tmp_path, "unknown").is_file(), "must NOT pool into the unknown bucket"


def test_marker_unknown_when_no_payload_no_env(tmp_path):
    """Backward-compat: no payload sid + no env → unknown bucket (unchanged)."""
    f = tmp_path / "big.py"
    f.write_text("x\n" * 420, encoding="utf-8")
    payload = {"tool_name": "Write", "tool_input": {"file_path": str(f)}}
    _run(_CFS, tmp_path, payload, env_sid=None)
    assert _marker(tmp_path, "unknown").is_file()


# --- bloat_gate_on_stop.py (gate) ------------------------------------------

def test_gate_reads_payload_session_id(tmp_path):
    """Gate keyed off payload session_id (env UNSET) → blocks on that marker."""
    (tmp_path / "shipwright_bloat_baseline.json").write_text(
        json.dumps({"version": 1, "entries": []}), encoding="utf-8")
    (tmp_path / "off.py").write_text("x\n" * 420, encoding="utf-8")
    _seed_marker(tmp_path, "S-A", [_crossing("off.py")])
    result = _run(_GATE, tmp_path, {"session_id": "S-A"}, env_sid=None)
    decision = _decision(result)
    assert decision is not None and decision.get("decision") == "block"


def test_gate_isolates_cross_session_marker(tmp_path):
    """Session B must NOT block on session A's marker."""
    (tmp_path / "shipwright_bloat_baseline.json").write_text(
        json.dumps({"version": 1, "entries": []}), encoding="utf-8")
    (tmp_path / "off.py").write_text("x\n" * 420, encoding="utf-8")
    _seed_marker(tmp_path, "S-A", [_crossing("off.py")])
    result = _run(_GATE, tmp_path, {"session_id": "S-B"}, env_sid=None)
    decision = _decision(result)
    assert decision is None or decision.get("decision") != "block"


def test_gate_payload_session_id_beats_env(tmp_path):
    """When both present, payload session_id wins (consistent with writer)."""
    (tmp_path / "shipwright_bloat_baseline.json").write_text(
        json.dumps({"version": 1, "entries": []}), encoding="utf-8")
    (tmp_path / "off.py").write_text("x\n" * 420, encoding="utf-8")
    _seed_marker(tmp_path, "S-PAYLOAD", [_crossing("off.py")])
    result = _run(_GATE, tmp_path, {"session_id": "S-PAYLOAD"}, env_sid="S-ENV")
    decision = _decision(result)
    assert decision is not None and decision.get("decision") == "block"
