"""Autonomous runs settle a section's soft size target by splitting modules, not by asking (e2e run 20, gate 28)."""
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

pytestmark = pytest.mark.covers("FR-01.05")


def _read(rel: str) -> str:
    return " ".join((ROOT / rel).read_text(encoding="utf-8").split())


def test_spec_reviewer_passes_a_split_and_rejects_cut_behaviour():
    text = _read("agents/spec-reviewer.md")
    assert "Size-target carve-out (autonomous runs)" in text
    assert "split into further modules" in text and "cut required behaviour" in text and "raised the limit" in text


def test_build_skill_and_reference_state_the_rule():
    assert "Size decision: split allowed (soft target)" in _read("skills/build/SKILL.md")
    ref = _read("skills/build/references/requirement-writeback.md")
    assert "Size target vs required behaviour (autonomous runs)" in ref and "Ask only when no split is possible" in ref


MARKER = "Size decision: split allowed (soft target)"


def test_carve_out_is_keyed_on_the_marker_so_interactive_runs_are_unchanged():
    text = _read("agents/spec-reviewer.md")
    assert MARKER in text and "ONLY when the section contains the line" in text and "without that line the size target is a limit" in text
    assert MARKER in _read("skills/build/references/requirement-writeback.md")


def test_section_writer_writes_the_marker_only_in_autonomous_runs():
    text = " ".join((ROOT.parent / "shipwright-plan" / "agents" / "section-writer.md").read_text(encoding="utf-8").split())
    assert MARKER in text and "In an interactive run never write it" in text


def test_build_autonomy_definition_matches_design_and_plan():
    text = _read("skills/build/references/code-review.md")
    assert "a `brief_package` in `shipwright_run_config.json`, or `autonomy` is `autonomous` or `unattended`" in text
