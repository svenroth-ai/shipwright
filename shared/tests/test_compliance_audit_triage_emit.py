"""Producer test: compliance audit findings collapse to ONE backlog action-unit.

As of iterate-2026-05-31-compliance-triage-bundle, `mirror_findings_to_triage`
emits a single rolling `compliance:backlog:<sig>` item (not one per failing
check), auto-dismisses it when no check fails, refreshes on a changed set, and
one-shot-retires legacy per-check items. Tests the producer directly with
synthetic AuditReports.
"""

from __future__ import annotations

import importlib.util
import sys
from dataclasses import dataclass, field
from pathlib import Path

import pytest

_WORKTREE = Path(__file__).resolve().parents[2]
_SHARED_SCRIPTS = _WORKTREE / "shared" / "scripts"
_COMPLIANCE_SCRIPTS = _WORKTREE / "plugins" / "shipwright-compliance" / "scripts"

if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))
if str(_COMPLIANCE_SCRIPTS.parent) not in sys.path:
    sys.path.insert(0, str(_COMPLIANCE_SCRIPTS.parent))

_DETECTOR_PATH = _COMPLIANCE_SCRIPTS / "audit" / "audit_detector.py"
_spec = importlib.util.spec_from_file_location("audit_detector_under_test", _DETECTOR_PATH)
assert _spec is not None and _spec.loader is not None
audit_detector = importlib.util.module_from_spec(_spec)
sys.modules["audit_detector_under_test"] = audit_detector
_spec.loader.exec_module(audit_detector)

from triage import (  # noqa: E402
    append_triage_item,
    mark_status,
    read_all_items,
)

AuditReport = audit_detector.AuditReport
mirror_findings_to_triage = audit_detector.mirror_findings_to_triage


@dataclass
class _Finding:
    group: str
    check_id: str
    name: str
    severity: str
    source: str = "detective-only"
    status: str = "fail"
    detail: str = ""
    suggested_iterate_cmd: str | None = None
    evidence: list[str] = field(default_factory=list)


def _report(*findings: _Finding) -> AuditReport:
    return AuditReport(findings=list(findings))


@pytest.fixture
def project(tmp_path: Path) -> Path:
    return tmp_path


def _open_backlog(project: Path) -> list[dict]:
    return [it for it in read_all_items(project)
            if it.get("source") == "compliance"
            and it.get("status") == "triage"
            and str(it.get("dedupKey") or "").startswith("compliance:backlog:")]


# --- AC-1: one rolling backlog item -------------------------------------

def test_many_fails_one_backlog_item(project: Path) -> None:
    report = _report(
        _Finding("A", "A2", "RLS missing on x", "HIGH", detail="no RLS on tasks"),
        _Finding("B", "B7", "commit lacks event", "MEDIUM"),
        _Finding("D", "D1", "FR coverage gap", "LOW"),
    )
    out = mirror_findings_to_triage(project, report, run_id="r1", commit="abc")
    assert out["appended"] == 1

    items = _open_backlog(project)
    assert len(items) == 1
    it = items[0]
    assert it["dedupKey"].startswith("compliance:backlog:")
    assert it["kind"] == "compliance"
    assert it["severity"] == "high"          # max(HIGH, MEDIUM, LOW)
    # body lists every failing check key
    for key in ("A/A2", "B/B7", "D/D1"):
        assert key in it["detail"]
    assert it["launchPayload"].startswith("/shipwright-compliance")
    assert it["runId"] == "r1"


def test_pass_skip_not_emitted(project: Path) -> None:
    report = _report(
        _Finding("A", "A1", "n", "HIGH", status="pass"),
        _Finding("A", "A2", "n", "MEDIUM", status="skip"),
    )
    out = mirror_findings_to_triage(project, report)
    assert out["appended"] == 0
    assert read_all_items(project) == []


# --- AC-2: idempotent + refresh -----------------------------------------

