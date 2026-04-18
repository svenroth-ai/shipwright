"""Rollout tests for Phase-Quality PR 4.

Covers plan § 7 risk IDs R15-R25:

- R15 — S2 SKIPs when complexity=small.
- R16 — S4 WARNs, never FAILs on removed FRs.
- R17 — S9/S10 WARN (never FAIL) on missing doc freshness.
- R18 — S8 respects greenfield / monorepo layouts.
- R19 — ``SHIPWRIGHT_ENFORCE_CRITICAL_GATES=1`` default OFF.
- R20 — SessionStart-Injection capped at 3 Tier-1 FAILs; WARN excluded.
- R21 — Per-run findings files + session summary hard-capped.
- R22 — Audit hook fires only on Stop matcher (covered in existing
  test_audit_phase_quality.py via hook registration tests).
- R23 — Canon findings carry audited_at (covered in phase_quality
  write_finding_json).
- R24 — Marketplace-cache drift is an ops concern, covered in
  scripts/update-marketplace.sh; tested indirectly via
  test_plugin_hooks_json_registers_audit_hook.
- R25 — Override reason is required for SKIP (tested in PR 1 harness).

This file focuses on the PR 4 deltas: the env-flag matrix for
``SHIPWRIGHT_PHASE_QUALITY_MODE`` and
``SHIPWRIGHT_ENFORCE_CRITICAL_GATES``, the Orchestrator-Gate helper
functions, and the SessionStart injection parser.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_ORCH_LIB = _PROJECT_ROOT / "plugins" / "shipwright-run" / "scripts" / "lib"
if str(_ORCH_LIB) not in sys.path:
    sys.path.insert(0, str(_ORCH_LIB))

from hooks import capture_session_id as cs  # noqa: E402
from lib import phase_quality as pq  # noqa: E402

import orchestrator  # noqa: E402


CAPTURE_SCRIPT = str(_SCRIPTS / "hooks" / "capture_session_id.py")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def proj(tmp_path: Path) -> Path:
    (tmp_path / "agent_docs").mkdir()
    return tmp_path


def _write_run_config(proj: Path, data: dict) -> None:
    (proj / "shipwright_run_config.json").write_text(
        json.dumps(data), encoding="utf-8",
    )


def _write_summary(proj: Path, text: str) -> None:
    (proj / "agent_docs").mkdir(exist_ok=True)
    (proj / "agent_docs" / "skill-compliance-findings.md").write_text(
        text, encoding="utf-8",
    )


def _run_capture(payload: str, cwd: Path, **env_overrides) -> subprocess.CompletedProcess:
    env = {**os.environ}
    # Strip any inherited phase-quality env so tests are deterministic.
    for k in (
        "SHIPWRIGHT_PHASE_QUALITY_MODE",
        "SHIPWRIGHT_ENFORCE_CRITICAL_GATES",
        "SHIPWRIGHT_SESSION_ID",
    ):
        env.pop(k, None)
    env.update(env_overrides)
    return subprocess.run(
        [sys.executable, CAPTURE_SCRIPT],
        input=payload,
        capture_output=True, text=True, encoding="utf-8",
        cwd=str(cwd), env=env,
    )


# ---------------------------------------------------------------------------
# R19 — ENFORCE_CRITICAL_GATES default OFF
# ---------------------------------------------------------------------------


def test_enforce_critical_gates_default_off(monkeypatch):
    monkeypatch.delenv("SHIPWRIGHT_ENFORCE_CRITICAL_GATES", raising=False)
    assert orchestrator._enforce_critical_gates_enabled() is False


@pytest.mark.parametrize("value,expected", [
    ("1", True), ("true", True), ("yes", True), ("on", True),
    ("0", False), ("false", False), ("no", False), ("", False),
])
def test_enforce_critical_gates_env_matrix(monkeypatch, value, expected):
    monkeypatch.setenv("SHIPWRIGHT_ENFORCE_CRITICAL_GATES", value)
    assert orchestrator._enforce_critical_gates_enabled() is expected


def test_critical_gate_only_triggers_on_w5_w6_w7():
    """R19 — Only W5/W6/W7 FAILs promote to ask-level, never others."""
    finding = {
        "workflow": [
            {"id": "W1", "status": "FAIL", "evidence": "TDD broken"},
            {"id": "W5", "status": "FAIL", "evidence": "external review missing"},
            {"id": "W6", "status": "FAIL", "evidence": "no git tag"},
            {"id": "W7", "status": "PASS", "evidence": "smoke ok"},
        ],
        "canon": [{"id": "C1", "status": "FAIL", "evidence": "event missing"}],
    }
    issues = orchestrator._collect_critical_gate_issues(finding)
    names = [i["name"] for i in issues]
    assert any("W5" in n for n in names)
    assert any("W6" in n for n in names)
    # W7 was PASS — excluded. W1/C1 not in critical allowlist.
    assert not any("W1" in n for n in names)
    assert not any("C1" in n for n in names)
    assert not any("W7" in n for n in names)


def test_critical_gate_skips_tier2_findings():
    """R19 — Tier-2 findings are never enforced, even if id is critical."""
    finding = {
        "workflow": [
            {"id": "W5", "status": "FAIL", "evidence": "x", "tier": 2},
        ],
    }
    assert orchestrator._collect_critical_gate_issues(finding) == []


def test_critical_gate_issue_carries_remediation():
    finding = {
        "workflow": [{
            "id": "W6", "status": "FAIL",
            "evidence": "no tag",
            "remediation": "Run git tag v0.1.0",
        }],
    }
    issues = orchestrator._collect_critical_gate_issues(finding)
    assert len(issues) == 1
    assert issues[0]["severity"] == "ask"
    assert "git tag" in issues[0]["remediation"]


def test_read_latest_finding_picks_most_recent(proj: Path, monkeypatch):
    # Two phase findings; newer should win.
    d = proj / "compliance" / "skill-compliance"
    d.mkdir(parents=True)
    older = d / "build-run-1-sess-1.json"
    newer = d / "build-run-2-sess-2.json"
    older.write_text(
        json.dumps({"phase": "build", "workflow": [
            {"id": "W6", "status": "FAIL", "evidence": "old"}
        ]}), encoding="utf-8",
    )
    newer.write_text(
        json.dumps({"phase": "build", "workflow": [
            {"id": "W6", "status": "PASS", "evidence": "fixed"}
        ]}), encoding="utf-8",
    )
    # Ensure mtime ordering
    import time
    os.utime(older, (time.time() - 10, time.time() - 10))
    finding = orchestrator._read_latest_phase_quality_finding(proj, "build")
    assert finding is not None
    assert finding["workflow"][0]["evidence"] == "fixed"


def test_read_latest_finding_none_on_greenfield(proj: Path):
    assert orchestrator._read_latest_phase_quality_finding(proj, "build") is None


# ---------------------------------------------------------------------------
# R20 — SessionStart-Injection cap + Tier-2 exclusion
# ---------------------------------------------------------------------------


def test_inject_mode_default_on(monkeypatch):
    """Post-epic default: injection is ON unless explicitly opted out."""
    monkeypatch.delenv("SHIPWRIGHT_PHASE_QUALITY_MODE", raising=False)
    assert cs._phase_quality_inject_enabled() is True


def test_inject_mode_off_when_audit_only(monkeypatch):
    monkeypatch.setenv("SHIPWRIGHT_PHASE_QUALITY_MODE", "audit_only")
    assert cs._phase_quality_inject_enabled() is False


@pytest.mark.parametrize("value,expected", [
    ("audit_only", False),     # explicit opt-out — only value that disables
    ("audit_inject", True),    # legacy explicit opt-in still works
    ("other", True),           # anything unknown → default ON
    ("AUDIT_ONLY ", False),    # case-insensitive + whitespace-tolerant
    ("", True),                # empty env var → default ON
])
def test_inject_mode_audit_only_is_only_disabler(monkeypatch, value, expected):
    """audit_only is the only value that disables injection; default ON."""
    monkeypatch.setenv("SHIPWRIGHT_PHASE_QUALITY_MODE", value)
    assert cs._phase_quality_inject_enabled() is expected


def test_collect_tier1_fails_caps_at_five():
    """R20 (revised post-epic) — max 5 Tier-1 FAILs injected, rest dropped."""
    text = "\n".join([
        "## build — run-1",
        "- audited_at: 2026-04-19",
        "- source: orchestrator",
        "- totals: 0 PASS · 7 FAIL · 0 WARN · 0 SKIP",
        "- open FAILs:",
        "  - **W5** external review missing",
        "  - **W6** no git tag",
        "  - **W7** smoke not green",
        "  - **I1** RTM stale",
        "  - **I2** test evidence stale",
        "  - **I3** change-history stale",
        "  - **C1** no phase_completed event",
        "",
    ])
    fails = cs._collect_tier1_fails(text)
    assert len(fails) == 5
    assert [f["id"] for f in fails] == ["W5", "W6", "W7", "I1", "I2"]


def test_collect_tier1_fails_filters_tier2():
    """R20 — Tier-2 ids (S3/Q1/T2/...) never injected."""
    text = "\n".join([
        "## iterate — run-42",
        "- open FAILs:",
        "  - **W2** marker missing",
        "  - **T2** orphan rows",     # Tier-2
        "  - **Q1** ADR too thin",    # Tier-2
        "  - **I4** sbom stale",      # Tier-2
        "  - **S9** readme stale",    # Tier-2
        "  - **C1** event missing",
        "",
    ])
    fails = cs._collect_tier1_fails(text)
    ids = [f["id"] for f in fails]
    assert "T2" not in ids
    assert "Q1" not in ids
    assert "I4" not in ids
    assert "S9" not in ids
    assert "W2" in ids
    assert "C1" in ids


def test_collect_tier1_fails_empty_on_no_fail_block():
    text = "## build — run-1\n- audited_at: x\n"
    assert cs._collect_tier1_fails(text) == []


def test_format_injection_contains_phase_and_ids():
    fails = [
        {"id": "W5", "phase": "plan", "run": "r1", "evidence": "review missing"},
        {"id": "W6", "phase": "changelog", "run": "r2", "evidence": "no tag"},
    ]
    text = cs._format_injection(fails)
    assert "W5" in text
    assert "plan" in text
    assert "W6" in text
    assert "changelog" in text
    assert "Phase-Quality" in text


def test_build_injection_returns_empty_when_mode_audit_only(tmp_path, monkeypatch):
    """audit_only is the documented opt-out — even with findings, no inject."""
    monkeypatch.setenv("SHIPWRIGHT_PHASE_QUALITY_MODE", "audit_only")
    _write_summary(tmp_path, (
        "## build — run-1\n- open FAILs:\n  - **W6** no tag\n"
    ))
    assert cs._build_phase_quality_injection(str(tmp_path)) == ""


def test_build_injection_reads_summary_by_default(tmp_path, monkeypatch):
    """Default mode is inject-on; no env needed."""
    monkeypatch.delenv("SHIPWRIGHT_PHASE_QUALITY_MODE", raising=False)
    (tmp_path / "agent_docs").mkdir()
    _write_summary(tmp_path, (
        "## build — run-1\n"
        "- audited_at: 2026-04-19\n"
        "- source: orchestrator\n"
        "- totals: 0 PASS · 1 FAIL · 0 WARN · 0 SKIP\n"
        "- open FAILs:\n"
        "  - **W6** no git tag\n"
    ))
    text = cs._build_phase_quality_injection(str(tmp_path))
    assert text
    assert "W6" in text
    assert "build" in text


def test_build_injection_no_summary_file(tmp_path, monkeypatch):
    """Default mode on + missing summary → empty string (silent no-op)."""
    monkeypatch.delenv("SHIPWRIGHT_PHASE_QUALITY_MODE", raising=False)
    assert cs._build_phase_quality_injection(str(tmp_path)) == ""


# ---------------------------------------------------------------------------
# Capture-session-id subprocess: injection flow end-to-end
# ---------------------------------------------------------------------------


def test_capture_session_injects_by_default(tmp_path, monkeypatch):
    """Post-epic default: injection ON, Claude sees Tier-1 FAILs at SessionStart."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "agent_docs").mkdir()
    (tmp_path / "shipwright_run_config.json").write_text("{}", encoding="utf-8")
    _write_summary(tmp_path, (
        "## build — run-1\n"
        "- audited_at: 2026-04-19\n"
        "- source: orchestrator\n"
        "- totals: 0 PASS · 1 FAIL · 0 WARN · 0 SKIP\n"
        "- open FAILs:\n"
        "  - **W6** no git tag\n"
    ))
    result = _run_capture(
        json.dumps({"session_id": "sess-x"}),
        cwd=tmp_path,
        CLAUDE_PLUGIN_ROOT="/fake/plugin",
    )
    assert result.stdout.strip()
    out = json.loads(result.stdout)
    context = out["hookSpecificOutput"]["additionalContext"]
    assert "Phase-Quality" in context
    assert "W6" in context


