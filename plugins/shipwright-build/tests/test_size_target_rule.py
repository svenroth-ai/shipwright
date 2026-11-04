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
    assert "soft target (autonomous run)" in _read("skills/build/SKILL.md")
    ref = _read("skills/build/references/requirement-writeback.md")
    assert "Size target vs required behaviour (autonomous runs)" in ref and "Ask only when no split is possible" in ref
