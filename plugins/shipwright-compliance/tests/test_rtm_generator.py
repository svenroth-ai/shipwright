"""Tests for rtm_generator.py."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from scripts.lib.data_collector import (
    ComplianceData, RequirementInfo, WorkEvent, collect_all,
)
from scripts.lib.rtm_generator import generate, generate_file


def _git(args: list[str], cwd: Path) -> None:
    """Run a git command in ``cwd``, raising on failure."""
    subprocess.run(
        ["git", *args], cwd=str(cwd), check=True, capture_output=True, text=True
    )


class TestGenerate:
    def test_produces_markdown(self, project_root: Path):
        data = collect_all(project_root)
        result = generate(data)
        assert "# Requirements Traceability Matrix" in result
        assert "## Section Traceability" in result
        assert "## Coverage Summary" in result

    def test_contains_section_data(self, project_root: Path):
        data = collect_all(project_root)
        result = generate(data)
        assert "01-login" in result
        assert "02-rbac" in result
        assert "03-profile" in result
        assert "abc123def456" in result  # commit hash

    def test_no_traceability_flow_diagram(self, project_root: Path):
        data = collect_all(project_root)
        result = generate(data)
        assert "## Traceability Flow" not in result
        assert "flowchart TD" not in result

    def test_summary_metrics(self, project_root: Path):
        data = collect_all(project_root)
        result = generate(data)
        assert "| Total splits | 3 |" in result
        assert "| Total sections | 3 |" in result
        assert "| Traceability coverage | 100% |" in result

    def test_empty_data(self, empty_project_root: Path):
        data = collect_all(empty_project_root)
        result = generate(data)
        assert "No sections available yet" in result

    def test_section_pass_status(self, project_root: Path):
        data = collect_all(project_root)
        result = generate(data)
        # Section traceability shows PASS for sections with green unit tests
        assert "PASS" in result

    def test_findings_in_summary(self, project_root: Path):
        data = collect_all(project_root)
        result = generate(data)
        # 03-profile has 2 findings (1 fixed, 1 deferred) -> totals in summary
        assert "| Total review findings | 3 |" in result
        assert "| Unresolved findings | 1 |" in result


def _make_data(tmp_path, *, baseline=0, tests_passed=830, tests_total=831):
    """Helper to build ComplianceData with one FR and one work event."""
    data = ComplianceData(project_root=tmp_path, timestamp="2026-04-06T00:00:00Z")
    data.baseline_failure_count = baseline
    we = WorkEvent(
        id="ev-1", timestamp="2026-04-06T10:00:00Z", source="iterate",
        description="Add feature", tests_passed=tests_passed, tests_total=tests_total,
        affected_frs=["FR-01.01"],
    )
    data.work_events = [we]
    data.requirements = [
        RequirementInfo(id="FR-01.01", text="Login works", priority="Must", split="01-auth"),
    ]
    return data


class TestKnownFailures:
    def test_baseline_failures_give_covered_baseline(self, tmp_path: Path):
        """FRs with failures <= baseline get COVERED (baseline) not FAIL."""
        data = _make_data(tmp_path, baseline=1, tests_passed=830, tests_total=831)
        result = generate(data)
        assert "COVERED (baseline)" in result
        assert "| FAIL |" not in result

    def test_failures_beyond_baseline_still_fail(self, tmp_path: Path):
        """FRs with failures > baseline still get FAIL."""
        data = _make_data(tmp_path, baseline=1, tests_passed=828, tests_total=831)
        result = generate(data)
        assert "FAIL" in result
        assert "COVERED (baseline)" not in result

    def test_no_known_failures_unchanged(self, tmp_path: Path):
        """Without known_failures, behavior is identical to current."""
        data = _make_data(tmp_path, baseline=0, tests_passed=830, tests_total=831)
        result = generate(data)
        assert "FAIL" in result
        assert "COVERED (baseline)" not in result

    def test_all_passing_ignores_baseline(self, tmp_path: Path):
        """When all tests pass, status is COVERED regardless of baseline."""
        data = _make_data(tmp_path, baseline=1, tests_passed=831, tests_total=831)
        result = generate(data)
        assert "COVERED" in result
        assert "baseline" not in result


class TestRtmAdoptedProjectWorktree:
    """F0.5 end-to-end: RTM generation from a git worktree of an adopted project.

    Reproduces both bugs together:
      * Bug A — the adopted spec uses a 6-column FR table.
      * Bug B — shipwright_events.jsonl is untracked, so a fresh worktree
        checkout does not carry it.
    Before the fixes, RTM generation from the worktree saw zero FRs and
    zero events, fell back to the legacy section-count path, and an adopted
    project (0 build sections) emitted "| Traceability coverage | 0% |" —
    which the check_rtm_coverage pre-commit hook soft-blocks. After the
    fixes the RTM shows real, event-sourced FR coverage.
    """

    SIX_COL_SPEC = (
        "# Specification - adopted\n\n"
        "## Functional Requirements\n\n"
        "| ID | Name | Priority | Description | Source | Confidence |\n"
        "|----|------|----------|-------------|--------|------------|\n"
        "| FR-01.01 | dashboard | Must | User views active projects. | src/app/dashboard/page.tsx | 0.82 |\n"
        "| FR-01.02 | login | Must | User authenticates via magic link. | src/app/login/page.tsx | 0.91 |\n"
        "| FR-01.03 | settings | Should | User edits profile preferences. | src/app/settings/page.tsx | 0.55 |\n"
    )

    def _build_adopted_project(self, root: Path) -> None:
        """Create a completed adopted project: 1 planning split, 0 build sections."""
        root.mkdir(parents=True, exist_ok=True)
        _git(["init"], root)
        _git(["config", "user.email", "test@example.com"], root)
        _git(["config", "user.name", "Test"], root)

        (root / "shipwright_run_config.json").write_text(
            json.dumps({"status": "complete", "profile": "supabase-nextjs"}),
            encoding="utf-8",
        )
        (root / "shipwright_project_config.json").write_text(
            json.dumps({"splits": [{"name": "01-adopted", "status": "complete"}]}),
            encoding="utf-8",
        )
        planning = root / ".shipwright" / "planning" / "01-adopted"
        planning.mkdir(parents=True)
        (planning / "spec.md").write_text(self.SIX_COL_SPEC, encoding="utf-8")

        # Tracked artifacts go into the commit so the worktree carries them.
        _git(["add", "-A"], root)
        _git(["commit", "-m", "adopt baseline"], root)

        # The event log is untracked (mirrors gitignored) and written AFTER
        # the commit — a fresh worktree must NOT receive it.
        events = [{
            "id": "evt-adopt-1", "type": "work_completed", "source": "iterate",
            "ts": "2026-05-15T10:00:00Z", "commit": "deadbeef",
            "affected_frs": ["FR-01.01", "FR-01.02", "FR-01.03"],
            "tests": {"passed": 12, "total": 12},
        }]
        (root / "shipwright_events.jsonl").write_text(
            "\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8"
        )

    def test_rtm_from_worktree_shows_real_coverage(self, tmp_path: Path):
        main = tmp_path / "adopted-main"
        self._build_adopted_project(main)

        worktree = tmp_path / "wt"
        _git(["worktree", "add", str(worktree)], main)
        # The worktree carries the committed spec but NOT the untracked log.
        assert (worktree / ".shipwright" / "planning" / "01-adopted" / "spec.md").exists()
        assert not (worktree / "shipwright_events.jsonl").exists()

        rtm_path = generate_file(worktree)
        rtm = rtm_path.read_text(encoding="utf-8")

        # Bug B regression guard: the legacy 0%-coverage path is NOT taken.
        assert "| Traceability coverage | 0% |" not in rtm
        # Bug A: all three 6-column FR rows surfaced.
        for fr in ("FR-01.01", "FR-01.02", "FR-01.03"):
            assert fr in rtm
        # Event-sourced coverage summary present with real counts.
        assert "| Requirements verified | 3/3 |" in rtm
        assert "COVERED" in rtm


class TestGenerateFile:
    def test_writes_file(self, project_root: Path):
        data = collect_all(project_root)
        path = generate_file(project_root, data)
        assert path.exists()
        assert path.name == "traceability-matrix.md"
        content = path.read_text(encoding="utf-8")
        assert "# Requirements Traceability Matrix" in content

    def test_creates_compliance_dir(self, tmp_path: Path):
        """If compliance/ doesn't exist, generate_file creates it."""
        root = tmp_path / "project"
        root.mkdir()
        data = ComplianceData(project_root=root)
        data.timestamp = "2026-03-21T14:00:00Z"
        path = generate_file(root, data)
        assert (root / ".shipwright" / "compliance").exists()
        assert path.exists()
