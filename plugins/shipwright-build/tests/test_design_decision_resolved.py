"""Build accepts a recorded `Design decision:` as resolved; only an unresolved contradiction stops."""
from pathlib import Path

import pytest

pytestmark = pytest.mark.covers("FR-01.05/AC05")

ROOT = Path(__file__).resolve().parent.parent


def _flat(rel):
    return " ".join((ROOT / rel).read_text(encoding="utf-8").split())


def test_skill_resolves_on_recorded_decision_and_stops_on_unresolved():
    s = _flat("skills/build/SKILL.md")
    assert "recorded `Design decision:` line in the section is resolved" in s
    assert "Only an unresolved `Design contradiction:`" in s
    assert "STOP and put it to a person" in s  # interactive / undecided behaviour unchanged


def test_spec_reviewer_passes_the_winner_and_rejects_the_other_side():
    r = _flat("agents/spec-reviewer.md")
    assert "follows the recorded winner PASSES" in r
    assert "follows the other side REJECTS as `unfaithful`" in r
    assert "REJECT with `kind: \"contradiction\"`" in r


def test_writeback_reference_documents_the_rule():
    w = _flat("skills/build/references/requirement-writeback.md")
    assert "Recorded `Design decision:` = resolved" in w and "rule cannot decide" in w
