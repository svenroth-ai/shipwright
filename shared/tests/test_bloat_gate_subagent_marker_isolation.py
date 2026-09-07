"""Subagent marker isolation — 2026-09-07.

Bug: a campaign orchestrator sharing its git worktree with a background
``sub-iterate-runner`` subagent (spawned via the Agent/Task tool) shares that
subagent's ``session_id`` too — Claude Code only distinguishes the two via the
``agent_id`` payload field, present only inside the subagent call. Both hook
scripts keyed their per-session marker off ``session_id`` alone, so the
subagent's still in-flight, uncommitted oversize edit landed in the SAME
marker file the orchestrator's own Stop event reads — blocking the
orchestrator's turn completion on a file it never touched and had no way to
fix. Observed in campaign-req3-06-mechanics-webui (shipwright-webui repo).

Fix: ``bloat_baseline.marker_key`` (via ``bloat_marker_key.py``) suffixes the
marker key with ``agent_id`` when present, so orchestrator and subagent land
in separate marker files.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

HOOKS_DIR = Path(__file__).resolve().parent.parent / "scripts" / "hooks"
_CFS = HOOKS_DIR / "check_file_size.py"
_GATE = HOOKS_DIR / "bloat_gate_on_stop.py"

SHARED_SESSION_ID = "orchestrator-session-abc"
SUBAGENT_AGENT_ID = "task-sub-iterate-runner-1"


def _env(sid: str | None = None) -> dict:
    env = os.environ.copy()
    env.pop("SHIPWRIGHT_SESSION_ID", None)
    if sid is not None:
        env["SHIPWRIGHT_SESSION_ID"] = sid
    return env


def _run(script: Path, cwd: Path, payload: dict) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(script)],
        input=json.dumps(payload), capture_output=True, text=True,
        encoding="utf-8", errors="replace", cwd=str(cwd), env=_env(),
    )


def _decision(result: subprocess.CompletedProcess) -> dict | None:
    raw = result.stdout.strip()
    return json.loads(raw) if raw else None


def _marker(cwd: Path, key: str) -> Path:
    return cwd / ".shipwright" / "locks" / f"bloat_pending.{key}.json"


def test_writer_keys_subagent_marker_separately_from_orchestrator(tmp_path):
    """PostToolUse from inside a subagent (agent_id set) must NOT write into
    the orchestrator's own bloat_pending.<sid>.json."""
    f = tmp_path / "offender.py"
    f.write_text("x\n" * 420, encoding="utf-8")
    payload = {
        "tool_name": "Write", "session_id": SHARED_SESSION_ID,
        "agent_id": SUBAGENT_AGENT_ID,
        "tool_input": {"file_path": str(f)},
    }
    _run(_CFS, tmp_path, payload)
    assert not _marker(tmp_path, SHARED_SESSION_ID).is_file(), (
        "a subagent's marker must not pool into the orchestrator's own marker file"
    )
    assert _marker(tmp_path, f"{SHARED_SESSION_ID}.{SUBAGENT_AGENT_ID}").is_file()


def test_orchestrator_stop_ignores_inflight_subagent_marker(tmp_path):
    """Integration (category: integration) — the REAL writer + REAL gate
    compose: a background subagent's still in-flight oversize edit must not
    block the orchestrator's own Stop event, because they no longer share a
    marker file. This is the exact repro of the reported bug."""
    (tmp_path / "shipwright_bloat_baseline.json").write_text(
        json.dumps({"version": 1, "entries": []}), encoding="utf-8")
    offender = tmp_path / "server" / "src" / "core" / "preview-session-manager.test.ts"
    offender.parent.mkdir(parents=True, exist_ok=True)
    offender.write_text("x\n" * 343, encoding="utf-8")

    # 1. The background subagent (sub-iterate-runner) edits the file — its
    #    PostToolUse hook fires with agent_id set (same session_id as parent).
    subagent_payload = {
        "tool_name": "Write", "session_id": SHARED_SESSION_ID,
        "agent_id": SUBAGENT_AGENT_ID,
        "tool_input": {"file_path": str(offender)},
    }
    write_result = _run(_CFS, tmp_path, subagent_payload)
    assert write_result.returncode == 0
    assert _marker(tmp_path, f"{SHARED_SESSION_ID}.{SUBAGENT_AGENT_ID}").is_file(), (
        "precondition: the subagent's marker must actually exist, else the gate "
        "passing below would be vacuous (no marker anywhere, not isolation)"
    )

    # 2. The orchestrator's own Stop event fires (its turn ends while the
    #    subagent is still running in the background) — no agent_id.
    stop_result = _run(_GATE, tmp_path, {"session_id": SHARED_SESSION_ID})
    decision = _decision(stop_result)
    assert decision is None or decision.get("decision") != "block", (
        "orchestrator's Stop must not block on a sibling subagent's "
        "in-flight, uncommitted marker"
    )


