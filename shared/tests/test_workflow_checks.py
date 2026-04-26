"""Tests for the Phase-Quality workflow category (PR 2 — W1-W7, Sec1-Sec2, Cmp1-Cmp2, D1-D2).

Covers each check with a positive and negative fixture plus the plan § 7
risks relevant to this PR:

- R8 — W1 (TDD order) must SKIP, never FAIL, when evidence is unreliable
- R9 — marker-based checks (W2, W5) carry ``provenance: unverified_marker``
- R10 — dispatcher is resilient to broken wrappers (never blocks Stop)
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

import pytest

_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from lib import phase_quality as pq  # noqa: E402
from tools.verifiers import (  # noqa: E402
    build_compliance,
    changelog_compliance,
    compliance_compliance,
    deploy_compliance,
    design_compliance,
    iterate_compliance,
    plan_compliance,
    security_compliance,
    test_compliance,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _write_events(project_root: Path, events: list[dict[str, Any]]) -> None:
    (project_root / "shipwright_events.jsonl").write_text(
        "\n".join(json.dumps(e) for e in events) + "\n",
        encoding="utf-8",
    )


@pytest.fixture
def proj(tmp_path: Path) -> Path:
    (tmp_path / "agent_docs").mkdir()
    return tmp_path


# ---------------------------------------------------------------------------
# W1 — TDD order (Tier-2, SKIP-only per R8)
# ---------------------------------------------------------------------------


def test_w1_skips_when_events_missing(proj: Path):
    f = build_compliance.check_w1_tdd_order(proj, "run-1")
    assert f["id"] == "W1"
    assert f["status"] == pq.STATUS_SKIP
    assert f["tier"] == 2
    assert f["provenance"] == "unverified_marker"


def test_w1_skips_when_no_build_work_events(proj: Path):
    _write_events(proj, [
        {"type": "phase_completed", "phase": "build", "ts": "2026-04-18T12:00:00Z"},
    ])
    f = build_compliance.check_w1_tdd_order(proj, "run-1")
    assert f["status"] == pq.STATUS_SKIP


def test_w1_skips_when_no_test_evidence(proj: Path):
    _write_events(proj, [
        {"type": "work_completed", "source": "build", "commit": "abc",
         "ts": "2026-04-18T12:00:00Z"},
    ])
    f = build_compliance.check_w1_tdd_order(proj, "run-1")
    assert f["status"] == pq.STATUS_SKIP


def test_w1_passes_when_test_run_precedes_work(proj: Path):
    _write_events(proj, [
        {"type": "test_run", "ts": "2026-04-18T11:00:00Z",
         "layers": {"unit": {"passed": 10, "total": 10}}},
        {"type": "work_completed", "source": "build", "commit": "abc",
         "ts": "2026-04-18T12:00:00Z", "tests": {"new": 3}},
    ])
    f = build_compliance.check_w1_tdd_order(proj, "run-1")
    assert f["status"] == pq.STATUS_PASS
    assert f["provenance"] == "events.jsonl"


def test_w1_never_fails_even_with_adverse_input(proj: Path):
    # R8: no FAIL under any input permutation.
    for events in (
        [],
        [{"type": "work_completed", "source": "build"}],
        [{"type": "work_completed", "source": "build", "tests": {"new": 0}}],
    ):
        _write_events(proj, events)
        f = build_compliance.check_w1_tdd_order(proj, "run-1")
        assert f["status"] != pq.STATUS_FAIL


# ---------------------------------------------------------------------------
# W2 — iterate external-review marker
# ---------------------------------------------------------------------------


def _write_run_config(proj: Path, **overrides: Any) -> None:
    data: dict[str, Any] = {
        "iterate_history": [{"run_id": "run-1", "complexity": "medium"}],
    }
    data.update(overrides)
    (proj / "shipwright_run_config.json").write_text(
        json.dumps(data), encoding="utf-8",
    )


def test_w2_skips_small_complexity(proj: Path):
    _write_run_config(proj, iterate_history=[{"run_id": "run-1", "complexity": "small"}])
    f = iterate_compliance.check_w2_external_review_marker(proj, "run-1")
    assert f["status"] == pq.STATUS_SKIP


def test_w2_fails_when_marker_missing(proj: Path):
    _write_run_config(proj)
    (proj / ".shipwright" / "planning" / "iterate").mkdir(parents=True)
    (proj / ".shipwright" / "planning" / "iterate" / "2026-04-18-feat.md").write_text("spec", encoding="utf-8")
    f = iterate_compliance.check_w2_external_review_marker(proj, "run-1")
    assert f["status"] == pq.STATUS_FAIL
    assert f.get("remediation")


def test_w2_passes_with_per_run_marker(proj: Path):
    _write_run_config(proj)
    d = proj / ".shipwright" / "planning" / "iterate"
    d.mkdir(parents=True)
    (d / "run-1-external-review.json").write_text("{}", encoding="utf-8")
    f = iterate_compliance.check_w2_external_review_marker(proj, "run-1")
    assert f["status"] == pq.STATUS_PASS
    # R9 — marker-based PASS carries unverified_marker provenance
    assert f["provenance"] == "unverified_marker"


def test_w2_passes_with_skipped_state_and_reason(proj: Path):
    _write_run_config(proj)
    d = proj / ".shipwright" / "planning" / "iterate"
    d.mkdir(parents=True)
    (d / "external_review_state.json").write_text(
        json.dumps({"status": "skipped_user_opt_out", "reason": "offline demo"}),
        encoding="utf-8",
    )
    f = iterate_compliance.check_w2_external_review_marker(proj, "run-1")
    assert f["status"] == pq.STATUS_PASS
    assert "offline demo" in f["evidence"]


# ---------------------------------------------------------------------------
# W3 — iterate work_completed + test-evidence
# ---------------------------------------------------------------------------


def test_w3_fails_without_work_event(proj: Path):
    f = iterate_compliance.check_w3_work_completed_and_evidence(proj, "run-1")
    assert f["status"] == pq.STATUS_FAIL


def test_w3_fails_without_evidence_file(proj: Path):
    _write_events(proj, [
        {"type": "work_completed", "source": "iterate", "ts": "2026-04-18T12:00:00Z"},
    ])
    f = iterate_compliance.check_w3_work_completed_and_evidence(proj, "run-1")
    assert f["status"] == pq.STATUS_FAIL
    assert "test-evidence" in f["evidence"]


def test_w3_passes_with_event_and_fresh_evidence(proj: Path):
    _write_events(proj, [
        {"type": "work_completed", "source": "iterate", "ts": "2026-04-18T12:00:00Z"},
    ])
    (proj / "compliance").mkdir()
    ev = proj / "compliance" / "test-evidence.md"
    ev.write_text("# Evidence\n", encoding="utf-8")
    now = time.time()
    ev.touch()
    f = iterate_compliance.check_w3_work_completed_and_evidence(proj, "run-1")
    assert f["status"] == pq.STATUS_PASS


# ---------------------------------------------------------------------------
# W4 — test coverage threshold
# ---------------------------------------------------------------------------


def test_w4_skips_without_results(proj: Path):
    f = test_compliance.check_w4_coverage_meets_threshold(proj)
    assert f["status"] == pq.STATUS_SKIP


def test_w4_fails_below_threshold(proj: Path):
    (proj / "shipwright_test_results.json").write_text(
        json.dumps({"coverage": {"total": 50}}), encoding="utf-8",
    )
    f = test_compliance.check_w4_coverage_meets_threshold(proj)
    assert f["status"] == pq.STATUS_FAIL


def test_w4_passes_at_or_above_threshold(proj: Path):
    (proj / "shipwright_test_results.json").write_text(
        json.dumps({"coverage": {"total": 85}}), encoding="utf-8",
    )
    f = test_compliance.check_w4_coverage_meets_threshold(proj)
    assert f["status"] == pq.STATUS_PASS


def test_w4_respects_custom_threshold(proj: Path):
    (proj / "shipwright_test_config.json").write_text(
        json.dumps({"coverage": {"min": 90}}), encoding="utf-8",
    )
    (proj / "shipwright_test_results.json").write_text(
        json.dumps({"coverage": {"total": 85}}), encoding="utf-8",
    )
    f = test_compliance.check_w4_coverage_meets_threshold(proj)
    assert f["status"] == pq.STATUS_FAIL
    assert "threshold=90%" in f["evidence"]


def test_w4_accepts_fractional_threshold(proj: Path):
    (proj / "shipwright_test_config.json").write_text(
        json.dumps({"coverage": {"min": 0.75}}), encoding="utf-8",
    )
    (proj / "shipwright_test_results.json").write_text(
        json.dumps({"coverage": {"total": 0.80}}), encoding="utf-8",
    )
    f = test_compliance.check_w4_coverage_meets_threshold(proj)
    assert f["status"] == pq.STATUS_PASS


# ---------------------------------------------------------------------------
# W5 — plan external review state
# ---------------------------------------------------------------------------


def test_w5_fails_when_marker_missing(proj: Path):
    f = plan_compliance.check_w5_external_review_marker(proj)
    assert f["status"] == pq.STATUS_FAIL


def test_w5_passes_with_completed_status(proj: Path):
    (proj / ".shipwright" / "planning").mkdir(parents=True)
    (proj / ".shipwright" / "planning" / "external_review_state.json").write_text(
        json.dumps({"status": "completed", "provider": "openrouter"}),
        encoding="utf-8",
    )
    f = plan_compliance.check_w5_external_review_marker(proj)
    assert f["status"] == pq.STATUS_PASS
    assert f["provenance"] == "marker"


def test_w5_fails_on_skipped_without_reason(proj: Path):
    (proj / ".shipwright" / "planning").mkdir(parents=True)
    (proj / ".shipwright" / "planning" / "external_review_state.json").write_text(
        json.dumps({"status": "skipped_user_opt_out", "reason": ""}),
        encoding="utf-8",
    )
    f = plan_compliance.check_w5_external_review_marker(proj)
    assert f["status"] == pq.STATUS_FAIL


def test_w5_passes_on_skipped_with_reason(proj: Path):
    (proj / ".shipwright" / "planning").mkdir(parents=True)
    (proj / ".shipwright" / "planning" / "external_review_state.json").write_text(
        json.dumps({
            "status": "skipped_config_disabled",
            "reason": "offline demo; feature flag off",
        }),
        encoding="utf-8",
    )
    f = plan_compliance.check_w5_external_review_marker(proj)
    assert f["status"] == pq.STATUS_PASS


# ---------------------------------------------------------------------------
# W6 — changelog git tag (wrapper)
# ---------------------------------------------------------------------------


def test_w6_warns_when_no_released_version(proj: Path):
    (proj / "CHANGELOG.md").write_text("# Changelog\n\n## [Unreleased]\n", encoding="utf-8")
    f = changelog_compliance.check_w6_git_tag_exists(proj)
    # No released version: changelog_checks returns WARNING severity
    assert f["status"] in (pq.STATUS_WARN, pq.STATUS_FAIL)


# ---------------------------------------------------------------------------
# W7 — deploy smoke status
# ---------------------------------------------------------------------------


def test_w7_skips_without_evidence(proj: Path):
    f = deploy_compliance.check_w7_smoke_status(proj)
    assert f["status"] == pq.STATUS_SKIP


def test_w7_passes_via_deploy_config(proj: Path):
    (proj / "shipwright_deploy_config.json").write_text(
        json.dumps({"smoke_test_status": "pass"}), encoding="utf-8",
    )
    f = deploy_compliance.check_w7_smoke_status(proj)
    assert f["status"] == pq.STATUS_PASS


def test_w7_fails_via_test_results(proj: Path):
    (proj / "shipwright_test_results.json").write_text(
        json.dumps({"smoke": {"status": "fail"}}), encoding="utf-8",
    )
    f = deploy_compliance.check_w7_smoke_status(proj)
    assert f["status"] == pq.STATUS_FAIL


def test_w7_falls_back_to_events(proj: Path):
    _write_events(proj, [
        {"type": "test_run", "ts": "2026-04-18T12:00:00Z",
         "layers": {"smoke": {"status": "pass"}}},
    ])
    f = deploy_compliance.check_w7_smoke_status(proj)
    assert f["status"] == pq.STATUS_PASS


# ---------------------------------------------------------------------------
# Sec1 / Sec2 — security report + critical findings
# ---------------------------------------------------------------------------


def test_sec1_fails_without_report(proj: Path):
    f = security_compliance.check_sec1_report_fresh(proj)
    assert f["status"] == pq.STATUS_FAIL


def test_sec1_passes_when_report_exists_without_phase_started(proj: Path):
    (proj / "compliance").mkdir()
    (proj / "compliance" / "security-scan-report.md").write_text(
        "# Security\n", encoding="utf-8",
    )
    f = security_compliance.check_sec1_report_fresh(proj)
    assert f["status"] == pq.STATUS_PASS


def test_sec1_fails_when_report_stale(proj: Path):
    (proj / "compliance").mkdir()
    report = proj / "compliance" / "security-scan-report.md"
    report.write_text("# Security\n", encoding="utf-8")
    # Force mtime far in the past
    past = time.time() - 7200
    import os
    os.utime(report, (past, past))
    future_ts = "2099-12-31T23:59:59Z"
    _write_events(proj, [
        {"type": "phase_started", "phase": "security", "ts": future_ts},
    ])
    f = security_compliance.check_sec1_report_fresh(proj)
    assert f["status"] == pq.STATUS_FAIL


def test_sec2_skips_without_report(proj: Path):
    f = security_compliance.check_sec2_no_critical(proj)
    assert f["status"] == pq.STATUS_SKIP


def test_sec2_passes_with_clean_report(proj: Path):
    (proj / "compliance").mkdir()
    (proj / "compliance" / "security-scan-report.md").write_text(
        "# Security\n\n| ID | Sev | Status |\n|---|---|---|\n| F-1 | LOW | resolved |\n",
        encoding="utf-8",
    )
    f = security_compliance.check_sec2_no_critical(proj)
    assert f["status"] == pq.STATUS_PASS


def test_sec2_fails_on_unresolved_critical(proj: Path):
    (proj / "compliance").mkdir()
    (proj / "compliance" / "security-scan-report.md").write_text(
        "# Security\n\n| ID | Sev | Status |\n|---|---|---|\n"
        "| F-1 | CRITICAL | unresolved |\n",
        encoding="utf-8",
    )
    f = security_compliance.check_sec2_no_critical(proj)
    assert f["status"] == pq.STATUS_FAIL


def test_sec2_passes_with_active_override(proj: Path):
    (proj / "compliance").mkdir()
    (proj / "compliance" / "security-scan-report.md").write_text(
        "# Security\n\n| ID | Sev | Status |\n|---|---|---|\n"
        "| F-1 | CRITICAL | unresolved |\n",
        encoding="utf-8",
    )
    (proj / "compliance" / "compliance_overrides.log").write_text(
        "2026-04-18 | Sec2 critical override | reason: false positive\n",
        encoding="utf-8",
    )
    f = security_compliance.check_sec2_no_critical(proj)
    assert f["status"] == pq.STATUS_PASS
    assert f["provenance"] == "override"


# ---------------------------------------------------------------------------
# Cmp1 / Cmp2 — compliance
# ---------------------------------------------------------------------------


def test_cmp1_warns_without_dashboard(proj: Path):
    f = compliance_compliance.check_cmp1_dashboard_covers_phases(proj)
    assert f["status"] == pq.STATUS_WARN
    assert f["tier"] == 2


def test_cmp1_warns_on_missing_phase_mention(proj: Path):
    _write_run_config(proj, completed_steps=["project", "design", "build"])
    (proj / "compliance").mkdir()
    (proj / "compliance" / "dashboard.md").write_text(
        "# Dashboard\n\n- project complete\n- design complete\n",
        encoding="utf-8",
    )
    f = compliance_compliance.check_cmp1_dashboard_covers_phases(proj)
    assert f["status"] == pq.STATUS_WARN
    assert "build" in f["evidence"]


def test_cmp1_passes_when_all_phases_mentioned(proj: Path):
    _write_run_config(proj, completed_steps=["project", "design", "build"])
    (proj / "compliance").mkdir()
    (proj / "compliance" / "dashboard.md").write_text(
        "# Dashboard\n\n- project\n- design\n- build\n",
        encoding="utf-8",
    )
    f = compliance_compliance.check_cmp1_dashboard_covers_phases(proj)
    assert f["status"] == pq.STATUS_PASS


def test_cmp2_skips_without_rtm(proj: Path):
    f = compliance_compliance.check_cmp2_rtm_coverage(proj)
    assert f["status"] == pq.STATUS_SKIP


def test_cmp2_fails_below_threshold(proj: Path):
    (proj / "compliance").mkdir()
    (proj / "compliance" / "traceability-matrix.md").write_text(
        "| Traceability coverage | 50% |\n", encoding="utf-8",
    )
    f = compliance_compliance.check_cmp2_rtm_coverage(proj)
    assert f["status"] == pq.STATUS_FAIL


def test_cmp2_passes_at_threshold(proj: Path):
    (proj / "compliance").mkdir()
    (proj / "compliance" / "traceability-matrix.md").write_text(
        "| Traceability coverage | 90% |\n", encoding="utf-8",
    )
    f = compliance_compliance.check_cmp2_rtm_coverage(proj)
    assert f["status"] == pq.STATUS_PASS


def test_cmp2_respects_configured_threshold(proj: Path):
    (proj / "compliance").mkdir()
    (proj / "compliance" / "traceability-matrix.md").write_text(
        "| Traceability coverage | 75% |\n", encoding="utf-8",
    )
    (proj / "shipwright_compliance_config.json").write_text(
        json.dumps({"enforcement": {"rtm_coverage_min": 0.70}}),
        encoding="utf-8",
    )
    f = compliance_compliance.check_cmp2_rtm_coverage(proj)
    assert f["status"] == pq.STATUS_PASS


# ---------------------------------------------------------------------------
# D1 / D2 — design
# ---------------------------------------------------------------------------


def test_d1_fails_without_artifacts(proj: Path):
    f = design_compliance.check_d1_design_artifact(proj)
    assert f["status"] == pq.STATUS_FAIL


def test_d1_passes_with_html_mockup(proj: Path):
    (proj / "designs" / "mockups").mkdir(parents=True)
    (proj / "designs" / "mockups" / "01-login.html").write_text("<html/>", encoding="utf-8")
    f = design_compliance.check_d1_design_artifact(proj)
    assert f["status"] == pq.STATUS_PASS


def test_d1_passes_with_screens_md_only(proj: Path):
    (proj / "agent_docs" / "screens.md").write_text("# Screens\n", encoding="utf-8")
    f = design_compliance.check_d1_design_artifact(proj)
    assert f["status"] == pq.STATUS_PASS


def test_d2_warns_on_missing(proj: Path):
    f = design_compliance.check_d2_docs_present(proj)
    assert f["status"] == pq.STATUS_WARN
    assert f["tier"] == 2


def test_d2_passes_with_both_docs(proj: Path):
    (proj / "agent_docs" / "screens.md").write_text("# Screens\n", encoding="utf-8")
    (proj / "agent_docs" / "user-flow.md").write_text("# Flows\n", encoding="utf-8")
    f = design_compliance.check_d2_docs_present(proj)
    assert f["status"] == pq.STATUS_PASS


# ---------------------------------------------------------------------------
# Dispatcher resilience (R10)
# ---------------------------------------------------------------------------


def test_dispatcher_returns_empty_for_phase_without_workflow_checks(proj: Path):
    assert pq.run_workflow_checks("project", proj, "run-1") == []


def test_dispatcher_survives_broken_wrapper(monkeypatch, proj: Path):
    import importlib

    original_import = importlib.import_module

    def boom(name: str, *args, **kwargs):
        if name.endswith("build_compliance"):
            raise RuntimeError("boom")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(importlib, "import_module", boom)
    findings = pq.run_workflow_checks("build", proj, "run-1")
    assert len(findings) == 1
    assert findings[0]["status"] == pq.STATUS_FAIL
    assert findings[0]["provenance"] == "error"


def test_dispatcher_applies_env_skip_override(monkeypatch, proj: Path):
    monkeypatch.setenv("SHIPWRIGHT_SKIP_QUALITY_CHECK", "W4")
    monkeypatch.setenv("SHIPWRIGHT_AUDIT_OVERRIDE_REASON", "legacy project, no coverage tooling")
    findings = pq.run_workflow_checks("test", proj, "run-1")
    w4 = next(f for f in findings if f["id"] == "W4")
    assert w4["status"] == pq.STATUS_SKIP
    assert "legacy project" in w4["evidence"]
    assert w4["provenance"] == "override"


def test_dispatcher_each_phase_runs_all_checks(proj: Path):
    """Smoke test: every phase with workflow checks returns at least one finding
    with a well-formed id (no exceptions, no empty evidence)."""
    expected_min = {
        "build": 1, "iterate": 2, "test": 1, "plan": 1, "changelog": 1,
        "deploy": 1, "security": 2, "compliance": 2, "design": 2,
    }
    for phase, n in expected_min.items():
        findings = pq.run_workflow_checks(phase, proj, "run-1")
        assert len(findings) >= n, f"{phase}: expected >={n}, got {len(findings)}"
        for f in findings:
            assert f.get("id"), f"missing id in {phase}: {f}"
            assert f.get("status") in {
                pq.STATUS_PASS, pq.STATUS_FAIL, pq.STATUS_WARN, pq.STATUS_SKIP,
            }
