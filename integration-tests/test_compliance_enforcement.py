"""Integration test: Compliance Enforcement Flow.

Tests that compliance hooks correctly integrate with the build pipeline:
  - RTM coverage hook blocks commits when coverage is below threshold
  - Security scan hook blocks deploys when findings are unresolved
  - Override logging works across the pipeline
  - Hooks are transparent when no compliance data exists (early pipeline)
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import (
    BUILD_PLUGIN,
    PLAN_PLUGIN,
    PROJECT_PLUGIN,
    REPO_ROOT,
    run_script,
)

COMPLIANCE_PLUGIN = REPO_ROOT / "plugins" / "shipwright-compliance"


def run_hook(hook_script: str, payload: dict, cwd: Path) -> tuple[int, dict | None]:
    """Run a compliance hook with JSON payload on stdin.

    Returns (exit_code, parsed_json_output_or_None).
    """
    result = subprocess.run(
        [sys.executable, str(COMPLIANCE_PLUGIN / "scripts" / "hooks" / hook_script)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        cwd=str(cwd),
    )
    output = None
    if result.stdout.strip():
        try:
            output = json.loads(result.stdout.strip())
        except json.JSONDecodeError:
            pass
    return result.returncode, output


def write_rtm(project_root: Path, coverage_pct: int, unresolved: int = 0):
    """Create a realistic traceability-matrix.md."""
    compliance_dir = project_root / ".shipwright" / "compliance"
    compliance_dir.mkdir(parents=True, exist_ok=True)

    lines = [
        "# Requirements Traceability Matrix",
        "",
        f"Generated: 2026-03-23T10:00:00Z",
        "",
        "## Matrix",
        "",
        "| Split | Section | Commit | Tests Passed | Tests Total | Review Findings | Status |",
        "|-------|---------|--------|-------------|-------------|-----------------|--------|",
        "| auth | 01-models | abc123 | 5 | 5 | 0 | PASS |",
        "| auth | 02-routes | def456 | 3 | 3 | 1 (1 fixed) | PASS |",
    ]

    if coverage_pct < 100:
        lines.append("| auth | 03-ui | — | 0 | 0 | 0 | PENDING |")

    if unresolved > 0:
        lines.append(f"| data | 01-schema | ghi789 | 2 | 4 | {unresolved} ({unresolved} deferred) | FAIL |")

    lines.extend([
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Traceability coverage | {coverage_pct}% |",
        f"| Unresolved findings | {unresolved} |",
    ])

    (compliance_dir / "traceability-matrix.md").write_text(
        "\n".join(lines), encoding="utf-8"
    )


class TestComplianceEnforcementInPipeline:
    """Test compliance hooks in the context of a build pipeline."""

    def test_hooks_transparent_early_pipeline(self, trilogy_project):
        """Before any compliance data exists, hooks allow everything."""
        # No compliance/ directory exists yet — hooks should pass through
        commit_payload = {"tool_input": {"command": "git commit -m 'feat: initial'"}}
        deploy_payload = {"tool_input": {"command": "deploy to jelastic"}}

        rc1, _ = run_hook("check_rtm_coverage.py", commit_payload, trilogy_project)
        rc2, _ = run_hook("check_security_scan.py", deploy_payload, trilogy_project)

        assert rc1 == 0, "RTM hook should allow when no compliance data"
        assert rc2 == 0, "Security hook should allow when no compliance data"

    def test_rtm_hook_blocks_commit_after_build(self, trilogy_project):
        """After build with low coverage, commit should be soft-blocked."""
        # Simulate: project + plan done, build partially done (62% coverage)
        write_rtm(trilogy_project, coverage_pct=62)

        rc, output = run_hook(
            "check_rtm_coverage.py",
            {"tool_input": {"command": "git commit -m 'feat: add auth'"}},
            trilogy_project,
        )

        assert rc == 2, "Should soft-block at 62% coverage"
        assert output is not None
        assert output["hookSpecificOutput"]["blocked"] is True
        assert "62%" in output["hookSpecificOutput"]["reason"]
        assert "Continue anyway" in output["hookSpecificOutput"]["additionalContext"]

    def test_rtm_hook_allows_commit_when_coverage_ok(self, trilogy_project):
        """After build with good coverage, commit should be allowed."""
        write_rtm(trilogy_project, coverage_pct=85)

        rc, _ = run_hook(
            "check_rtm_coverage.py",
            {"tool_input": {"command": "git commit -m 'feat: complete auth'"}},
            trilogy_project,
        )

        assert rc == 0, "Should allow at 85% coverage"

    def test_security_hook_blocks_deploy_with_findings(self, trilogy_project):
        """Deploy should be blocked when unresolved findings exist."""
        write_rtm(trilogy_project, coverage_pct=80, unresolved=3)

        rc, output = run_hook(
            "check_security_scan.py",
            {"tool_input": {"command": "deploy to jelastic"}},
            trilogy_project,
        )

        assert rc == 2, "Should soft-block deploy with 3 unresolved findings"
        assert output["hookSpecificOutput"]["blocked"] is True
        assert "3 unresolved" in output["hookSpecificOutput"]["reason"]

    def test_security_hook_allows_deploy_when_clean(self, trilogy_project):
        """Deploy should be allowed when no unresolved findings."""
        write_rtm(trilogy_project, coverage_pct=100, unresolved=0)

        rc, _ = run_hook(
            "check_security_scan.py",
            {"tool_input": {"command": "deploy to jelastic"}},
            trilogy_project,
        )

        assert rc == 0, "Should allow deploy with 0 unresolved findings"

    def test_custom_thresholds_from_config(self, trilogy_project):
        """Project-level config can lower the enforcement thresholds."""
        write_rtm(trilogy_project, coverage_pct=62)

        # Set a lower threshold
        config = {"enforcement": {"rtm_coverage_min": 0.50}}
        (trilogy_project / "shipwright_compliance_config.json").write_text(
            json.dumps(config), encoding="utf-8"
        )

        rc, _ = run_hook(
            "check_rtm_coverage.py",
            {"tool_input": {"command": "git commit -m 'feat: partial'"}},
            trilogy_project,
        )

        assert rc == 0, "62% should be allowed with 50% threshold"

    def test_hooks_ignore_non_matching_commands(self, trilogy_project):
        """Hooks should only trigger on specific command patterns."""
        write_rtm(trilogy_project, coverage_pct=30, unresolved=10)

        # RTM hook should not trigger on non-commit commands
        rc1, _ = run_hook(
            "check_rtm_coverage.py",
            {"tool_input": {"command": "npm test"}},
            trilogy_project,
        )
        assert rc1 == 0

        # Security hook should not trigger on non-deploy commands
        rc2, _ = run_hook(
            "check_security_scan.py",
            {"tool_input": {"command": "git push origin main"}},
            trilogy_project,
        )
        assert rc2 == 0

    def test_override_logging_integration(self, trilogy_project):
        """Override logger creates entries that can be read back.

        Imported via file-spec rather than ``from lib.override_logger import ...``
        because two ``lib/`` packages co-exist in this repo
        (``shared/scripts/lib/`` and ``plugins/shipwright-compliance/scripts/lib/``).
        Once any earlier test has imported from ``shared/scripts/lib/`` (e.g.
        ``lib.artifact_migrations`` from the integration negative-assertions),
        ``sys.modules['lib']`` is cached as the shared package and the
        ``sys.path.insert`` trick below cannot redirect a subsequent
        ``from lib.X import Y`` -- Python won't re-resolve a cached package.
        """
        import importlib.util

        override_logger_path = (
            COMPLIANCE_PLUGIN / "scripts" / "lib" / "override_logger.py"
        )
        spec = importlib.util.spec_from_file_location(
            "_compliance_override_logger_under_test", override_logger_path
        )
        override_logger = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(override_logger)
        log_override = override_logger.log_override
        read_overrides = override_logger.read_overrides

        # Simulate: hook blocked, user overrides
        log_override(
            trilogy_project,
            hook_name="check_rtm_coverage",
            reason="User confirmed: coverage will be completed in next section",
            details={"coverage_pct": 62, "threshold_pct": 80},
        )

        # Later: another override for security
        log_override(
            trilogy_project,
            hook_name="check_security_scan",
            reason="User confirmed: deploying to dev only, not prod",
            details={"unresolved_findings": 2},
        )

        entries = read_overrides(trilogy_project)
        assert len(entries) == 2
        assert "check_rtm_coverage" in entries[0]
        assert "check_security_scan" in entries[1]

        # Verify log file is in agent_docs
        log_path = trilogy_project / ".shipwright" / "agent_docs" / "compliance_overrides.log"
        assert log_path.exists()


class TestStructuredErrorsInPipeline:
    """SubagentStop hooks halt the run via top-level `decision: "block"`.

    Pre-ADR-042 these tests asserted on stdout `hookSpecificOutput.additionalContext`
    + `structuredError`. The Claude Code SubagentStop schema does not permit
    those fields, so the hook now emits a top-level decision payload (which
    DOES halt the subagent run) and writes the structured detail to stderr
    for the operator.
    """

    def test_write_section_on_stop_invalid_payload(self):
        """Invalid stdin payload halts the subagent via decision:block."""
        result = subprocess.run(
            [sys.executable, str(PLAN_PLUGIN / "scripts" / "hooks" / "write-section-on-stop.py")],
            input="not valid json",
            capture_output=True,
            text=True,
        )
        # Should not crash (exit 0) but output a SubagentStop-valid block.
        assert result.returncode == 0
        output = json.loads(result.stdout)
        assert output.get("decision") == "block"
        assert "Parse hook stdin payload" in output.get("reason", "")
        # Structured detail surfaces on stderr (post-ADR-042).
        assert "ERROR [validation]" in result.stderr
        assert "Parse hook stdin payload" in result.stderr
        assert '"error_category": "validation"' in result.stderr

    def test_write_section_on_stop_missing_transcript(self):
        """Missing transcript halts the subagent via decision:block; structured
        detail on stderr."""
        payload = {"transcript_path": "/nonexistent/path/transcript.jsonl"}
        result = subprocess.run(
            [sys.executable, str(PLAN_PLUGIN / "scripts" / "hooks" / "write-section-on-stop.py")],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        output = json.loads(result.stdout)
        assert output.get("decision") == "block"
        # Stderr carries the structured-detail blob.
        assert '"error_category": "transient"' in result.stderr
        assert '"is_retryable": true' in result.stderr
