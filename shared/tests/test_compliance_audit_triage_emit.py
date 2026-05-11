"""AC-5 producer test: Compliance audit findings land in triage.jsonl;
disappeared findings auto-dismissed.

Tests `mirror_findings_to_triage` directly with synthetic AuditReports
to avoid coupling to the live audit groups. Cross-plugin import via
explicit sys.path insertion (audit_detector lives under
plugins/shipwright-compliance/).
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

# Make triage importable
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

# Make `scripts.audit.audit_adapters` importable from the compliance plugin
if str(_COMPLIANCE_SCRIPTS.parent) not in sys.path:
    sys.path.insert(0, str(_COMPLIANCE_SCRIPTS.parent))

# Load audit_detector via importlib so we don't depend on the compliance
# plugin's conftest/__init__ side effects.
_DETECTOR_PATH = _COMPLIANCE_SCRIPTS / "audit" / "audit_detector.py"
_spec = importlib.util.spec_from_file_location(
    "audit_detector_under_test", _DETECTOR_PATH,
)
assert _spec is not None and _spec.loader is not None
audit_detector = importlib.util.module_from_spec(_spec)
# Register BEFORE exec — Python's dataclass machinery looks up the module
# in sys.modules while processing forward-ref annotations like
# `list[Finding]`. Without this the dataclass decorator raises
# AttributeError on '__dict__'.
sys.modules["audit_detector_under_test"] = audit_detector
_spec.loader.exec_module(audit_detector)

from triage import read_all_items  # noqa: E402

AuditReport = audit_detector.AuditReport
mirror_findings_to_triage = audit_detector.mirror_findings_to_triage


# Lightweight Finding stub matching the real dataclass surface we care about.
@dataclass
class _Finding:
    group: str
    check_id: str
    name: str
    severity: str  # HIGH | MEDIUM | LOW
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


# --- Fail finding → triage item ----------------------------------------

def test_single_fail_finding_emitted(project: Path) -> None:
    report = _report(_Finding(
        group="A", check_id="A2", name="RLS missing on x",
        severity="HIGH", detail="table public.tasks has no RLS",
        evidence=["supabase/migrations/0042.sql:14"],
    ))
    out = mirror_findings_to_triage(project, report, run_id="r1", commit="abc")
    assert out == {"appended": 1, "dismissed": 0}

    [item] = read_all_items(project)
    assert item["source"] == "compliance"
    assert item["severity"] == "high"
    assert item["kind"] == "compliance"
    assert item["dedupKey"] == "A2"
    assert item["suggestedPriority"] == "P1"     # high → P1
    assert item["suggestedDomain"] == "compliance"
    assert "RLS missing on x" in item["title"]
    assert "supabase/migrations/0042.sql:14" in item["detail"]
    assert item["runId"] == "r1"


def test_severity_map(project: Path) -> None:
    """HIGH→high, MEDIUM→medium, LOW→low."""
    report = _report(
        _Finding(group="A", check_id="A1", name="n", severity="HIGH"),
        _Finding(group="B", check_id="B1", name="n", severity="MEDIUM"),
        _Finding(group="C", check_id="C1", name="n", severity="LOW"),
    )
    mirror_findings_to_triage(project, report)
    by_key = {it["dedupKey"]: it for it in read_all_items(project)}
    assert by_key["A1"]["severity"] == "high"
    assert by_key["B1"]["severity"] == "medium"
    assert by_key["C1"]["severity"] == "low"


def test_pass_findings_not_emitted(project: Path) -> None:
    report = _report(
        _Finding(group="A", check_id="A1", name="n", severity="HIGH", status="pass"),
        _Finding(group="A", check_id="A2", name="n", severity="MEDIUM", status="skip"),
    )
    out = mirror_findings_to_triage(project, report)
    assert out["appended"] == 0
    assert read_all_items(project) == []


# --- Dedup across runs (match_commit=False) -----------------------------

def test_re_emit_dedups_across_commits(project: Path) -> None:
    """Same finding on a new commit → dedup'd (compliance dedup is
    cross-commit; the finding is the same issue)."""
    report = _report(_Finding(
        group="A", check_id="A2", name="n", severity="HIGH",
    ))
    mirror_findings_to_triage(project, report, commit="abc")
    mirror_findings_to_triage(project, report, commit="def")  # new commit
    items = read_all_items(project)
    keys = [it["dedupKey"] for it in items]
    assert keys.count("A2") == 1


# --- Auto-dismiss when finding disappears ------------------------------

def test_auto_dismiss_when_finding_resolved(project: Path) -> None:
    """A2 in run-1, not in run-2 → run-2 auto-dismisses A2 with
    reason=auditResolved."""
    report1 = _report(
        _Finding(group="A", check_id="A2", name="n", severity="HIGH"),
        _Finding(group="A", check_id="A3", name="n", severity="MEDIUM"),
    )
    mirror_findings_to_triage(project, report1)

    report2 = _report(
        _Finding(group="A", check_id="A3", name="n", severity="MEDIUM"),
    )
    out = mirror_findings_to_triage(project, report2)
    assert out["dismissed"] == 1

    by_key = {it["dedupKey"]: it for it in read_all_items(project)}
    assert by_key["A2"]["status"] == "dismissed"
    assert by_key["A2"]["statusReason"] == "auditResolved"
    assert by_key["A3"]["status"] == "triage"


def test_dismissed_items_stay_terminal(project: Path) -> None:
    """An item already dismissed by an operator stays dismissed; auto-dismiss
    doesn't double-fire and doesn't reopen on subsequent absence."""
    report1 = _report(_Finding(group="A", check_id="A2", name="n", severity="HIGH"))
    mirror_findings_to_triage(project, report1)

    # Operator dismisses manually
    [item] = read_all_items(project)
    from triage import mark_status
    mark_status(project, item["id"], new_status="dismissed", by="operator",
                reason="manual-known-fp")

    # New run: finding still absent
    report2 = _report()
    out = mirror_findings_to_triage(project, report2)
    # No new dismiss (item is already dismissed, not in triage state)
    assert out["dismissed"] == 0

    [item2] = read_all_items(project)
    assert item2["status"] == "dismissed"
    assert item2["statusReason"] == "manual-known-fp"  # not overwritten


def test_promoted_items_stay_terminal(project: Path) -> None:
    """A promoted item stays promoted even when the audit no longer fires."""
    report1 = _report(_Finding(group="A", check_id="A2", name="n", severity="HIGH"))
    mirror_findings_to_triage(project, report1)
    [item] = read_all_items(project)
    from triage import mark_status
    mark_status(project, item["id"], new_status="promoted", by="operator",
                promoted_task_id="EXT:linear-ENG-1", reason="manualPromote")

    report2 = _report()
    out = mirror_findings_to_triage(project, report2)
    assert out["dismissed"] == 0

    [item2] = read_all_items(project)
    assert item2["status"] == "promoted"
    assert item2["promotedTaskId"] == "EXT:linear-ENG-1"


# --- Other source items unaffected ------------------------------------

def test_other_source_items_not_auto_dismissed(project: Path) -> None:
    """Auto-dismiss only touches source=='compliance' items.
    Phase-Quality items remain in triage when compliance doesn't see them."""
    from triage import append_triage_item
    pq_id = append_triage_item(
        project, source="phaseQuality", severity="high", kind="bug",
        title="phase-quality finding", detail="d",
        dedup_key="iterate:C1",
    )

    report = _report()  # no compliance findings
    out = mirror_findings_to_triage(project, report)
    assert out["dismissed"] == 0

    items = {it["id"]: it for it in read_all_items(project)}
    assert items[pq_id]["status"] == "triage"


# --- Empty report (no findings) ---------------------------------------

def test_empty_report_no_op(project: Path) -> None:
    out = mirror_findings_to_triage(project, _report())
    assert out == {"appended": 0, "dismissed": 0}
    assert read_all_items(project) == []
