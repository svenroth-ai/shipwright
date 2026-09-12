"""``check-plan-gates.py --gate sections`` (Step 9) — split out of
``test_check_plan_gates.py`` (300-LOC guideline). Review/boundary gates
live there; this file covers section quality, FR coverage/trace, dependency
order, the decision-log trail (FR-01.03 #8/#10), and the E2E-journeys check
(FR-01.03 #11).
"""

import json

import pytest

from tests._check_plan_gates_support import _problems, run_gates

# `planning` fixture comes from conftest.py — no import needed, and importing
# it here would shadow the same-named test-function parameter (ruff F811).


def test_a_prerequisite_after_its_user_fails(planning, no_e2e_plugin_root):
    (planning / "plan.md").write_text(
        "# Plan\n\n<!-- SECTION_MANIFEST\n01-a: 02-b\n02-b\nEND_MANIFEST -->\n",
        encoding="utf-8",
    )
    code, out = run_gates(planning, "sections", plugin_root=no_e2e_plugin_root)
    assert code == 1
    assert any("numbered after it" in p for p in _problems(out, "sections"))


@pytest.mark.covers("FR-01.03/AC05")
def test_an_uncovered_requirement_fails(planning, no_e2e_plugin_root):
    (planning / "spec.md").write_text(
        "# Spec\n\n| ID | Requirement | Priority |\n"
        "| FR-01.01 | thing | Must |\n| FR-01.02 | other thing | Must |\n",
        encoding="utf-8",
    )
    code, out = run_gates(planning, "sections", plugin_root=no_e2e_plugin_root)
    assert code == 1
    assert any("FR-01.02" in p and "no section" in p for p in _problems(out, "sections"))


@pytest.mark.covers("FR-01.03/AC06")
def test_a_section_serving_no_requirement_fails(planning, no_e2e_plugin_root):
    (planning / "sections" / "02-b.md").write_text(
        "# Section: 02-b\n\n## Overview\nWork nobody asked for.\n\n"
        "## Prerequisites\nNone.\n\n"
        "## Implementation Steps\n1. one\n2. two\n\n## Tests First\n- t\n",
        encoding="utf-8",
    )
    code, out = run_gates(planning, "sections", plugin_root=no_e2e_plugin_root)
    assert code == 1
    assert any("02-b" in p and "no live requirement" in p for p in _problems(out, "sections"))


@pytest.mark.covers("FR-01.03/AC07", "FR-01.03/AC08")
def test_an_ill_formed_section_fails_even_in_a_new_plan(planning, no_e2e_plugin_root):
    """No leniency in session: a section written today has no excuse.

    FR-01.03/AC07 (says what it is for, >=2 steps, states how tested) and
    AC08 (names prerequisites so a builder needn't read other sections) are
    exactly the four shape problems this section is missing, asserted below."""
    (planning / "sections" / "02-b.md").write_text(
        "# Section: 02-b\n\nRequirements: FR-01.01\n\nJust prose.\n", encoding="utf-8"
    )
    code, out = run_gates(planning, "sections", plugin_root=no_e2e_plugin_root)
    assert code == 1
    problems = _problems(out, "sections")
    assert sum(1 for p in problems if p.startswith("02-b")) == 4


def test_a_declared_but_unwritten_section_fails(planning, no_e2e_plugin_root):
    (planning / "sections" / "02-b.md").unlink()
    code, out = run_gates(planning, "sections", plugin_root=no_e2e_plugin_root)
    assert code == 1
    assert any("declared but not written: 02-b" in p for p in _problems(out, "sections"))


def test_an_unparseable_manifest_reports_the_parse_errors(planning, no_e2e_plugin_root):
    (planning / "plan.md").write_text(
        "# Plan\n\n<!-- SECTION_MANIFEST\nBad Name\nEND_MANIFEST -->\n", encoding="utf-8"
    )
    code, out = run_gates(planning, "sections", plugin_root=no_e2e_plugin_root)
    assert code == 1
    assert any("Invalid section name" in p for p in _problems(out, "sections"))


