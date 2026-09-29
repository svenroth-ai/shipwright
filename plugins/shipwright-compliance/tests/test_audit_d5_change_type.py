"""D5 change_type exemption (iterate-2026-05-31-compliance-check-context-gate).

D5 (advisory) flags feature/change iterate events with no FR linkage. It must exempt
events whose ``change_type`` ∈ {tooling, compliance, infra, docs} — the same
alternative-to-FR-linkage the ``record_event`` ADR-C.1 gate accepts — while
still flagging genuine feature work that links no FR.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

from scripts.audit import group_d  # noqa: E402


def _events(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def _flagged(f) -> bool:
    """D5 is advisory (FR-01.10/AC06): a flag is a ``pass`` + fix command."""
    return f.status == "pass" and f.suggested_iterate_cmd is not None


def _d5(tmp_path: Path):
    findings = group_d.run(tmp_path, {}, None)
    return next(f for f in findings if f.check_id == "D5")


@pytest.mark.parametrize("change_type", ["tooling", "compliance", "infra", "docs"])
def test_d5_exempts_known_change_types_with_none_reason(tmp_path, change_type):
    # Parity with the record_event gate (BP-1): exempt change_type requires a
    # valid none_reason AND a behavior-preserving spec_impact.
    _events(tmp_path / "shipwright_events.jsonl", [
        {"type": "work_completed", "source": "iterate", "intent": "change",
         "ts": "2026-05-31T00:00:00+00:00", "commit": "c1",
         "change_type": change_type, "none_reason": "framework-internal change",
         "spec_impact": "none"},
    ])
    assert _d5(tmp_path).status == "pass"


def test_d5_flags_behavior_affecting_change_type(tmp_path):
    # BP-1 gate parity: a behavior-affecting change (spec_impact modify) cannot
    # be exempted by change_type — it must link an FR, so D5 flags it (advisory).
    _events(tmp_path / "shipwright_events.jsonl", [
        {"type": "work_completed", "source": "iterate", "intent": "change",
         "ts": "2026-05-31T00:00:00+00:00", "commit": "deadbee4",
         "change_type": "compliance", "none_reason": "behavior change",
         "spec_impact": "MODIFY"},
    ])
    assert _flagged(_d5(tmp_path))


def test_d5_flags_exempt_change_type_without_none_reason(tmp_path):
    # change_type alone is NOT an exemption (the write gate requires both) —
    # an exempt type with a blank none_reason must still be flagged.
    _events(tmp_path / "shipwright_events.jsonl", [
        {"type": "work_completed", "source": "iterate", "intent": "change",
         "ts": "2026-05-31T00:00:00+00:00", "commit": "deadbee3",
         "change_type": "compliance"},
    ])
    assert _flagged(_d5(tmp_path))


def test_d5_still_exempts_spec_impact_none(tmp_path):
    _events(tmp_path / "shipwright_events.jsonl", [
        {"type": "work_completed", "source": "iterate", "intent": "feature",
         "ts": "2026-05-31T00:00:00+00:00", "commit": "c2", "spec_impact": "none"},
    ])
    assert _d5(tmp_path).status == "pass"


@pytest.mark.covers("FR-01.10/AC06")
def test_d5_still_flags_feature_with_no_fr_and_no_exemption(tmp_path):
    # Regression: D5 stays useful — a real feature with neither FR nor exemption is still flagged (advisory).
    _events(tmp_path / "shipwright_events.jsonl", [
        {"type": "work_completed", "source": "iterate", "intent": "feature",
         "ts": "2026-05-31T00:00:00+00:00", "commit": "deadbee2",
         "description": "new capability, no FR"},
    ])
    d5 = _d5(tmp_path)
    assert _flagged(d5)
    assert "deadbee2" in d5.detail


def test_d5_does_not_exempt_unknown_change_type(tmp_path):
    # An unrecognized change_type is NOT an exemption — must still flag.
    _events(tmp_path / "shipwright_events.jsonl", [
        {"type": "work_completed", "source": "iterate", "intent": "change",
         "ts": "2026-05-31T00:00:00+00:00", "commit": "c3",
         "change_type": "feature-work", "spec_impact": "MODIFY"},
    ])
    assert _flagged(_d5(tmp_path))


@pytest.mark.covers("FR-01.10/AC06")
def test_d5_flag_does_not_fail_the_audit(tmp_path):
    # AC06: reported with a suggested fix WITHOUT failing the audit — the
    # aggregate verdict (AuditReport.any_fail -> run_audit exit code) stays green.
    from scripts.audit.audit_detector import AuditReport

    _events(tmp_path / "shipwright_events.jsonl", [
        {"type": "work_completed", "source": "iterate", "intent": "change",
         "ts": "2026-05-31T00:00:00+00:00", "commit": "deadbee5",
         "spec_impact": "MODIFY"},
    ])
    d5 = _d5(tmp_path)
    assert d5.suggested_iterate_cmd
    assert not AuditReport(findings=[d5]).any_fail


@pytest.mark.covers("FR-01.10/AC06")
def test_d5_flag_renders_suggested_command_in_markdown(tmp_path):
    # The human-readable report must carry the fix command for an advisory flag.
    from scripts.audit.audit_detector import AuditReport
    from scripts.audit.audit_report import render_markdown

    _events(tmp_path / "shipwright_events.jsonl", [
        {"type": "work_completed", "source": "iterate", "intent": "change",
         "ts": "2026-05-31T00:00:00+00:00", "commit": "deadbee6",
         "spec_impact": "MODIFY"},
    ])
    d5 = _d5(tmp_path)
    md = render_markdown(AuditReport(findings=[d5]))
    assert "_Suggested:_" in md and d5.suggested_iterate_cmd in md
