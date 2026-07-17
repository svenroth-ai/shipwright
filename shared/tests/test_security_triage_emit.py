"""AC-1 producer test: Security findings land in triage.jsonl.

Unit-tests the `_emit_findings_to_triage` helper in
``plugins/shipwright-security/scripts/tools/generate_security_report.py``.
End-to-end CLI behavior of the report generator is not in scope here —
this asserts the producer-side contract (one finding → one triage item,
dedup keys, severity mapping).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_WORKTREE = Path(__file__).resolve().parents[2]
_SHARED_SCRIPTS = _WORKTREE / "shared" / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

_REPORT_PATH = (
    _WORKTREE / "plugins" / "shipwright-security" / "scripts" / "tools"
    / "generate_security_report.py"
)
_spec = importlib.util.spec_from_file_location(
    "generate_security_report_for_test", _REPORT_PATH,
)
assert _spec is not None and _spec.loader is not None
sec_report = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sec_report)

from triage import read_all_items  # noqa: E402


@pytest.fixture
def project(tmp_path: Path) -> Path:
    return tmp_path


def _finding(
    *,
    source: str = "semgrep",
    severity: str = "high",
    rule: str = "py.lang.security.audit.dangerous-system-call",
    affected_file: str = "src/utils/runner.py",
    affected_line: int = 42,
    description: str = "subprocess invocation with shell=True",
) -> dict:
    return {
        "source": source,
        "severity": severity,
        "rule": rule,
        "affected_file": affected_file,
        "affected_line": affected_line,
        "description": description,
    }


@pytest.mark.covers("FR-01.14")
def test_one_finding_emits_one_triage_item(project: Path) -> None:
    appended = sec_report._emit_findings_to_triage(
        project, [_finding()], run_id="r1",
    )
    assert appended == 1
    [item] = read_all_items(project)
    assert item["source"] == "security"
    assert item["severity"] == "high"
    assert item["kind"] == "bug"
    assert item["suggestedPriority"] == "P1"
    assert item["suggestedDomain"] == "engineering"
    assert item["status"] == "triage"


@pytest.mark.covers("FR-01.14")
def test_dedup_key_includes_tool_check_file_line(project: Path) -> None:
    sec_report._emit_findings_to_triage(project, [_finding()], run_id="r1")
    [item] = read_all_items(project)
    assert item["dedupKey"] == (
        "semgrep:py.lang.security.audit.dangerous-system-call:"
        "src/utils/runner.py:42"
    )


@pytest.mark.covers("FR-01.14")
def test_kind_bug_for_critical_and_high(project: Path) -> None:
    sec_report._emit_findings_to_triage(
        project,
        [_finding(severity="critical", rule="CRIT"),
         _finding(severity="high", rule="HIGH")],
        run_id="r1",
    )
    items = {it["dedupKey"]: it for it in read_all_items(project)}
    assert all(it["kind"] == "bug" for it in items.values())


@pytest.mark.covers("FR-01.14")
def test_kind_improvement_for_medium_low_info(project: Path) -> None:
    sec_report._emit_findings_to_triage(
        project,
        [_finding(severity="medium", rule="MED"),
         _finding(severity="low", rule="LOW"),
         _finding(severity="info", rule="INFO")],
        run_id="r1",
    )
    items = {it["dedupKey"]: it for it in read_all_items(project)}
    for it in items.values():
        assert it["kind"] == "improvement"


@pytest.mark.covers("FR-01.14")
def test_unknown_severity_falls_back_to_medium(project: Path) -> None:
    """Conservative default — never raise into the consolidation path."""
    sec_report._emit_findings_to_triage(
        project, [_finding(severity="weird-unknown-value")], run_id="r1",
    )
    [item] = read_all_items(project)
    assert item["severity"] == "medium"
    assert item["kind"] == "improvement"


@pytest.mark.covers("FR-01.14")
def test_title_includes_tool_and_rule(project: Path) -> None:
    sec_report._emit_findings_to_triage(project, [_finding()], run_id="r1")
    [item] = read_all_items(project)
    assert "semgrep" in item["title"]
    assert "py.lang.security.audit.dangerous-system-call" in item["title"]


@pytest.mark.covers("FR-01.14")
def test_title_capped_at_160_chars(project: Path) -> None:
    long = _finding(description="x" * 500)
    sec_report._emit_findings_to_triage(project, [long], run_id="r1")
    [item] = read_all_items(project)
    assert len(item["title"]) <= 160


@pytest.mark.covers("FR-01.14")
def test_detail_includes_file_line_and_description(project: Path) -> None:
    sec_report._emit_findings_to_triage(project, [_finding()], run_id="r1")
    [item] = read_all_items(project)
    assert "src/utils/runner.py" in item["detail"]
    assert "42" in item["detail"]
    assert "subprocess invocation" in item["detail"]


@pytest.mark.covers("FR-01.14")
def test_same_finding_dedups_within_window(project: Path) -> None:
    sec_report._emit_findings_to_triage(project, [_finding()], run_id="r1")
    appended2 = sec_report._emit_findings_to_triage(
        project, [_finding()], run_id="r1",
    )
    assert appended2 == 0
    assert len(read_all_items(project)) == 1


@pytest.mark.covers("FR-01.14")
def test_empty_findings_no_op(project: Path) -> None:
    appended = sec_report._emit_findings_to_triage(project, [], run_id="r1")
    assert appended == 0
    assert read_all_items(project) == []


@pytest.mark.covers("FR-01.14")
def test_distinct_files_create_distinct_items(project: Path) -> None:
    sec_report._emit_findings_to_triage(
        project,
        [_finding(affected_file="a.py", affected_line=1),
         _finding(affected_file="b.py", affected_line=1)],
        run_id="r1",
    )
    keys = {it["dedupKey"] for it in read_all_items(project)}
    assert len(keys) == 2


@pytest.mark.covers("FR-01.14")
def test_malformed_finding_does_not_block_others(project: Path) -> None:
    """A finding missing required fields must NOT block subsequent findings.

    Best-effort contract: producer logs to stderr and continues.
    """
    malformed = {"description": "no severity, no rule, no file"}
    good = _finding(rule="Y1", affected_file="z.py", affected_line=99)
    sec_report._emit_findings_to_triage(
        project, [malformed, good], run_id="r1",
    )
    items = read_all_items(project)
    keys = {it["dedupKey"] for it in items}
    # The good finding must have landed even though the malformed one
    # was rejected. Producer never propagates per-item errors.
    assert any("Y1" in k for k in keys)