def test_subagent_own_stop_still_sees_its_own_marker(tmp_path):
    """The subagent's OWN Stop-class event (agent_id present) still finds and
    can act on its own marker — isolation is per-(session,agent), not a
    silent drop of the entry."""
    (tmp_path / "shipwright_bloat_baseline.json").write_text(
        json.dumps({"version": 1, "entries": []}), encoding="utf-8")
    offender = tmp_path / "offender.py"
    offender.write_text("x\n" * 420, encoding="utf-8")
    entry = {
        "path": "offender.py", "now": 420, "limit": 300,
        "classification": "source", "was_in_allowlist": False,
        "delta": "crossing",
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    marker = _marker(tmp_path, f"{SHARED_SESSION_ID}.{SUBAGENT_AGENT_ID}")
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(json.dumps({"version": 1, "entries": [entry]}), encoding="utf-8")

    result = _run(_GATE, tmp_path, {
        "session_id": SHARED_SESSION_ID, "agent_id": SUBAGENT_AGENT_ID,
    })
    decision = _decision(result)
    assert decision is not None and decision.get("decision") == "block"


def test_marker_key_sanitizes_unsafe_agent_id_characters():
    from lib import bloat_marker_key as _bmk

    key = _bmk.marker_key({"session_id": "S", "agent_id": "task/../weird id!"})
    assert key.startswith("S.")
    encoded = key.split(".", 1)[1]
    assert all(c in _bmk._MARKER_KEY_SAFE_CHARS or c == "~" for c in encoded), (
        f"encoded component must be filesystem-safe, got {encoded!r}"
    )


def test_marker_key_encoding_is_collision_free_not_lossy_substitution():
    """External review (2026-09-07): a prior version substituted every unsafe
    character with a single '_', which is LOSSY — 'a/b' and 'a:b' both
    became 'a_b', silently re-pooling two distinct subagents into one marker.
    The encoding must be a bijection: distinct agent_ids -> distinct keys."""
    from lib import bloat_marker_key as _bmk

    key1 = _bmk.marker_key({"session_id": "S", "agent_id": "a/b"})
    key2 = _bmk.marker_key({"session_id": "S", "agent_id": "a:b"})
    assert key1 != key2


def test_marker_key_whitespace_only_agent_id_treated_as_absent():
    from lib import bloat_marker_key as _bmk

    assert _bmk.marker_key({"session_id": "S", "agent_id": "   "}) == "S"


def test_marker_key_no_collision_past_prior_200_char_truncation_boundary():
    """Internal plan review (2026-09-07): a prior version capped the encoded
    output at [:200], which reintroduced the exact collision risk the
    encoding claims to eliminate — two long agent_ids sharing a 200-char
    encoded prefix would collapse to the same key. The cap was removed;
    prove two agent_ids that previously collapsed now stay distinct."""
    from lib import bloat_marker_key as _bmk

    prefix = "x" * 250
    key1 = _bmk.marker_key({"session_id": "S", "agent_id": prefix + "AAAA"})
    key2 = _bmk.marker_key({"session_id": "S", "agent_id": prefix + "BBBB"})
    assert key1 != key2


def test_marker_key_no_agent_id_matches_prior_session_only_behavior():
    from lib import bloat_marker_key as _bmk

    assert _bmk.marker_key({"session_id": "S-A"}) == "S-A"
    assert _bmk.marker_key(None, "S-ENV") == "S-ENV"
    assert _bmk.marker_key(None, None) == "unknown"