# --- the section gate's decision-log trail (Step 9, FR-01.03 #8 / #10) -----


@pytest.mark.covers("FR-01.03/AC18")
def test_no_planning_decision_logged_fails(tmp_path, planning, no_e2e_plugin_root):
    (tmp_path / ".shipwright" / "agent_docs" / "decision_log.md").write_text(
        "# Decision Log\n", encoding="utf-8"
    )
    code, out = run_gates(planning, "sections", plugin_root=no_e2e_plugin_root)
    assert code == 1
    assert any("01-auth" in p and "no design decision" in p for p in _problems(out, "sections"))


@pytest.mark.covers("FR-01.03/AC12")
def test_findings_count_unmatched_by_logged_entries_fails(tmp_path, planning, no_e2e_plugin_root):
    (planning / "external_review_state.json").write_text(
        json.dumps({
            "status": "completed", "provider": "openrouter", "findings_count": 2,
            "verdicts": {"gemini": "approve", "openai": "revise"},
        }),
        encoding="utf-8",
    )
    code, out = run_gates(planning, "sections", plugin_root=no_e2e_plugin_root)
    assert code == 1
    assert any("findings_count=2" in p for p in _problems(out, "sections"))


@pytest.mark.covers("FR-01.03/AC12")
def test_findings_count_matched_by_logged_entries_passes(tmp_path, planning, no_e2e_plugin_root):
    (planning / "external_review_state.json").write_text(
        json.dumps({
            "status": "completed", "provider": "openrouter", "findings_count": 1,
            "verdicts": {"gemini": "approve", "openai": "revise"},
        }),
        encoding="utf-8",
    )
    log = (tmp_path / ".shipwright" / "agent_docs" / "decision_log.md")
    log.write_text(
        log.read_text(encoding="utf-8")
        + "\n---\n\n### ADR-002: fix x\n- **Section:** External Review — 01-auth\n"
          "- **Context:** x\n- **Decision:** y\n- **Commit:** n/a\n",
        encoding="utf-8",
    )
    assert run_gates(planning, "sections", plugin_root=no_e2e_plugin_root)[0] == 0


# --- the section gate's E2E-journeys check (Step 9, FR-01.03 #11) ----------


def test_a_missing_plugin_root_is_a_usage_error_not_a_silent_skip(planning):
    """External review, iterate-2026-09-11-e1-checks-plan-design: omitting
    --plugin-root used to silently skip gate #11 (E2E journeys) instead of
    failing the usage."""
    code, out = run_gates(planning, "sections")
    assert code == 2
    assert out["error"] == "plugin_root_required"


@pytest.mark.covers("FR-01.03/AC14")
def test_missing_e2e_file_fails_when_a_plugin_root_is_given(tmp_path, planning):
    plugin_root = tmp_path / "plugin"
    plugin_root.mkdir()
    code, out = run_gates(planning, "sections", plugin_root=plugin_root)
    assert code == 1
    assert any("claude-plan-e2e.md" in p and "does not exist" in p for p in _problems(out, "sections"))


def test_e2e_disabled_in_config_needs_no_file(tmp_path, planning):
    plugin_root = tmp_path / "plugin"
    plugin_root.mkdir()
    (plugin_root / "config.json").write_text(
        json.dumps({"e2e_test_plan": {"enabled": False}}), encoding="utf-8"
    )
    assert run_gates(planning, "sections", plugin_root=plugin_root)[0] == 0


@pytest.mark.covers("FR-01.03/AC14")
def test_an_e2e_file_naming_a_flow_passes(tmp_path, planning):
    plugin_root = tmp_path / "plugin"
    plugin_root.mkdir()
    (planning / "claude-plan-e2e.md").write_text(
        "# E2E Test Plan\n\n## User Flows\n\n### Flow 1: Sign up\n- steps\n",
        encoding="utf-8",
    )
    assert run_gates(planning, "sections", plugin_root=plugin_root)[0] == 0
