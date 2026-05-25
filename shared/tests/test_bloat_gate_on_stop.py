"""Tests for shared/scripts/hooks/bloat_gate_on_stop.py — Campaign A.foundation."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

HOOKS_DIR = Path(__file__).resolve().parent.parent / "scripts" / "hooks"


def _lines(n: int) -> str:
    return "x\n" * n


def _run_gate(cwd: Path, session_id: str = "sid-A",
              stdin: str = "{}") -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["SHIPWRIGHT_SESSION_ID"] = session_id
    return subprocess.run(
        [sys.executable, str(HOOKS_DIR / "bloat_gate_on_stop.py")],
        input=stdin, capture_output=True, text=True,
        encoding="utf-8", errors="replace", cwd=str(cwd), env=env,
    )


def _seed_marker(cwd: Path, session_id: str, entries: list[dict]) -> Path:
    locks = cwd / ".shipwright" / "locks"
    locks.mkdir(parents=True, exist_ok=True)
    marker = locks / f"bloat_pending.{session_id}.json"
    doc = {"version": 1, "entries": entries}
    marker.write_text(json.dumps(doc), encoding="utf-8")
    return marker


def _seed_baseline(cwd: Path, paths: list[str]) -> Path:
    target = cwd / "shipwright_bloat_baseline.json"
    entries = [
        {"path": p, "limit": 300, "current": 410,
         "state": "grandfathered", "adr": None}
        for p in paths
    ]
    target.write_text(
        json.dumps({"version": 1, "entries": entries}), encoding="utf-8",
    )
    return target


def _entry(path: str, *, delta: str = "crossing", now: int = 320,
           limit: int = 300, was_in_allowlist: bool = False,
           ts: str | None = None,
           classification: str = "source") -> dict:
    return {
        "path": path,
        "now": now,
        "limit": limit,
        "classification": classification,
        "was_in_allowlist": was_in_allowlist,
        "delta": delta,
        "ts": ts or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def _parse_decision(result) -> dict | None:
    """Parse the gate's stdout JSON; ``None`` when stdout is blank."""
    raw = result.stdout.strip()
    if not raw:
        return None
    return json.loads(raw)


# AC-7: no-baseline / malformed-baseline pass-through (fail-open) -----

def test_no_baseline_pass_silent(tmp_path):
    # Seed a marker but no baseline.
    (tmp_path / "foo.py").write_text(_lines(320), encoding="utf-8")
    _seed_marker(tmp_path, "sid-A", [_entry("foo.py")])
    result = _run_gate(tmp_path, session_id="sid-A")
    assert result.returncode == 0
    decision = _parse_decision(result)
    assert decision is None or decision.get("decision") != "block"


def test_malformed_baseline_pass_silent_with_stderr(tmp_path):
    (tmp_path / "shipwright_bloat_baseline.json").write_text(
        "{not valid", encoding="utf-8",
    )
    (tmp_path / "foo.py").write_text(_lines(320), encoding="utf-8")
    _seed_marker(tmp_path, "sid-A", [_entry("foo.py")])
    result = _run_gate(tmp_path, session_id="sid-A")
    assert result.returncode == 0
    decision = _parse_decision(result)
    assert decision is None or decision.get("decision") != "block"
    assert "bloat" in result.stderr.lower() or "baseline" in result.stderr.lower()


def test_no_marker_pass_silent(tmp_path):
    _seed_baseline(tmp_path, [])
    result = _run_gate(tmp_path, session_id="sid-A")
    assert result.returncode == 0
    decision = _parse_decision(result)
    assert decision is None or decision.get("decision") != "block"


# AC-4 / AC-5: blocks on anti-ratchet + new crossing ------------------

