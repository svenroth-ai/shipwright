"""Integration test: the deploy gate gates on SECURITY, not on review findings.

`cross_component` integration coverage for iterate-2026-07-28-hygiene-sweep
(AC-5 / trg-17f53a39). The unit tests in
``plugins/shipwright-compliance/tests/test_enforcement_hooks.py`` pin each branch
of the gate in isolation; this module proves the pieces *compose* on a real
project tree — the PreToolUse hook, ``resolve_project_root``, the compliance
config, and the two compliance artifacts that used to be confused for each other.

The defect this closes: ``check_security_scan`` soft-blocked deploys while the
RTM row ``| Unresolved findings | N |`` exceeded ``allowed_critical_findings``.
That row is ``sum(review.findings - review.fixed)`` over ``work_completed``
events — code-review findings. On 2026-07-28 the monorepo carried RTM 24
unresolved beside ``critical_gate=pass`` / ``by_severity.critical=0``: every
deploy was blocked, and the message named security. The two artifacts must now
be read independently, and only the security one may gate.
"""

import json
import subprocess
import sys
from pathlib import Path

from conftest import REPO_ROOT

COMPLIANCE_PLUGIN = REPO_ROOT / "plugins" / "shipwright-compliance"
DEPLOY = {"tool_input": {"command": "deploy to jelastic"}}


def _run_gate(cwd: Path) -> tuple[int, dict | None]:
    result = subprocess.run(
        [sys.executable,
         str(COMPLIANCE_PLUGIN / "scripts" / "hooks" / "check_security_scan.py")],
        input=json.dumps(DEPLOY), capture_output=True, text=True, cwd=str(cwd),
    )
    out = None
    if result.stdout.strip():
        try:
            out = json.loads(result.stdout.strip())
        except json.JSONDecodeError:
            pass
    return result.returncode, out


def _compliance_dir(project_root: Path) -> Path:
    d = project_root / ".shipwright" / "compliance"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _write_scan(project_root: Path, *, critical: int, degraded: bool = False) -> None:
    """The producer's shape — ci_security.summarize_ci_security."""
    (_compliance_dir(project_root) / "ci-security.json").write_text(json.dumps({
        "schema": 1, "scan_date": "2026-07-28T07:51:37Z", "source": "security.yml#1",
        "by_severity": {"critical": critical, "high": 2, "medium": 1, "low": 0},
        "total": critical + 3, "open_high_critical": critical + 2,
        "critical_gate": "fail" if critical > 0 else "pass",
        "prompt_injection": 0, "degraded": degraded,
    }, indent=2, sort_keys=True), encoding="utf-8")


def _write_rtm_review_findings(project_root: Path, unresolved: int) -> None:
    """Only the row the gate used to read — nothing else matters here."""
    (_compliance_dir(project_root) / "traceability-matrix.md").write_text(
        "# Requirements Traceability Matrix\n\n## Summary\n\n"
        "| Metric | Value |\n|--------|-------|\n"
        f"| Total review findings | 66 |\n| Unresolved findings | {unresolved} |\n",
        encoding="utf-8",
    )


class TestTheTwoArtifactsAreIndependent:
    def test_the_exact_state_of_the_monorepo_on_2026_07_28(self, trilogy_project):
        """24 unresolved review findings + a clean scan → deploy proceeds."""
        _write_rtm_review_findings(trilogy_project, 24)
        _write_scan(trilogy_project, critical=0)
        assert _run_gate(trilogy_project)[0] == 0

    def test_a_clean_rtm_does_not_excuse_a_dirty_scan(self, trilogy_project):
        """The inverse false-green: zero review findings must not let open
        criticals through. Before the change this pairing DEPLOYED."""
        _write_rtm_review_findings(trilogy_project, 0)
        _write_scan(trilogy_project, critical=2)
        rc, out = _run_gate(trilogy_project)
        assert rc == 2
        assert "2 open critical" in out["hookSpecificOutput"]["reason"]

    def test_the_block_message_names_the_scan_not_the_rtm(self, trilogy_project):
        """An operator must be able to act on the message. It has to point at
        the security artifact and its scan date, not at a review counter."""
        _write_rtm_review_findings(trilogy_project, 24)
        _write_scan(trilogy_project, critical=1)
        _rc, out = _run_gate(trilogy_project)
        details = out["hookSpecificOutput"]["details"]
        assert details["summary_path"] == ".shipwright/compliance/ci-security.json"
        assert details["scan_date"] == "2026-07-28T07:51:37Z"
        assert details["critical_findings"] == 1
        assert "unresolved_findings" not in details


class TestDegradedAndBrokenArtifacts:
    def test_a_degraded_scan_blocks_even_with_zero_findings(self, trilogy_project):
        """A leg that fataled returns [] — green by absence, not by evidence
        (project_scanner_degraded_marker)."""
        _write_scan(trilogy_project, critical=0, degraded=True)
        rc, out = _run_gate(trilogy_project)
        assert rc == 2
        assert "degraded" in out["hookSpecificOutput"]["reason"]

    def test_a_truncated_artifact_blocks(self, trilogy_project):
        """External review (OpenAI #1, Gemini #1): present-but-unusable is a
        failed scan, not a clean one. Fails CLOSED."""
        (_compliance_dir(trilogy_project) / "ci-security.json").write_text(
            '{"schema": 1, "by_sever', encoding="utf-8")
        rc, out = _run_gate(trilogy_project)
        assert rc == 2
        assert "unreadable or malformed" in out["hookSpecificOutput"]["reason"]

    def test_never_scanned_still_allows(self, trilogy_project):
        """A repo that was never scanned (fresh adopt) must not be bricked —
        this is the one state that legitimately fails open."""
        assert _run_gate(trilogy_project)[0] == 0


class TestOperatorThreshold:
    def test_a_configured_tolerance_is_honoured_end_to_end(self, trilogy_project):
        (trilogy_project / "shipwright_compliance_config.json").write_text(
            json.dumps({"enforcement": {"allowed_critical_findings": 2}}),
            encoding="utf-8")
        _write_scan(trilogy_project, critical=2)
        assert _run_gate(trilogy_project)[0] == 0, "at threshold → allow"
        _write_scan(trilogy_project, critical=3)
        assert _run_gate(trilogy_project)[0] == 2, "above threshold → block"
