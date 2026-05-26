"""Tests for compliance enforcement hooks.

Tests the PreToolUse hooks that soft-block commits and deploys
when compliance thresholds are not met.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

# Hook scripts are standalone (no imports needed), we test via subprocess
HOOKS_DIR = Path(__file__).parent.parent / "scripts" / "hooks"
LIB_DIR = Path(__file__).parent.parent / "scripts" / "lib"

# Import lib modules directly for unit testing.
# A sibling test (test_collectors_dashboard.py, alphabetically earlier) loads
# `shared/scripts/lib/phase_quality/`, which transitively caches `lib.*`
# entries in sys.modules pointing at the SHARED lib (no `thresholds.py`).
# Clear those so the `from lib.thresholds` below resolves through our own
# `plugins/shipwright-compliance/scripts/lib/`.
for _stale in [k for k in list(sys.modules) if k == "lib" or k.startswith("lib.")]:
    del sys.modules[_stale]
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from lib.thresholds import EnforcementThresholds, load_thresholds  # noqa: E402
from lib.override_logger import log_override, read_overrides  # noqa: E402


# ---------------------------------------------------------------------------
# Thresholds tests
# ---------------------------------------------------------------------------

class TestThresholds:
    def test_defaults(self):
        t = EnforcementThresholds()
        assert t.rtm_coverage_min == 0.80
        assert t.allowed_critical_findings == 0
        assert t.sbom_completeness_min == 0.90

    def test_load_from_config(self, tmp_path: Path):
        config = {
            "enforcement": {
                "rtm_coverage_min": 0.70,
                "allowed_critical_findings": 2,
                "sbom_completeness_min": 0.85,
            }
        }
        (tmp_path / "shipwright_compliance_config.json").write_text(
            json.dumps(config), encoding="utf-8"
        )
        t = load_thresholds(tmp_path)
        assert t.rtm_coverage_min == 0.70
        assert t.allowed_critical_findings == 2
        assert t.sbom_completeness_min == 0.85

    def test_load_missing_config(self, tmp_path: Path):
        t = load_thresholds(tmp_path)
        assert t.rtm_coverage_min == 0.80  # default

    def test_load_corrupt_config(self, tmp_path: Path):
        (tmp_path / "shipwright_compliance_config.json").write_text(
            "not json", encoding="utf-8"
        )
        t = load_thresholds(tmp_path)
        assert t.rtm_coverage_min == 0.80  # default

    def test_load_partial_enforcement(self, tmp_path: Path):
        config = {"enforcement": {"rtm_coverage_min": 0.50}}
        (tmp_path / "shipwright_compliance_config.json").write_text(
            json.dumps(config), encoding="utf-8"
        )
        t = load_thresholds(tmp_path)
        assert t.rtm_coverage_min == 0.50
        assert t.allowed_critical_findings == 0  # default


# ---------------------------------------------------------------------------
# Override logger tests
# ---------------------------------------------------------------------------

class TestOverrideLogger:
    def test_log_override_creates_file(self, tmp_path: Path):
        path = log_override(tmp_path, "check_rtm_coverage", "User confirmed continue")
        assert path.exists()
        content = path.read_text(encoding="utf-8")
        assert "OVERRIDE" in content
        assert "check_rtm_coverage" in content
        assert "User confirmed continue" in content

    def test_log_override_appends(self, tmp_path: Path):
        log_override(tmp_path, "hook_a", "reason_a")
        log_override(tmp_path, "hook_b", "reason_b")
        entries = read_overrides(tmp_path)
        assert len(entries) == 2
        assert "hook_a" in entries[0]
        assert "hook_b" in entries[1]

    def test_log_override_with_details(self, tmp_path: Path):
        log_override(tmp_path, "check_rtm", "override", details={"coverage": 0.62})
        entries = read_overrides(tmp_path)
        assert '"coverage": 0.62' in entries[0]

    def test_read_overrides_empty(self, tmp_path: Path):
        assert read_overrides(tmp_path) == []


# ---------------------------------------------------------------------------
# RTM coverage hook tests (via subprocess)
# ---------------------------------------------------------------------------

def _make_rtm(project_root: Path, coverage_pct: int, unresolved: int = 0) -> None:
    """Create a minimal traceability-matrix.md with given coverage."""
    compliance_dir = project_root / ".shipwright" / "compliance"
    compliance_dir.mkdir(parents=True, exist_ok=True)

    # Build a minimal RTM with summary table
    lines = [
        "# Requirements Traceability Matrix",
        "",
        "## Matrix",
        "",
        "| Split | Section | Commit | Tests Passed | Tests Total | Review Findings | Status |",
        "|-------|---------|--------|-------------|-------------|-----------------|--------|",
    ]
    if coverage_pct < 100:
        lines.append("| auth | 01-login | — | 0 | 0 | 0 | PENDING |")
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


def _run_hook(hook_script: str, payload: dict, cwd: str | Path) -> tuple[int, str]:
    """Run a hook script with JSON payload on stdin."""
    result = subprocess.run(
        [sys.executable, str(HOOKS_DIR / hook_script)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        cwd=str(cwd),
    )
    return result.returncode, result.stdout.strip()


class TestCheckRtmCoverage:
    def test_allows_non_commit_command(self, tmp_path: Path):
        _make_rtm(tmp_path, 50)
        rc, _ = _run_hook(
            "check_rtm_coverage.py",
            {"tool_input": {"command": "ls -la"}},
            tmp_path,
        )
        assert rc == 0

    def test_allows_when_no_rtm(self, tmp_path: Path):
        rc, _ = _run_hook(
            "check_rtm_coverage.py",
            {"tool_input": {"command": "git commit -m 'test'"}},
            tmp_path,
        )
        assert rc == 0

    def test_allows_when_coverage_sufficient(self, tmp_path: Path):
        _make_rtm(tmp_path, 85)
        rc, _ = _run_hook(
            "check_rtm_coverage.py",
            {"tool_input": {"command": "git commit -m 'feat: add auth'"}},
            tmp_path,
        )
        assert rc == 0

    def test_blocks_when_coverage_low(self, tmp_path: Path):
        _make_rtm(tmp_path, 62)
        rc, output = _run_hook(
            "check_rtm_coverage.py",
            {"tool_input": {"command": "git commit -m 'feat: add auth'"}},
            tmp_path,
        )
        assert rc == 2
        data = json.loads(output)
        assert data["hookSpecificOutput"]["blocked"] is True
        assert "62%" in data["hookSpecificOutput"]["reason"]
        assert "Continue anyway" in data["hookSpecificOutput"]["additionalContext"]

    def test_respects_custom_threshold(self, tmp_path: Path):
        _make_rtm(tmp_path, 62)
        config = {"enforcement": {"rtm_coverage_min": 0.50}}
        (tmp_path / "shipwright_compliance_config.json").write_text(
            json.dumps(config), encoding="utf-8"
        )
        rc, _ = _run_hook(
            "check_rtm_coverage.py",
            {"tool_input": {"command": "git commit -m 'test'"}},
            tmp_path,
        )
        assert rc == 0  # 62% > 50% threshold

    def test_allows_invalid_stdin(self, tmp_path: Path):
        """Hook should not crash on bad input."""
        result = subprocess.run(
            [sys.executable, str(HOOKS_DIR / "check_rtm_coverage.py")],
            input="not json",
            capture_output=True,
            text=True,
            cwd=str(tmp_path),
        )
        assert result.returncode == 0


class TestCheckSecurityScan:
    def test_allows_non_deploy_command(self, tmp_path: Path):
        _make_rtm(tmp_path, 80, unresolved=5)
        rc, _ = _run_hook(
            "check_security_scan.py",
            {"tool_input": {"command": "npm test"}},
            tmp_path,
        )
        assert rc == 0

    def test_allows_when_no_findings(self, tmp_path: Path):
        _make_rtm(tmp_path, 80, unresolved=0)
        rc, _ = _run_hook(
            "check_security_scan.py",
            {"tool_input": {"command": "deploy to jelastic"}},
            tmp_path,
        )
        assert rc == 0

    def test_blocks_deploy_with_findings(self, tmp_path: Path):
        _make_rtm(tmp_path, 80, unresolved=3)
        rc, output = _run_hook(
            "check_security_scan.py",
            {"tool_input": {"command": "deploy to jelastic"}},
            tmp_path,
        )
        assert rc == 2
        data = json.loads(output)
        assert data["hookSpecificOutput"]["blocked"] is True
        assert "3 unresolved" in data["hookSpecificOutput"]["reason"]

    def test_allows_when_no_rtm(self, tmp_path: Path):
        rc, _ = _run_hook(
            "check_security_scan.py",
            {"tool_input": {"command": "vercel deploy"}},
            tmp_path,
        )
        assert rc == 0

    def test_respects_custom_threshold(self, tmp_path: Path):
        _make_rtm(tmp_path, 80, unresolved=2)
        config = {"enforcement": {"allowed_critical_findings": 3}}
        (tmp_path / "shipwright_compliance_config.json").write_text(
            json.dumps(config), encoding="utf-8"
        )
        rc, _ = _run_hook(
            "check_security_scan.py",
            {"tool_input": {"command": "deploy to jelastic"}},
            tmp_path,
        )
        assert rc == 0  # 2 <= 3 allowed