def test_capture_session_does_not_inject_when_audit_only(tmp_path, monkeypatch):
    """audit_only is the documented opt-out lever for a silent session."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "agent_docs").mkdir()
    _write_summary(tmp_path, (
        "## build — run-1\n- open FAILs:\n  - **W6** no tag\n"
    ))
    result = _run_capture(
        json.dumps({"session_id": "sess-x"}),
        cwd=tmp_path,
        CLAUDE_PLUGIN_ROOT="/fake/plugin",
        SHIPWRIGHT_PHASE_QUALITY_MODE="audit_only",
    )
    if result.stdout.strip():
        out = json.loads(result.stdout)
        context = out["hookSpecificOutput"]["additionalContext"]
        assert "Phase-Quality" not in context


# ---------------------------------------------------------------------------
# PLUGIN_TO_PHASE sanity (R22/R24 — registration stable)
# ---------------------------------------------------------------------------


def test_phase_quality_tier2_set_includes_new_spec_ids():
    """Tier-2 must still include S3-S5, S7, S9, S10 after PR 4."""
    for sid in ("S3", "S4", "S5", "S7", "S9", "S10"):
        assert sid in pq.TIER_2_CHECK_IDS


def test_phase_quality_flag_disabled_by_zero(monkeypatch):
    """R19 spirit — SHIPWRIGHT_PHASE_QUALITY=0 disables hook entirely."""
    monkeypatch.setenv("SHIPWRIGHT_PHASE_QUALITY", "0")
    assert pq.phase_quality_enabled() is False


def test_phase_quality_flag_default_on(monkeypatch):
    monkeypatch.delenv("SHIPWRIGHT_PHASE_QUALITY", raising=False)
    assert pq.phase_quality_enabled() is True


def test_critical_gate_constants_frozen():
    """Defensive: critical gate set is exactly {W5, W6, W7}."""
    assert orchestrator._CRITICAL_GATE_CHECK_IDS == frozenset({"W5", "W6", "W7"})