def test_idempotent_across_commits(project: Path) -> None:
    report = _report(_Finding("A", "A2", "n", "HIGH"))
    mirror_findings_to_triage(project, report, commit="abc")
    out2 = mirror_findings_to_triage(project, report, commit="def")  # new commit
    assert out2["appended"] == 0
    assert len(_open_backlog(project)) == 1


def test_refresh_on_changed_set(project: Path) -> None:
    mirror_findings_to_triage(project, _report(_Finding("A", "A2", "n", "HIGH")))
    [old] = _open_backlog(project)
    out = mirror_findings_to_triage(
        project, _report(_Finding("A", "A2", "n", "HIGH"), _Finding("B", "B7", "n", "LOW")))
    assert out["appended"] == 1
    assert out["dismissed"] == 1  # stale-sig backlog dismissed
    items = _open_backlog(project)
    assert len(items) == 1
    assert items[0]["dedupKey"] != old["dedupKey"]


# --- AC-3: auto-dismiss when resolved -----------------------------------

def test_auto_dismiss_when_all_resolved(project: Path) -> None:
    mirror_findings_to_triage(project, _report(_Finding("A", "A2", "n", "HIGH")))
    assert len(_open_backlog(project)) == 1
    out = mirror_findings_to_triage(project, _report())   # nothing fails now
    assert out["appended"] == 0
    assert out["dismissed"] == 1
    assert _open_backlog(project) == []
    [item] = read_all_items(project)
    assert item["statusReason"] == "complianceResolved"


def test_empty_report_no_op(project: Path) -> None:
    out = mirror_findings_to_triage(project, _report())
    assert out == {"appended": 0, "dismissed": 0}
    assert read_all_items(project) == []


# --- Terminal statuses preserved ----------------------------------------

def test_promoted_backlog_stays_terminal(project: Path) -> None:
    mirror_findings_to_triage(project, _report(_Finding("A", "A2", "n", "HIGH")))
    [item] = read_all_items(project)
    mark_status(project, item["id"], new_status="promoted", by="op",
                promoted_task_id="EXT:linear-ENG-1", reason="manualPromote")
    out = mirror_findings_to_triage(project, _report())  # resolved
    assert out["dismissed"] == 0                          # promoted not touched
    [item2] = read_all_items(project)
    assert item2["status"] == "promoted"


def test_other_source_items_not_touched(project: Path) -> None:
    pq_id = append_triage_item(
        project, source="phaseQuality", severity="high", kind="bug",
        title="pq finding", detail="d", dedup_key="iterate:C1")
    out = mirror_findings_to_triage(project, _report(_Finding("A", "A2", "n", "HIGH")))
    assert out["appended"] == 1
    items = {it["id"]: it for it in read_all_items(project)}
    assert items[pq_id]["status"] == "triage"   # phaseQuality untouched


# --- AC-4: one-shot legacy per-check retirement -------------------------

def test_legacy_per_check_items_retired(project: Path) -> None:
    # A pre-existing legacy per-check compliance item (old dedup_key=check_id).
    legacy_id = append_triage_item(
        project, source="compliance", severity="medium", kind="compliance",
        title="A/A2: legacy per-check", detail="d", dedup_key="A2")
    out = mirror_findings_to_triage(project, _report(_Finding("D", "D1", "n", "HIGH")))
    assert out["appended"] == 1            # new backlog item
    by_id = {it["id"]: it for it in read_all_items(project)}
    assert by_id[legacy_id]["status"] == "dismissed"
    assert by_id[legacy_id]["statusReason"] == "supersededByBacklog"
    assert len(_open_backlog(project)) == 1


def test_severity_is_max_of_bundle(project: Path) -> None:
    mirror_findings_to_triage(project, _report(
        _Finding("A", "A1", "n", "LOW"), _Finding("B", "B1", "n", "CRITICAL")))
    [it] = _open_backlog(project)
    assert it["severity"] == "critical"
