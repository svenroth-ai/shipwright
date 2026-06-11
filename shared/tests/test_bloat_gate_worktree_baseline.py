"""Regression: the bloat Stop-gate must resolve a file's ceiling from the SAME
tree it re-measures the file in (trg-28e83840 — gap left by #150/trg-305e2aab).

A `/shipwright-iterate` worktree that bumps an already-baselined file's ceiling
via an ADR exception commits the bump in the WORKTREE's
`shipwright_bloat_baseline.json` — it is NOT on `main` until the PR merges. The
Stop gate re-measures the worktree file (`main_root/.worktrees/<slug>/...`) but
must read the ceiling from that worktree's baseline, not the stale main baseline,
or it false-blocks (the symptom hit during PR #184). Reuses the subprocess +
seeding helpers from ``test_bloat_gate_on_stop``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_bloat_gate_on_stop import (  # noqa: E402
    _entry,
    _lines,
    _parse_decision,
    _run_gate,
    _seed_baseline,
    _seed_marker,
)

_REL = "shared/x.py"
_SLUG = "iterate-2026-06-11-x"
_WT_REL = f".worktrees/{_SLUG}/{_REL}"


def _seed_worktree_baseline(main_root: Path, current: int, *, file_lines: int) -> None:
    """Create a worktree with its own (bumped) baseline + the grown file."""
    wt = main_root / ".worktrees" / _SLUG
    (wt / "shared").mkdir(parents=True, exist_ok=True)
    (wt / _REL).write_text(_lines(file_lines), encoding="utf-8")
    (wt / "shipwright_bloat_baseline.json").write_text(
        json.dumps({"version": 1, "entries": [
            {"path": _REL, "limit": 300, "current": current,
             "state": "exception", "adr": "ADR-099"}]}),
        encoding="utf-8")


def test_worktree_baseline_bump_not_false_blocked(tmp_path):
    """File grown to the WORKTREE's bumped ceiling (420==420) must NOT block,
    even though the stale main baseline still says 410. (Fails pre-fix: the gate
    reads main's 410 ceiling and blocks 420>410.)"""
    _seed_baseline(tmp_path, [_REL])                 # main ceiling = 410
    _seed_worktree_baseline(tmp_path, 420, file_lines=420)  # worktree ceiling = 420, file = 420
    _seed_marker(tmp_path, "sid-A", [_entry(
        _WT_REL, delta="anti-ratchet", now=420, was_in_allowlist=True)])

    decision = _parse_decision(_run_gate(tmp_path, session_id="sid-A"))
    assert decision is None or decision.get("decision") != "block", (
        "worktree-committed baseline bump (file==worktree ceiling) must not "
        "false-block — the gate must read the worktree's baseline, not main's"
    )


def test_worktree_file_over_worktree_ceiling_still_blocks(tmp_path):
    """The fix must NOT mask a real ratchet: a file exceeding even the WORKTREE's
    (bumped) ceiling still blocks (430 > worktree ceiling 420)."""
    _seed_baseline(tmp_path, [_REL])                 # main ceiling = 410
    _seed_worktree_baseline(tmp_path, 420, file_lines=430)  # worktree ceiling = 420, file = 430
    _seed_marker(tmp_path, "sid-A", [_entry(
        _WT_REL, delta="anti-ratchet", now=430, was_in_allowlist=True)])

    decision = _parse_decision(_run_gate(tmp_path, session_id="sid-A"))
    assert decision is not None and decision.get("decision") == "block"
    assert _WT_REL in decision["reason"] or _REL in decision["reason"]


def test_worktree_newly_baselined_file_not_treated_as_crossing(tmp_path):
    """A file baselined ONLY in the worktree (new ADR exception entry, absent
    from main's baseline) must not be treated as a new crossing — the gate reads
    the worktree baseline for the membership check too."""
    _seed_baseline(tmp_path, [])                     # main: file NOT baselined
    _seed_worktree_baseline(tmp_path, 410, file_lines=410)  # worktree: baselined at 410, file = 410
    _seed_marker(tmp_path, "sid-A", [_entry(
        _WT_REL, delta="crossing", now=410, was_in_allowlist=False)])

    decision = _parse_decision(_run_gate(tmp_path, session_id="sid-A"))
    assert decision is None or decision.get("decision") != "block"
