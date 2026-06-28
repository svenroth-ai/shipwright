"""BP-2 producer round-trips: the per-FR ``fr_impact`` map written by both
write-paths (the ``record_event`` CLI and the ``finalize_iterate`` worktree
F5b path) lands on disk in the normalized shape. The reader side
(``WorkEvent.from_dict``) is pinned in the compliance plugin's
``test_reconciliation.py``; together they cover write→read.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
_TOOLS = _SCRIPTS / "tools"
for _p in (str(_SCRIPTS), str(_TOOLS)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from record_event import build_event, main, parse_args, read_events  # noqa: E402


def _work_argv(project_root, **extra):
    argv = [
        "--project-root", str(project_root), "--type", "work_completed",
        "--source", "iterate", "--commit", "abc1234",
    ]
    for flag, val in extra.items():
        argv += ["--" + flag.replace("_", "-"), val]
    return argv


def _read_work(project_root):
    return [e for e in read_events(project_root) if e.get("type") == "work_completed"]


# --------------------------------------------------------------------------
# record_event CLI / build_event
# --------------------------------------------------------------------------

class TestRecordEventFrImpact:
    def test_build_event_normalizes_fr_impact(self):
        args = parse_args(_work_argv(
            ".", affected_frs="FR-01.07", spec_impact="modify",
            fr_impact='{"FR-01.07":"MODIFY"}'))
        event = build_event(args)
        assert event["fr_impact"] == {"FR-01.07": "modify"}

    def test_invalid_impact_value_rejected(self):
        args = parse_args(_work_argv(
            ".", affected_frs="FR-1", spec_impact="modify",
            fr_impact='{"FR-1":"tweak"}'))
        with pytest.raises(ValueError):
            build_event(args)

    def test_invalid_json_rejected(self):
        args = parse_args(_work_argv(
            ".", affected_frs="FR-1", spec_impact="modify", fr_impact="{not json"))
        with pytest.raises(ValueError):
            build_event(args)

    def test_cli_write_then_read_roundtrip(self, tmp_path, monkeypatch):
        monkeypatch.delenv("SHIPWRIGHT_SESSION_ID", raising=False)
        (tmp_path / "shipwright_events.jsonl").write_text("", encoding="utf-8")
        rc = main(_work_argv(
            tmp_path, affected_frs="FR-02.03", spec_impact="modify",
            fr_impact='{"FR-02.03":"modify"}'))
        assert rc == 0
        events = _read_work(tmp_path)
        assert len(events) == 1
        assert events[0]["fr_impact"] == {"FR-02.03": "modify"}

    def test_fr_impact_passes_fr_gate_with_linkage(self):
        # AC: the FR-gate + spec-impact gate still pass for a behavior-affecting
        # event that links its FR and carries the per-FR map.
        from record_event import _fr_or_change_type_gate_error
        event = build_event(parse_args(_work_argv(
            ".", source="iterate", intent="change", affected_frs="FR-1",
            spec_impact="modify", fr_impact='{"FR-1":"modify"}')))
        assert _fr_or_change_type_gate_error(event) is None


# --------------------------------------------------------------------------
# finalize_iterate worktree F5b path (event_extras)
# --------------------------------------------------------------------------

class TestFinalizeFrImpact:
    def _record(self, project_root, extras):
        from tools.finalize_iterate import _record_event
        return _record_event(project_root, "", "iterate-test-run", "desc",
                             event_extras=extras)

    def test_f5b_carries_and_normalizes_fr_impact(self, tmp_path, monkeypatch):
        monkeypatch.delenv("SHIPWRIGHT_SESSION_ID", raising=False)
        (tmp_path / "shipwright_events.jsonl").write_text("", encoding="utf-8")
        self._record(tmp_path, {
            "affected_frs": ["FR-09.01"], "spec_impact": "modify",
            "fr_impact": {"FR-09.01": "MODIFY"},
        })
        events = _read_work(tmp_path)
        assert events[0]["fr_impact"] == {"FR-09.01": "modify"}

    def test_f5b_rejects_malformed_fr_impact(self, tmp_path, monkeypatch):
        # Fail-closed parity with the record_event CLI + the FR-gate: a malformed
        # map raises (the producer bug surfaces) rather than silently dropping a
        # grade signal, and nothing is written to the log.
        from tools.finalize_iterate import FinalizeGateError
        monkeypatch.delenv("SHIPWRIGHT_SESSION_ID", raising=False)
        (tmp_path / "shipwright_events.jsonl").write_text("", encoding="utf-8")
        with pytest.raises(FinalizeGateError):
            self._record(tmp_path, {
                "change_type": "tooling", "none_reason": "no-FR infra",
                "spec_impact": "none", "fr_impact": "garbage-not-a-dict",
            })
        assert _read_work(tmp_path) == []
