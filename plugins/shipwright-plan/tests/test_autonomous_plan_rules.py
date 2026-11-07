"""Plan, autonomous run (e2e run 22): an explicit brief value wins over plan text and screens,
declared dev tooling is a plain Build step, and earlier phases' files never trip the boundary gate."""
from pathlib import Path

import pytest

pytestmark = pytest.mark.covers("FR-01.03/AC17")

ROOT = Path(__file__).resolve().parent.parent


def _flat(rel):
    return " ".join((ROOT / rel).read_text(encoding="utf-8").split())


def test_section_writer_brief_precedence_and_dev_tooling():
    w = _flat("agents/section-writer.md")
    assert "An explicit brief value wins over plan/section text AND over the screens" in w
    assert "including one no screen shows" in w and "a tooltip-only placement does not satisfy it" in w
    assert "the brief is silent or contradicts itself on the point AND no screen covers it" in w
    assert "Dev tooling, autonomous run" in w and 'Never write "the master/operator decides"' in w
    assert "Real contradictions, interactive run" in w  # interactive behaviour unchanged


def test_boundary_baseline_is_documented_where_the_agent_reads_it():
    step9 = _flat("skills/plan/references/step-9-completion.md")
    assert "never ask to commit earlier phases' output to clear this gate" in step9
    assert "On `not_written`" in step9 and "handled as before" in step9
    assert '--project-root "$(pwd)"' in _flat("skills/plan/references/first-actions.md")
