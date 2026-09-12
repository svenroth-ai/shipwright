"""Tests for ``check_e2e_specs_exist_when_journeys_planned`` (FR-01.06 #6,
sub-iterate ``e3-checks-test-security``).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tools.verifiers._test_gate_specs import (
    check_e2e_specs_exist_when_journeys_planned,
    _plan_declares_a_flow,
)

_PLAN_WITH_FLOW = """# E2E Test Plan

## User Flows

### Flow 1: Sign up

Steps...

## Page Object Model

nothing here is a flow
"""

_PLAN_WITHOUT_FLOW = """# E2E Test Plan

## User Flows

## Page Object Model
"""

_PLAN_NO_SECTION = """# Random notes

Nothing resembling a plan.
"""


def _write_plan(root: Path, text: str, split: str = "01-auth") -> Path:
    split_dir = root / ".shipwright" / "planning" / split
    split_dir.mkdir(parents=True, exist_ok=True)
    path = split_dir / "claude-plan-e2e.md"
    path.write_text(text, encoding="utf-8")
    return path


def test_skips_when_no_planning_dir(tmp_path):
    r = check_e2e_specs_exist_when_journeys_planned(tmp_path)
    assert r.is_skipped


def test_skips_when_no_plan_file(tmp_path):
    (tmp_path / ".shipwright" / "planning").mkdir(parents=True)
    r = check_e2e_specs_exist_when_journeys_planned(tmp_path)
    assert r.is_skipped
    assert "no claude-plan-e2e.md" in r.detail


def test_skips_when_plan_declares_no_flows(tmp_path):
    _write_plan(tmp_path, _PLAN_WITHOUT_FLOW)
    r = check_e2e_specs_exist_when_journeys_planned(tmp_path)
    assert r.is_skipped
    assert "none declare a flow" in r.detail


def test_invalid_utf8_plan_file_is_skipped_not_crashed(tmp_path):
    """Tier-3 CI review (PR #748, round 6): UnicodeDecodeError is a
    ValueError, not an OSError, so a plan file with invalid UTF-8 bytes used
    to crash the whole gate instead of being treated like any other
    unreadable file (folded into "no plan declares a flow")."""
    path = _write_plan(tmp_path, _PLAN_WITH_FLOW)
    path.write_bytes(b"\xff\xfe not valid utf-8 \x80\x81")
    r = check_e2e_specs_exist_when_journeys_planned(tmp_path)
    assert r.is_skipped
    assert "none declare a flow" in r.detail


def test_skips_when_plan_has_no_user_flows_section_at_all(tmp_path):
    _write_plan(tmp_path, _PLAN_NO_SECTION)
    r = check_e2e_specs_exist_when_journeys_planned(tmp_path)
    assert r.is_skipped


def test_fails_when_flow_declared_but_no_e2e_dir(tmp_path):
    _write_plan(tmp_path, _PLAN_WITH_FLOW)
    r = check_e2e_specs_exist_when_journeys_planned(tmp_path)
    assert r.ok is False
    assert "no *.spec.ts" in r.detail


def test_fails_when_flow_declared_but_e2e_dir_empty(tmp_path):
    _write_plan(tmp_path, _PLAN_WITH_FLOW)
    (tmp_path / "e2e").mkdir()
    r = check_e2e_specs_exist_when_journeys_planned(tmp_path)
    assert r.ok is False


def test_passes_when_specs_exist_alongside_flow(tmp_path):
    _write_plan(tmp_path, _PLAN_WITH_FLOW)
    flows = tmp_path / "e2e" / "flows"
    flows.mkdir(parents=True)
    (flows / "01-signup.spec.ts").write_text("test('signup', () => {});")
    r = check_e2e_specs_exist_when_journeys_planned(tmp_path)
    assert r.ok is True


def test_nested_spec_files_are_found(tmp_path):
    _write_plan(tmp_path, _PLAN_WITH_FLOW)
    nested = tmp_path / "e2e" / "flows" / "deep"
    nested.mkdir(parents=True)
    (nested / "01-signup.spec.ts").write_text("test('signup', () => {});")
    r = check_e2e_specs_exist_when_journeys_planned(tmp_path)
    assert r.ok is True


def test_unreadable_plan_file_is_skipped_not_crashed(tmp_path):
    """A plan directory named ``claude-plan-e2e.md`` (a directory, not a
    file) must not crash the check — OSError on read is swallowed and
    treated as no-flow-declared for that entry."""
    split_dir = tmp_path / ".shipwright" / "planning" / "01-auth"
    split_dir.mkdir(parents=True)
    (split_dir / "claude-plan-e2e.md").mkdir()
    r = check_e2e_specs_exist_when_journeys_planned(tmp_path)
    assert r.is_skipped


def test_symlinked_plan_escaping_root_is_treated_as_absent(tmp_path):
    outside = tmp_path.parent / "outside_e2e_plan_target.md"
    outside.write_text(_PLAN_WITH_FLOW, encoding="utf-8")
    split_dir = tmp_path / ".shipwright" / "planning" / "01-auth"
    split_dir.mkdir(parents=True)
    try:
        (split_dir / "claude-plan-e2e.md").symlink_to(outside)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlink unsupported in this environment: {exc}")  # test-hygiene: allow-silent-skip: symlink needs OS/privilege (Windows dev-mode); POSIX CI exercises it

    try:
        r = check_e2e_specs_exist_when_journeys_planned(tmp_path)
        # The symlinked plan is ignored entirely (treated as declaring no
        # flow), never read as if it were this project's own plan content.
        assert r.is_skipped
    finally:
        outside.unlink(missing_ok=True)


def test_plan_with_utf8_bom_is_still_read_correctly(tmp_path):
    """Step 3.8 confidence-calibration probe (empirical, not theoretical):
    a plan file saved with a leading UTF-8 BOM (Notepad, some Windows
    editors) previously kept the BOM as the first character of the first
    line, so `^##` never matched a heading that happened to open the
    file -- a real false-negative caught by probing the boundary rather
    than reasoning about it."""
    split_dir = tmp_path / ".shipwright" / "planning" / "01-auth"
    split_dir.mkdir(parents=True)
    (split_dir / "claude-plan-e2e.md").write_bytes(
        b"\xef\xbb\xbf" + _PLAN_WITH_FLOW.encode("utf-8")
    )
    r = check_e2e_specs_exist_when_journeys_planned(tmp_path)
    assert r.ok is False  # flow declared, no spec.ts yet -- NOT a false skip
    assert "declare user flows" in r.detail


def test_symlinked_spec_file_escaping_root_does_not_satisfy_the_gate(tmp_path):
    """External review round 2 (openai, low/security): a repo-controlled
    symlink under e2e/ pointing outside the project must not satisfy this
    gate in place of a real project-local browser test."""
    _write_plan(tmp_path, _PLAN_WITH_FLOW)
    outside = tmp_path.parent / "outside_spec_target.spec.ts"
    outside.write_text("test('unrelated', () => {});")
    flows = tmp_path / "e2e" / "flows"
    flows.mkdir(parents=True)
    try:
        (flows / "escaping.spec.ts").symlink_to(outside)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlink unsupported in this environment: {exc}")  # test-hygiene: allow-silent-skip: symlink needs OS/privilege (Windows dev-mode); POSIX CI exercises it

    try:
        r = check_e2e_specs_exist_when_journeys_planned(tmp_path)
        assert r.ok is False
        assert "no *.spec.ts" in r.detail
    finally:
        outside.unlink(missing_ok=True)


def test_multiple_plans_only_one_with_flows(tmp_path):
    _write_plan(tmp_path, _PLAN_WITHOUT_FLOW, split="01-auth")
    _write_plan(tmp_path, _PLAN_WITH_FLOW, split="02-billing")
    r = check_e2e_specs_exist_when_journeys_planned(tmp_path)
    assert r.ok is False
    assert "1 E2E plan(s)" in r.detail


# --- _plan_declares_a_flow direct coverage -----------------------------------

def test_plan_declares_a_flow_true():
    assert _plan_declares_a_flow(_PLAN_WITH_FLOW) is True


def test_plan_declares_a_flow_false_no_h3():
    assert _plan_declares_a_flow(_PLAN_WITHOUT_FLOW) is False


def test_plan_declares_a_flow_false_no_section():
    assert _plan_declares_a_flow(_PLAN_NO_SECTION) is False


def test_plan_declares_a_flow_ignores_h3_outside_section():
    text = """## Page Object Model

### home.page.ts

## User Flows

(no flows listed here)
"""
    assert _plan_declares_a_flow(text) is False


def test_plan_declares_a_flow_is_case_sensitive_matching_journey_plan_py():
    """External review round 2 (GLM): the heading match must stay
    case-sensitive, mirroring `journey_plan.py`'s own `_USER_FLOWS_SECTION`
    exactly — a case-insensitive floor could count a heading the real
    generator does not, disagreeing with the tool it floor-checks."""
    text = """# E2E Test Plan

## User flows

### Flow 1: Sign up

Steps...
"""
    assert _plan_declares_a_flow(text) is False


def test_plan_declares_a_flow_duplicate_heading_terminates_section():
    """External review (low): the old ``_NEXT_H2_RE`` never matched a
    second ``## User Flows`` heading, so H3s living under it (or later,
    unrelated H2 sections) could be miscounted as flows of the FIRST
    section. Any subsequent H2 — including a duplicate — must terminate."""
    text = """# E2E Test Plan

## User Flows

(no flows in the first section)

## User Flows

### Flow 1: Sign up

Steps...
"""
    assert _plan_declares_a_flow(text) is False
