"""iterate-2026-07-23-tests-skipped-tracking — compliance-side readers of the
work_completed ``tests.skipped`` field, kept in a focused sibling module so the
grandfathered ``test_test_evidence.py`` / ``test_audit_groups_a_d.py`` /
``test_data_collector.py`` are not ratcheted past their bloat baseline.

Covers three readers that must agree on the SAME present/absent predicate
(``isinstance(skipped, int)``): the test-evidence Test Progression renderer
(``_progression_result``), the D4 detective (``_failed_count``), and — for the
model side — ``WorkEvent.from_dict``.
"""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

from scripts.lib.data_collector import ComplianceData, RequirementInfo, WorkEvent
from scripts.lib.test_evidence import generate
from scripts.audit import group_d


# ---------------------------------------------------------------------------
# Renderer (_progression_result via generate)
# ---------------------------------------------------------------------------


def _render_data(tmp_path, *, baseline=0, passed=830, total=831, skipped=None):
    data = ComplianceData(project_root=tmp_path, timestamp="2026-04-06T00:00:00Z")
    data.baseline_failure_count = baseline
    data.work_events = [WorkEvent(
        id="ev-1", timestamp="2026-04-06T10:00:00Z", source="iterate",
        description="Add feature", tests_passed=passed, tests_total=total,
        tests_skipped=skipped, affected_frs=["FR-01.01"],
    )]
    data.requirements = [
        RequirementInfo(id="FR-01.01", text="Login works", priority="Must", split="01-auth"),
    ]
    return data


class TestExplicitSkipRender:
    """An EXPLICIT tests.skipped is rendered directly (surviving passed==total)
    and separates genuine failures from skips; legacy events keep the charitable
    rendering (pinned in test_test_evidence.py::TestSkipAwareResult)."""

    def test_disclosure_survives_when_passed_equals_total(self, tmp_path: Path):
        # Executed-totals recording — the gap-based renderer lost this; the
        # explicit count restores it (the exact information loss the request cites).
        result = generate(_render_data(tmp_path, passed=831, total=831, skipped=3))
        assert "PASS (3 skipped)" in result
        assert "| FAIL |" not in result

    def test_green_with_recorded_skips_and_gap(self, tmp_path: Path):
        result = generate(_render_data(tmp_path, passed=828, total=831, skipped=3))
        assert "PASS (3 skipped)" in result
        assert "FAIL" not in result

    def test_explicit_skip_residual_renders_fail(self, tmp_path: Path):
        # total - passed - skipped = 831-826-3 = 2 genuine failures.
        result = generate(_render_data(tmp_path, passed=826, total=831, skipped=3))
        assert "FAIL (2 failed, 3 skipped)" in result

    def test_explicit_residual_ignores_baseline_charity(self, tmp_path: Path):
        # An explicit residual is exact — the legacy baseline exemption must NOT
        # apply, or test-evidence renders PASS while D4 flags fail. residual=2,
        # baseline=2 → still FAIL.
        result = generate(_render_data(tmp_path, baseline=2, passed=826, total=831, skipped=3))
        assert "FAIL (2 failed, 3 skipped)" in result
        assert "PASS (baseline)" not in result

    def test_explicit_zero_skips_all_pass(self, tmp_path: Path):
        result = generate(_render_data(tmp_path, passed=831, total=831, skipped=0))
        assert "| PASS |" in result
        assert "skipped" not in result

    def test_non_int_skipped_renders_charitably_no_crash(self, tmp_path: Path):
        # A malformed (non-int) skipped — reachable only via a hand-built /
        # amendment payload — must NOT crash the renderer and must take the same
        # charitable path D4 uses (isinstance(int) predicate), NOT the arithmetic.
        result = generate(_render_data(tmp_path, passed=828, total=831, skipped="3"))
        assert "PASS (3 skipped)" in result  # gap-based charity, not total-passed-"3"
        assert "FAIL" not in result


# ---------------------------------------------------------------------------
# Model (WorkEvent.from_dict)
# ---------------------------------------------------------------------------


class TestWorkEventSkipped:
    """from_dict maps absent → None (not 0) — the present/absent distinction is
    load-bearing for the charitable-vs-exact reader split."""

    def _we(self, tests: dict) -> WorkEvent:
        return WorkEvent.from_dict({
            "id": "e", "type": "work_completed", "source": "iterate",
            "ts": "2026-07-23T00:00:00Z", "tests": tests,
        })

    def test_explicit_skipped_read(self):
        assert self._we({"passed": 828, "total": 831, "skipped": 3}).tests_skipped == 3

    def test_absent_skipped_is_none_not_zero(self):
        assert self._we({"passed": 10, "total": 10}).tests_skipped is None

    def test_explicit_zero_skipped_preserved(self):
        assert self._we({"passed": 10, "total": 10, "skipped": 0}).tests_skipped == 0


# ---------------------------------------------------------------------------
# Detective (D4 via group_d.run)
# ---------------------------------------------------------------------------


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content).lstrip("\n"), encoding="utf-8")


def _events(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def _spec_one_fr(path: Path) -> None:
    _write(path, "# Spec\n\n| FR | Description | Priority |\n"
                 "| --- | --- | --- |\n| FR-01.01 | x | Must |\n")


def _d4(tmp_path, tests: dict) -> str:
    _spec_one_fr(tmp_path / ".shipwright" / "planning" / "01-foo" / "spec.md")
    _events(tmp_path / "shipwright_events.jsonl", [
        {"type": "work_completed", "ts": "2026-04-01T00:00:00+00:00",
         "affected_frs": ["FR-01.01"], "tests": tests},
    ])
    findings = group_d.run(tmp_path, {"a4_path_fields": []}, None)
    return next(f for f in findings if f.check_id == "D4").status


class TestD4KeysOnFailures:
    """D4 flags an FR only when its latest covering event proves a genuine
    failure (total - passed - skipped > 0), charitable to a skip-count-less gap."""

    def test_charitable_when_gap_has_no_skip_count(self, tmp_path: Path):
        # Regression guard for the live FR-01.07 (4955/4967) false-positive that
        # had D4 disabled on this monorepo before this iterate.
        assert _d4(tmp_path, {"passed": 8, "total": 10}) == "pass"

    def test_green_run_with_recorded_skips(self, tmp_path: Path):
        assert _d4(tmp_path, {"passed": 8, "total": 10, "skipped": 2}) == "pass"

    def test_explicit_residual_flags(self, tmp_path: Path):
        assert _d4(tmp_path, {"passed": 6, "total": 10, "skipped": 2}) == "fail"

    def test_non_int_skipped_is_charitable(self, tmp_path: Path):
        # A malformed non-int skipped → _failed_count returns 0 (isinstance(int)),
        # matching the renderer — no divergence, no phantom failure.
        assert _d4(tmp_path, {"passed": 8, "total": 10, "skipped": "2"}) == "pass"
