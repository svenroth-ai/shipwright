"""Stop-chain wiring order for audit_compliance_on_stop.py.

Split out of test_audit_compliance_on_stop.py (which keeps the hook's own
behavior: marker lifecycle, opt-out, main()) to stay under the 300-line
source guideline. These tests read the plugins' own hooks.json files
directly — no hook module import needed.
"""

from __future__ import annotations

import json
from pathlib import Path

_WORKTREE = Path(__file__).resolve().parents[2]


def _stop_commands(hooks_json: Path) -> list[str]:
    data = json.loads(hooks_json.read_text(encoding="utf-8"))
    cmds = []
    for group in data["hooks"]["Stop"]:
        for h in group["hooks"]:
            cmds.append(h["command"])
    return cmds


def _idx(cmds, needle):
    for i, c in enumerate(cmds):
        if needle in c:
            return i
    return -1


def test_wired_into_iterate_stop_chain_in_order():
    cmds = _stop_commands(
        _WORKTREE / "plugins" / "shipwright-iterate" / "hooks" / "hooks.json")
    i_self = _idx(cmds, "audit_compliance_on_stop.py")
    i_pq = _idx(cmds, "audit_phase_quality_on_stop.py")
    i_agg = _idx(cmds, "aggregate_triage_on_stop.py")
    i_fin = _idx(cmds, "iterate_stop_finalize.py")
    assert i_self != -1, "compliance audit hook not wired into iterate Stop chain"
    assert i_fin < i_self, "must run AFTER finalize"
    assert i_pq < i_self, "must run AFTER phase_quality"
    assert i_self < i_agg, "must run BEFORE aggregate_triage"


def test_wired_into_changelog_stop_chain_after_phase_quality():
    cmds = _stop_commands(
        _WORKTREE / "plugins" / "shipwright-changelog" / "hooks" / "hooks.json")
    i_self = _idx(cmds, "audit_compliance_on_stop.py")
    i_pq = _idx(cmds, "audit_phase_quality_on_stop.py")
    assert i_self != -1, "compliance audit hook not wired into changelog Stop chain"
    assert i_pq < i_self, "must run AFTER phase_quality"
