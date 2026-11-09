"""An autonomous run settles a screenshot fail caused by a brief-required element by rule (run 27, phone screen)."""

from pathlib import Path

REF = Path(__file__).resolve().parents[1] / "skills" / "test" / "references" / "step-3.7b-screenshot-check.md"


def test_brief_element_fail_is_settled_by_precedence_not_asked():
    text = REF.read_text(encoding="utf-8")
    assert "--kind precedence --winner brief --loser approved-screen" in text
    assert "(c) A `fail` that remains" in text
    assert "never overrides a screenshot result" in text  # the no-waiver sentence stays
