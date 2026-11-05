"""Build, autonomous run (e2e run 22): explicit brief value, hard requirement over a visible
extra, declared dev tooling -- decided by rule and recorded, not asked."""
from pathlib import Path

import pytest

pytestmark = pytest.mark.covers("FR-01.05/AC05")

ROOT = Path(__file__).resolve().parent.parent


def _flat(rel):
    return " ".join((ROOT / rel).read_text(encoding="utf-8").split())


def test_skill_decides_the_three_build_conflicts_by_rule():
    s = _flat("skills/build/SKILL.md")
    assert "Autonomous run, two more rules — decide, do not ask:" in s
    assert "--kind brief-wins|hard-constraint" in s and "known-differences.md" in s
    assert "--kind dev-tooling --command" in s and "exit 1 = undeclared (or an interactive run): ask" in s


def test_spec_reviewer_settles_by_rule_only_in_an_autonomous_run():
    r = _flat("agents/spec-reviewer.md")
    assert "Autonomous run: settle by rule, never escalate what a rule decides." in r
    assert "an interactive run keeps items 3 and 5 as written" in r
    assert "REJECTS as `unfaithful` (never `contradiction`), citing the brief line as the winner" in r
    assert "a tooltip-only placement does not satisfy it" in r
    assert "A hard requirement (no layout shift, no height change" in r
    assert "Only when no ranking is possible (both hard, or both extras) is it REJECT `contradiction`" in r


def test_writeback_reference_documents_both_rules():
    w = _flat("skills/build/references/requirement-writeback.md")
    assert "Explicit brief value and hard requirements (autonomous runs)." in w
    assert "--kind hard-constraint" in w and "NNN px" in w
