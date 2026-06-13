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


# --------------------------------------------------------------------------
# worktree_root_for unit (SSoT helper, trg-537334f1)
# --------------------------------------------------------------------------


def test_worktree_root_for_reconstructs_worktree_root(tmp_path):
    assert _bb.worktree_root_for(
        tmp_path, ".worktrees/my-slug/shared/x.py"
    ) == tmp_path / ".worktrees" / "my-slug"


def test_worktree_root_for_none_for_main_tree_path(tmp_path):
    assert _bb.worktree_root_for(tmp_path, "shared/x.py") is None


def test_worktree_root_for_backslash_tolerant(tmp_path):
    assert _bb.worktree_root_for(
        tmp_path, r".worktrees\s\plugins\a\b.py"
    ) == tmp_path / ".worktrees" / "s"


# --------------------------------------------------------------------------
# Writer keys the delta off the WORKTREE baseline (trg-537334f1)
# --------------------------------------------------------------------------


def _seed_worktree_baseline(main: Path, slug: str, paths: list[str],
                            current: int = 320) -> None:
    """A worktree with its OWN baseline (ADR exception entries), no source files."""
    wt = main / ".worktrees" / slug
    wt.mkdir(parents=True, exist_ok=True)
    entries = [{"path": p, "limit": 300, "current": current,
                "state": "exception", "adr": "ADR-z"} for p in paths]
    (wt / "shipwright_bloat_baseline.json").write_text(
        json.dumps({"version": 1, "entries": entries}), encoding="utf-8")


def test_recorder_keys_delta_off_worktree_only_baseline(tmp_path):
    """A file baselined ONLY in the worktree (absent from MAIN's baseline) is
    recorded ``anti-ratchet`` — the writer keys membership off the SAME
    (worktree) baseline the Stop gate measures against, not stale main."""
    from hooks import check_file_size as cfs

    main = tmp_path
    _seed_baseline(main, [], current=410)             # MAIN: file NOT baselined
    _seed_worktree_baseline(main, "s", ["shared/x.py"], current=320)
    wt = main / ".worktrees" / "s" / "shared" / "x.py"
    wt.parent.mkdir(parents=True, exist_ok=True)
    wt.write_text(_lines(320), encoding="utf-8")
    cfs._write_marker_entry(main, str(wt), now=320, limit=300, before=300,
                            payload={"session_id": "sid-A"})
    [entry] = json.loads(
        (main / ".shipwright" / "locks" / "bloat_pending.sid-A.json")
        .read_text(encoding="utf-8"))["entries"]
    assert entry["delta"] == "anti-ratchet", entry
    assert entry["was_in_allowlist"] is True


def test_recorder_main_fallback_when_no_worktree_baseline(tmp_path):
    """No worktree baseline present → the writer falls back to MAIN (preserves
    the trg-305e2aab behavior), so a MAIN-baselined file still records
    ``anti-ratchet``."""
    from hooks import check_file_size as cfs

    main = tmp_path
    _seed_baseline(main, ["shared/x.py"], current=410)   # only MAIN baseline exists
    wt = main / ".worktrees" / "s" / "shared" / "x.py"
    wt.parent.mkdir(parents=True, exist_ok=True)
    wt.write_text(_lines(405), encoding="utf-8")
    cfs._write_marker_entry(main, str(wt), now=405, limit=300, before=400,
                            payload={"session_id": "sid-A"})
    [entry] = json.loads(
        (main / ".shipwright" / "locks" / "bloat_pending.sid-A.json")
        .read_text(encoding="utf-8"))["entries"]
    assert entry["delta"] == "anti-ratchet", entry


# --------------------------------------------------------------------------
# Integration (cross_component): real writer + real Stop gate compose
# --------------------------------------------------------------------------


def test_integration_writer_reader_compose_on_worktree_only_baseline(tmp_path):
    """End-to-end (category: integration): the REAL recorder + the REAL Stop
    gate must agree for a file baselined ONLY in the worktree.

    trg-537334f1 (writer keys delta off the worktree baseline) + trg-28e83840
    (gate resolves ceiling + membership from the same worktree baseline) compose
    so that a file AT its worktree ceiling does NOT block, while the same file
    grown PAST that ceiling DOES block (matching the CI anti-ratchet authority).
    """
    from hooks import check_file_size as cfs

    main = tmp_path
    _seed_baseline(main, [], current=410)             # MAIN: file NOT baselined
    _seed_worktree_baseline(main, "s", ["shared/x.py"], current=320)
    wt_rel = ".worktrees/s/shared/x.py"
    wt = main / ".worktrees" / "s" / "shared" / "x.py"
    wt.parent.mkdir(parents=True, exist_ok=True)

    # (a) file AT its worktree ceiling → recorded anti-ratchet, gate passes.
    wt.write_text(_lines(320), encoding="utf-8")
    cfs._write_marker_entry(main, str(wt), now=320, limit=300, before=300,
                            payload={"session_id": "sid-A"})
    assert _decision(_run_gate(main)) is None, "at-ceiling worktree file must not block"

    # (b) same file grown PAST the worktree ceiling → gate blocks.
    wt.write_text(_lines(330), encoding="utf-8")
    cfs._write_marker_entry(main, str(wt), now=330, limit=300, before=320,
                            payload={"session_id": "sid-A"})
    dec = _decision(_run_gate(main))
    assert dec is not None and dec.get("decision") == "block", (
        "worktree file grown past its worktree ceiling must block"
    )
    assert wt_rel in dec["reason"] or "shared/x.py" in dec["reason"]