def test_blocks_on_anti_ratchet(tmp_path):
    """Anti-ratchet always blocks, regardless of baseline content."""
    _seed_baseline(tmp_path, ["legacy.py"])
    (tmp_path / "legacy.py").write_text(_lines(420), encoding="utf-8")
    _seed_marker(tmp_path, "sid-A", [_entry(
        "legacy.py", delta="anti-ratchet", now=420, was_in_allowlist=True,
    )])
    result = _run_gate(tmp_path, session_id="sid-A")
    assert result.returncode == 0
    decision = _parse_decision(result)
    assert decision is not None
    assert decision.get("decision") == "block"
    assert decision.get("reason", "")  # non-empty reason
    # Iron-Law-style message body.
    assert "NO COMPLETION" in decision["reason"] or "IRON LAW" in decision["reason"].upper()
    # File path appears in the reason.
    assert "legacy.py" in decision["reason"]


def test_blocks_on_new_crossing_outside_baseline(tmp_path):
    _seed_baseline(tmp_path, ["other.py"])
    (tmp_path / "new_offender.py").write_text(_lines(320), encoding="utf-8")
    _seed_marker(tmp_path, "sid-A", [_entry("new_offender.py")])
    result = _run_gate(tmp_path, session_id="sid-A")
    decision = _parse_decision(result)
    assert decision is not None
    assert decision.get("decision") == "block"
    assert "new_offender.py" in decision["reason"]


# AC-8: grandfathered crossing passes (path in baseline) --------------

def test_grandfathered_crossing_passes(tmp_path):
    _seed_baseline(tmp_path, ["legacy.py"])
    (tmp_path / "legacy.py").write_text(_lines(411), encoding="utf-8")
    # Gate consults baseline directly; was_in_allowlist=False is a stale
    # producer flag (baseline absent at write-time) — gate corrects.
    _seed_marker(tmp_path, "sid-A", [_entry(
        "legacy.py", delta="crossing", now=411, was_in_allowlist=False,
    )])
    decision = _parse_decision(_run_gate(tmp_path, session_id="sid-A"))
    assert decision is None or decision.get("decision") != "block"


def test_path_normalization_grandfathers_backslash_baseline(tmp_path):
    """Baseline stored with backslashes; marker uses forward slashes."""
    target = tmp_path / "shipwright_bloat_baseline.json"
    target.write_text(json.dumps({"version": 1, "entries": [
        {"path": r"sub\legacy.py", "limit": 300, "current": 410,
         "state": "grandfathered", "adr": None},
    ]}), encoding="utf-8")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "legacy.py").write_text(_lines(411), encoding="utf-8")
    _seed_marker(tmp_path, "sid-A", [_entry(
        "sub/legacy.py", delta="crossing", now=411, was_in_allowlist=False,
    )])
    result = _run_gate(tmp_path, session_id="sid-A")
    decision = _parse_decision(result)
    assert decision is None or decision.get("decision") != "block"


# Stale-violation re-measurement (Gemini HIGH #2) ---------------------

def test_stale_marker_skipped_when_file_under_limit(tmp_path):
    _seed_baseline(tmp_path, [])
    # File has been fixed to be under the limit since the marker was written.
    (tmp_path / "now_fixed.py").write_text(_lines(150), encoding="utf-8")
    _seed_marker(tmp_path, "sid-A", [_entry("now_fixed.py", now=320)])
    result = _run_gate(tmp_path, session_id="sid-A")
    decision = _parse_decision(result)
    assert decision is None or decision.get("decision") != "block"


def test_missing_file_marker_skipped(tmp_path):
    _seed_baseline(tmp_path, [])
    _seed_marker(tmp_path, "sid-A", [_entry("ghost.py")])
    result = _run_gate(tmp_path, session_id="sid-A")
    decision = _parse_decision(result)
    assert decision is None or decision.get("decision") != "block"


# AC-4: session scoping (Gemini HIGH #3 / OpenAI HIGH #1) -------------

def test_session_scoping_ignores_other_session_marker(tmp_path):
    _seed_baseline(tmp_path, [])
    (tmp_path / "other.py").write_text(_lines(420), encoding="utf-8")
    _seed_marker(tmp_path, "sid-B", [_entry(
        "other.py", delta="anti-ratchet", now=420, was_in_allowlist=True,
    )])
    # Run with sid-A — should not see sid-B's marker.
    result = _run_gate(tmp_path, session_id="sid-A")
    decision = _parse_decision(result)
    assert decision is None or decision.get("decision") != "block"


