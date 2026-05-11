"""AC-4 producer test: Phase-Quality Tier-1 FAILs land in triage.jsonl.

Unit-test the `_emit_tier1_fails_to_triage` helper directly. End-to-end
schema compliance for the hook itself is covered by
`test_hook_output_schema_compliance.py` (auto-discovers the hook).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_WORKTREE = Path(__file__).resolve().parents[2]
_SHARED_SCRIPTS = _WORKTREE / "shared" / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

# Import the producer function from the hook module.
import importlib.util

_HOOK_PATH = _SHARED_SCRIPTS / "hooks" / "audit_phase_quality_on_stop.py"
_spec = importlib.util.spec_from_file_location(
    "audit_phase_quality_on_stop", _HOOK_PATH,
)
assert _spec is not None and _spec.loader is not None
audit_hook = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(audit_hook)

from triage import mark_status, read_all_items  # noqa: E402


@pytest.fixture
def project(tmp_path: Path) -> Path:
    return tmp_path


def _make_finding(code: str, status: str = "FAIL", *, tier: int | None = None,
                   name: str | None = None, evidence: str = "evidence text",
                   remediation: str = "do the thing") -> dict:
    f = {
        "id": code,
        "name": name or f"{code} check",
        "status": status,
        "evidence": evidence,
        "remediation": remediation,
    }
    if tier is not None:
        f["tier"] = tier
    return f


# --- Tier-1 FAIL → triage item ------------------------------------------

def test_tier1_fail_appended_with_high_severity(project: Path) -> None:
    findings = {
        "canon": [_make_finding("C1"), _make_finding("C5")],
    }
    appended = audit_hook._emit_tier1_fails_to_triage(
        project, phase="iterate", run_id="run-1",
        findings=findings, finding_path=None,
    )
    assert appended == 2

    items = read_all_items(project)
    assert len(items) == 2
    by_code = {it["dedupKey"]: it for it in items}
    assert "iterate:C1" in by_code
    assert "iterate:C5" in by_code
    for it in items:
        assert it["source"] == "phaseQuality"
        assert it["severity"] == "high"
        assert it["kind"] == "bug"
        assert it["suggestedPriority"] == "P1"
        assert it["suggestedDomain"] == "engineering"
        assert it["status"] == "triage"
        assert it["runId"] == "run-1"


def test_pass_findings_skipped(project: Path) -> None:
    findings = {
        "canon": [
            _make_finding("C1", status="PASS"),
            _make_finding("C5", status="WARN"),
            _make_finding("C2", status="SKIP"),
        ],
    }
    appended = audit_hook._emit_tier1_fails_to_triage(
        project, phase="iterate", run_id="run-1",
        findings=findings, finding_path=None,
    )
    assert appended == 0
    assert read_all_items(project) == []


def test_tier2_fails_excluded(project: Path) -> None:
    """Tier-2 = heuristic; not appended to triage."""
    findings = {
        "workflow": [
            _make_finding("C1"),                  # Tier-1
            _make_finding("W1", tier=2),          # Tier-2
            _make_finding("I4", tier=2),          # Tier-2
        ],
    }
    appended = audit_hook._emit_tier1_fails_to_triage(
        project, phase="iterate", run_id="run-1",
        findings=findings, finding_path=None,
    )
    assert appended == 1
    items = read_all_items(project)
    assert len(items) == 1
    assert items[0]["dedupKey"] == "iterate:C1"


# --- Dedup behavior -----------------------------------------------------

def test_same_run_dedups(project: Path) -> None:
    """Same finding + same commit, run twice → only one item."""
    findings = {"canon": [_make_finding("C1")]}
    audit_hook._emit_tier1_fails_to_triage(
        project, phase="iterate", run_id="run-1",
        findings=findings, finding_path=None,
    )
    appended2 = audit_hook._emit_tier1_fails_to_triage(
        project, phase="iterate", run_id="run-1",
        findings=findings, finding_path=None,
    )
    assert appended2 == 0
    items = read_all_items(project)
    assert len(items) == 1


def test_different_phase_creates_distinct_items(project: Path) -> None:
    """C1 in `iterate` vs C1 in `build` are different inbox items."""
    findings = {"canon": [_make_finding("C1")]}
    audit_hook._emit_tier1_fails_to_triage(
        project, phase="iterate", run_id="r1",
        findings=findings, finding_path=None,
    )
    audit_hook._emit_tier1_fails_to_triage(
        project, phase="build", run_id="r1",
        findings=findings, finding_path=None,
    )
    items = read_all_items(project)
    keys = {it["dedupKey"] for it in items}
    assert keys == {"iterate:C1", "build:C1"}


def test_dismissed_finding_can_re_fire(project: Path) -> None:
    """After dismiss, the next FAIL re-creates a new triage item.

    Matches the spec: dedup applies only against status=='triage' items;
    operators who dismiss a finding accept that future occurrences will
    re-fire (otherwise dismiss would silently suppress legit recurrence).
    """
    findings = {"canon": [_make_finding("C1")]}
    audit_hook._emit_tier1_fails_to_triage(
        project, phase="iterate", run_id="r1",
        findings=findings, finding_path=None,
    )
    [first] = read_all_items(project)
    mark_status(project, first["id"], new_status="dismissed", by="user",
                reason="known-not-actionable")

    audit_hook._emit_tier1_fails_to_triage(
        project, phase="iterate", run_id="r2",
        findings=findings, finding_path=None,
    )
    items = read_all_items(project)
    assert len(items) == 2


# --- Title + detail composition ----------------------------------------

def test_title_includes_phase_and_code(project: Path) -> None:
    findings = {
        "canon": [_make_finding("C1", name="C1 phase event recorded")],
    }
    audit_hook._emit_tier1_fails_to_triage(
        project, phase="iterate", run_id="r1",
        findings=findings, finding_path=None,
    )
    [item] = read_all_items(project)
    assert "iterate" in item["title"]
    assert "C1" in item["title"]


def test_evidence_path_recorded(project: Path) -> None:
    """When finding_path is provided, evidencePath is recorded relative."""
    findings = {"canon": [_make_finding("C1")]}
    evidence_file = project / ".shipwright" / "compliance" / "phase-quality-r1.json"
    evidence_file.parent.mkdir(parents=True, exist_ok=True)
    evidence_file.write_text("{}", encoding="utf-8")

    audit_hook._emit_tier1_fails_to_triage(
        project, phase="iterate", run_id="r1",
        findings=findings, finding_path=evidence_file,
    )
    [item] = read_all_items(project)
    assert item["evidencePath"] is not None
    assert "compliance" in item["evidencePath"]


def test_empty_findings_no_op(project: Path) -> None:
    appended = audit_hook._emit_tier1_fails_to_triage(
        project, phase="iterate", run_id="r1",
        findings={}, finding_path=None,
    )
    assert appended == 0
    assert read_all_items(project) == []


def test_arbitrary_tier1_code_emitted(project: Path) -> None:
    """Spec policy is 'all Tier-1 FAIL', not a fixed C1/C5/W3 allow-list
    (MED-2/MED-7 from code review — clarifies the policy is rule-based).

    A NEW Tier-1 code (e.g. "X9", "T1") that didn't exist when the spec
    was written must still emit. Otherwise the spec is brittle to
    future Phase-Quality additions.
    """
    findings = {
        "traceability": [
            _make_finding("T1", name="T1 traceability gap"),
            _make_finding("X9", name="X9 hypothetical future check"),
        ],
    }
    appended = audit_hook._emit_tier1_fails_to_triage(
        project, phase="iterate", run_id="r1",
        findings=findings, finding_path=None,
    )
    assert appended == 2
    keys = {it["dedupKey"] for it in read_all_items(project)}
    assert keys == {"iterate:T1", "iterate:X9"}


def test_empty_commit_fallback_emits(project: Path) -> None:
    """`_git_head_sha` returns "" on git failure; downstream
    append_triage_item_idempotent must accept the empty-string commit
    without raising (MED-3 from code review).
    """
    # Call the helper directly with commit="" (the documented fallback)
    from triage import append_triage_item_idempotent
    item_id = append_triage_item_idempotent(
        project,
        source="phaseQuality", severity="high", kind="bug",
        title="finding without git", detail="d",
        dedup_key="iterate:C1", commit="",
    )
    assert item_id is not None
    [item] = read_all_items(project)
    assert item["commit"] == ""
    assert item["dedupKey"] == "iterate:C1"
