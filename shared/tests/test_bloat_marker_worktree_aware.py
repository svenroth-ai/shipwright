"""Regression tests for trg-305e2aab — the bloat marker / Stop gate is
worktree-aware.

A ``/shipwright-iterate`` worktree run edits files under
``<main-root>/.worktrees/<slug>/...``; the PostTool recorder
(``check_file_size.py``) and the Stop gate (``bloat_gate_on_stop.py``) run from
the MAIN root, so the marker stores a ``.worktrees/<slug>/...`` path. That path
must resolve to the repo-relative baseline key (``shared/x.py``) for the
baseline lookup, else an already-baselined file is mis-classified ``crossing``
and the Stop gate false-blocks — even though the committed baseline + the CI
anti-ratchet gate correctly pass.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
HOOKS_DIR = _SCRIPTS / "hooks"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from lib import bloat_baseline as _bb  # noqa: E402


# --------------------------------------------------------------------------
# strip_worktree_prefix unit
# --------------------------------------------------------------------------


def test_strip_worktree_prefix_strips_one_segment():
    assert _bb.strip_worktree_prefix(
        ".worktrees/my-slug/shared/x.py") == "shared/x.py"


def test_strip_worktree_prefix_idempotent_for_repo_relative():
    assert _bb.strip_worktree_prefix("shared/x.py") == "shared/x.py"


def test_strip_worktree_prefix_normalizes_backslashes():
    assert _bb.strip_worktree_prefix(
        ".worktrees\\s\\plugins\\a\\b.py") == "plugins/a/b.py"


def test_strip_worktree_prefix_only_strips_leading_worktrees():
    # A real (non-worktree) path that merely contains the word is untouched.
    assert _bb.strip_worktree_prefix("a/.worktrees/x/y.py") == "a/.worktrees/x/y.py"


# --------------------------------------------------------------------------
# Stop-gate harness
# --------------------------------------------------------------------------


def _lines(n: int) -> str:
    return "x\n" * n


def _run_gate(cwd: Path, session_id: str = "sid-A") -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["SHIPWRIGHT_SESSION_ID"] = session_id
    return subprocess.run(
        [sys.executable, str(HOOKS_DIR / "bloat_gate_on_stop.py")],
        input="{}", capture_output=True, text=True,
        encoding="utf-8", errors="replace", cwd=str(cwd), env=env,
    )


def _seed_baseline(cwd: Path, paths: list[str], current: int = 410) -> None:
    entries = [{"path": p, "limit": 300, "current": current,
                "state": "exception", "adr": "ADR-x"} for p in paths]
    (cwd / "shipwright_bloat_baseline.json").write_text(
        json.dumps({"version": 1, "entries": entries}), encoding="utf-8")


def _seed_marker(cwd: Path, sid: str, path: str, delta: str, now: int) -> None:
    locks = cwd / ".shipwright" / "locks"
    locks.mkdir(parents=True, exist_ok=True)
    entry = {
        "path": path, "now": now, "limit": 300, "classification": "source",
        "was_in_allowlist": delta == "anti-ratchet", "delta": delta,
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    (locks / f"bloat_pending.{sid}.json").write_text(
        json.dumps({"version": 1, "entries": [entry]}), encoding="utf-8")


def _seed_worktree_file(cwd: Path, rel: str, n: int) -> None:
    p = cwd / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(_lines(n), encoding="utf-8")


def _decision(result) -> dict | None:
    raw = result.stdout.strip()
    return json.loads(raw) if raw else None


def test_worktree_prefixed_baselined_crossing_does_not_block(tmp_path):
    """The bug: recorder mis-classifies a worktree edit of an already-baselined
    file as ``crossing``; the gate must resolve the stripped key, see it IS in
    the baseline, and NOT block (file 405 <= committed ceiling 410)."""
    _seed_baseline(tmp_path, ["shared/x.py"], current=410)
    _seed_worktree_file(tmp_path, ".worktrees/my-slug/shared/x.py", 405)
    _seed_marker(tmp_path, "sid-A", ".worktrees/my-slug/shared/x.py", "crossing", 405)
    result = _run_gate(tmp_path)
    assert _decision(result) is None, f"false-blocked: {result.stdout}"


def test_worktree_prefixed_anti_ratchet_within_ceiling_does_not_block(tmp_path):
    """delta=anti-ratchet on a worktree path resolves its ceiling via the
    stripped key; within ceiling → no block."""
    _seed_baseline(tmp_path, ["shared/x.py"], current=410)
    _seed_worktree_file(tmp_path, ".worktrees/s/shared/x.py", 405)
    _seed_marker(tmp_path, "sid-A", ".worktrees/s/shared/x.py", "anti-ratchet", 405)
    result = _run_gate(tmp_path)
    assert _decision(result) is None, f"false-blocked: {result.stdout}"


def test_worktree_prefixed_anti_ratchet_over_ceiling_still_blocks(tmp_path):
    """A genuine ratchet (file 420 > ceiling 410) on a worktree path STILL
    blocks — the fix resolves the key, it does not weaken the gate."""
    _seed_baseline(tmp_path, ["shared/x.py"], current=410)
    _seed_worktree_file(tmp_path, ".worktrees/s/shared/x.py", 420)
    _seed_marker(tmp_path, "sid-A", ".worktrees/s/shared/x.py", "anti-ratchet", 420)
    result = _run_gate(tmp_path)
    dec = _decision(result)
    assert dec is not None and dec.get("decision") == "block"


def test_worktree_prefixed_genuine_new_crossing_still_blocks(tmp_path):
    """A worktree file NOT in the baseline is a real new crossing → still blocks."""
    _seed_baseline(tmp_path, ["shared/other.py"], current=410)
    _seed_worktree_file(tmp_path, ".worktrees/s/shared/x.py", 405)
    _seed_marker(tmp_path, "sid-A", ".worktrees/s/shared/x.py", "crossing", 405)
    result = _run_gate(tmp_path)
    dec = _decision(result)
    assert dec is not None and dec.get("decision") == "block"


def test_recorder_classifies_worktree_baselined_file_as_anti_ratchet(tmp_path):
    """The write-side half: check_file_size records a worktree edit of an
    already-baselined file as ``anti-ratchet`` (not a new ``crossing``)."""
    from hooks import check_file_size as cfs

    _seed_baseline(tmp_path, ["shared/x.py"], current=410)
    wt = tmp_path / ".worktrees" / "s" / "shared" / "x.py"
    wt.parent.mkdir(parents=True, exist_ok=True)
    wt.write_text(_lines(405), encoding="utf-8")
    cfs._write_marker_entry(tmp_path, str(wt), now=405, limit=300, before=400,
                            payload={"session_id": "sid-A"})
    marker = json.loads(
        (tmp_path / ".shipwright" / "locks" / "bloat_pending.sid-A.json")
        .read_text(encoding="utf-8"))
    [entry] = marker["entries"]
    assert entry["delta"] == "anti-ratchet", entry
    # The stored path keeps the worktree prefix (needed for re-measure).
    assert entry["path"] == ".worktrees/s/shared/x.py"