def test_session_scoping_unknown_fallback(tmp_path):
    """Missing SHIPWRIGHT_SESSION_ID falls back to bloat_pending.unknown.json."""
    _seed_baseline(tmp_path, [])
    (tmp_path / "f.py").write_text(_lines(420), encoding="utf-8")
    _seed_marker(tmp_path, "unknown", [_entry(
        "f.py", delta="anti-ratchet", now=420, was_in_allowlist=True,
    )])
    env = {k: v for k, v in os.environ.items() if k != "SHIPWRIGHT_SESSION_ID"}
    result = subprocess.run(
        [sys.executable, str(HOOKS_DIR / "bloat_gate_on_stop.py")],
        input="{}", capture_output=True, text=True,
        encoding="utf-8", errors="replace", cwd=str(tmp_path), env=env,
    )
    decision = _parse_decision(result)
    assert decision is not None and decision.get("decision") == "block"


# TTL filter ----------------------------------------------------------

def test_ttl_filter_skips_old_markers(tmp_path):
    _seed_baseline(tmp_path, [])
    (tmp_path / "f.py").write_text(_lines(420), encoding="utf-8")
    old_ts = "2020-01-01T00:00:00Z"
    _seed_marker(tmp_path, "sid-A", [_entry(
        "f.py", delta="anti-ratchet", now=420, was_in_allowlist=True,
        ts=old_ts,
    )])
    result = _run_gate(tmp_path, session_id="sid-A")
    decision = _parse_decision(result)
    assert decision is None or decision.get("decision") != "block"


# Fail-open on malformed marker ---------------------------------------

def test_malformed_marker_pass_silent(tmp_path):
    _seed_baseline(tmp_path, [])
    locks = tmp_path / ".shipwright" / "locks"
    locks.mkdir(parents=True)
    (locks / "bloat_pending.sid-A.json").write_text("{not valid", encoding="utf-8")
    result = _run_gate(tmp_path, session_id="sid-A")
    decision = _parse_decision(result)
    assert decision is None or decision.get("decision") != "block"


# Iron-Law message contents (AC-6) ------------------------------------

def test_block_reason_contains_red_flags_and_rationalization(tmp_path):
    _seed_baseline(tmp_path, ["legacy.py"])
    (tmp_path / "legacy.py").write_text(_lines(420), encoding="utf-8")
    _seed_marker(tmp_path, "sid-A", [_entry(
        "legacy.py", delta="anti-ratchet", now=420, was_in_allowlist=True,
    )])
    result = _run_gate(tmp_path, session_id="sid-A")
    decision = _parse_decision(result)
    reason = decision["reason"]
    # Iron-Law header
    assert "IRON LAW" in reason.upper()
    # Red-Flags section header (adapted to bloat)
    assert "Red Flag" in reason or "RED FLAGS" in reason.upper()
    # Rationalization-Prevention section
    assert "Rationaliz" in reason
    # MIT attribution / Superpowers reference
    assert "Superpowers" in reason or "Jesse Vincent" in reason


# Hook output schema compliance (Stop event, ADR-042) -----------------

def test_block_output_uses_top_level_decision_not_additional_context(tmp_path):
    _seed_baseline(tmp_path, [])
    (tmp_path / "f.py").write_text(_lines(420), encoding="utf-8")
    _seed_marker(tmp_path, "sid-A", [_entry(
        "f.py", delta="anti-ratchet", now=420, was_in_allowlist=True,
    )])
    result = _run_gate(tmp_path, session_id="sid-A")
    decision = _parse_decision(result)
    assert decision is not None
    # Top-level keys only.
    assert decision.get("decision") == "block"
    # If hookSpecificOutput present, it must NOT carry additionalContext.
    hso = decision.get("hookSpecificOutput", {})
    assert "additionalContext" not in hso
