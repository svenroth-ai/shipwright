"""What a section must say, and the two directions of requirement coverage.

`SKILL.md` Step 9 has long listed a "Section Quality Gate" and an "FR Coverage
Check" among its verification gates. Neither existed in code, and the FR check
that did exist looked only outward (a cited FR must exist) — nothing checked
that every requirement is covered, or that a section traces back to a
requirement at all, so a plan could quietly add work nobody asked for.

Linkage is read from one explicit ``Requirements:`` field. Scanning prose for
``FR-NN.NN`` was rejected: an id named in an example or a rationale would count
as coverage, and authors would learn to sprinkle ids to satisfy the gate.
"""

from pathlib import Path

import pytest

from lib.plan_section_quality import (
    coverage_report,
    parse_section_file,
    quality_problems,
)

GOOD = """# Section: 02-api

Requirements: FR-01.03, FR-01.05

## Overview
Exposes the planning artifacts over HTTP.

## Implementation Steps
1. Add the route module.
2. Wire the serializer.
3. Register the blueprint.

## Tests First
- unit: serializer round-trip
"""


def _write(tmp_path: Path, name: str, body: str) -> Path:
    p = tmp_path / f"{name}.md"
    p.write_text(body, encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# parse_section_file
# ---------------------------------------------------------------------------


def test_a_well_formed_section_parses(tmp_path):
    s = parse_section_file(_write(tmp_path, "02-api", GOOD))
    assert s.name == "02-api"
    assert s.has_purpose
    assert s.step_count == 3
    assert s.has_tests
    assert s.requirements == ("FR-01.03", "FR-01.05")
    assert s.declares_requirements
    assert quality_problems(s) == []


@pytest.mark.parametrize("heading", ["Overview", "Purpose", "Description", "Goal"])
def test_purpose_heading_synonyms(tmp_path, heading):
    s = parse_section_file(_write(tmp_path, "01-a", f"# S\n\n## {heading}\nWhy it exists.\n"))
    assert s.has_purpose


@pytest.mark.parametrize("heading", ["Implementation Steps", "Implementation", "Steps"])
def test_steps_heading_synonyms(tmp_path, heading):
    body = f"# S\n\n## {heading}\n1. one\n2. two\n"
    assert parse_section_file(_write(tmp_path, "01-a", body)).step_count == 2


@pytest.mark.parametrize("heading", ["Tests First", "Test Strategy", "Tests", "Testing"])
def test_test_heading_synonyms(tmp_path, heading):
    s = parse_section_file(_write(tmp_path, "01-a", f"# S\n\n## {heading}\n- a unit test\n"))
    assert s.has_tests


def test_bullet_and_numbered_steps_both_count(tmp_path):
    body = "# S\n\n## Implementation Steps\n- one\n* two\n+ three\n1) four\n"
    assert parse_section_file(_write(tmp_path, "01-a", body)).step_count == 4


def test_an_empty_heading_body_is_not_a_purpose(tmp_path):
    body = "# S\n\n## Overview\n\n## Implementation Steps\n1. one\n2. two\n"
    assert parse_section_file(_write(tmp_path, "01-a", body)).has_purpose is False


def test_prose_mentioning_an_fr_is_not_a_declaration(tmp_path):
    body = "# S\n\n## Overview\nThis is like FR-01.03 but is not it.\n"
    s = parse_section_file(_write(tmp_path, "01-a", body))
    assert s.requirements == ()
    assert s.declares_requirements is False


def test_requirements_field_tolerates_markdown(tmp_path):
    for line in ("**Requirements:** FR-01.03", "- Requirements: FR-01.03", "requirements:  FR-01.03"):
        s = parse_section_file(_write(tmp_path, "01-a", f"# S\n\n{line}\n"))
        assert s.requirements == ("FR-01.03",), line


def test_an_empty_requirements_field_counts_as_adopting_but_names_nothing(tmp_path):
    s = parse_section_file(_write(tmp_path, "01-a", "# S\n\nRequirements:\n\n## Overview\nx\n"))
    assert s.declares_requirements is True
    assert s.requirements == ()


def test_a_token_that_merely_contains_an_fr_id_is_malformed_not_coverage(tmp_path):
    """An unanchored search credits FR-01.01x and not-FR-02.02-example as live
    ids, letting a typo in the explicit field satisfy both coverage
    directions. The repo has been bitten by this exact shape before."""
    body = "# S\n\nRequirements: FR-01.01x, not-FR-02.02-example, FR-01.03\n"
    s = parse_section_file(_write(tmp_path, "01-a", body))
    assert s.requirements == ("FR-01.03",)
    assert s.malformed_requirements == ("FR-01.01x", "not-FR-02.02-example")


def test_malformed_tokens_are_reported_as_linkage_errors(tmp_path):
    s = parse_section_file(_write(tmp_path, "01-a", "# S\n\nRequirements: FR-9.9.9\n"))
    rep = coverage_report([s], {"FR-01.01"})
    assert rep.untraced_sections == ["01-a"]
    assert any("not an FR id" in r for r in rep.unknown_refs["01-a"])


def test_a_missing_file_yields_an_empty_section(tmp_path):
    s = parse_section_file(tmp_path / "nope.md")
    assert s.step_count == 0 and not s.has_purpose


# ---------------------------------------------------------------------------
# quality_problems — AC8
# ---------------------------------------------------------------------------


def test_missing_purpose_is_named(tmp_path):
    body = "# S\n\n## Implementation Steps\n1. a\n2. b\n\n## Tests First\n- t\n"
    problems = quality_problems(parse_section_file(_write(tmp_path, "01-a", body)))
    assert any("what it is for" in p for p in problems)
    assert any("Overview" in p for p in problems)  # names the heading it wanted


def test_one_step_is_not_enough(tmp_path):
    body = "# S\n\n## Overview\nx\n\n## Implementation Steps\n1. only one\n\n## Tests First\n- t\n"
    problems = quality_problems(parse_section_file(_write(tmp_path, "01-a", body)))
    assert any("2 implementation steps" in p for p in problems)


def test_missing_test_strategy_is_named(tmp_path):
    body = "# S\n\n## Overview\nx\n\n## Implementation Steps\n1. a\n2. b\n"
    problems = quality_problems(parse_section_file(_write(tmp_path, "01-a", body)))
    assert any("tested" in p for p in problems)


def test_a_section_in_an_unrecognised_shape_reports_all_three(tmp_path):
    s = parse_section_file(_write(tmp_path, "01-a", "# S\n\nJust prose, no headings.\n"))
    assert len(quality_problems(s)) == 3
    assert s.uses_known_shape is False


def test_uses_known_shape_is_true_once_any_part_is_present(tmp_path):
    s = parse_section_file(_write(tmp_path, "01-a", "# S\n\n## Overview\nx\n"))
    assert s.uses_known_shape is True


# ---------------------------------------------------------------------------
# coverage_report — AC6 (every requirement lands) and AC7 (every section traces)
# ---------------------------------------------------------------------------


def _sections(tmp_path, spec: dict[str, str]):
    return [parse_section_file(_write(tmp_path, n, b)) for n, b in spec.items()]


def test_full_coverage_both_ways(tmp_path):
    sections = _sections(tmp_path, {
        "01-a": "# a\nRequirements: FR-01.01\n",
        "02-b": "# b\nRequirements: FR-01.02, FR-01.03\n",
    })
    rep = coverage_report(sections, {"FR-01.01", "FR-01.02", "FR-01.03"})
    assert rep.uncovered_frs == []
    assert rep.untraced_sections == []
    assert rep.adopted is True


def test_a_requirement_no_section_claims_is_uncovered(tmp_path):
    sections = _sections(tmp_path, {"01-a": "# a\nRequirements: FR-01.01\n"})
    rep = coverage_report(sections, {"FR-01.01", "FR-01.02"})
    assert rep.uncovered_frs == ["FR-01.02"]


def test_a_section_claiming_nothing_is_untraced(tmp_path):
    sections = _sections(tmp_path, {
        "01-a": "# a\nRequirements: FR-01.01\n",
        "02-b": "# b\n## Overview\nwork nobody asked for\n",
    })
    rep = coverage_report(sections, {"FR-01.01"})
    assert rep.untraced_sections == ["02-b"]


def test_a_section_claiming_only_non_live_ids_is_untraced(tmp_path):
    sections = _sections(tmp_path, {"01-a": "# a\nRequirements: FR-09.99\n"})
    rep = coverage_report(sections, {"FR-01.01"})
    assert rep.untraced_sections == ["01-a"]
    assert rep.unknown_refs == {"01-a": ["FR-09.99"]}


def test_an_empty_field_beside_an_absent_one_still_adopts_the_split(tmp_path):
    """Writing the field and leaving it empty is adopting the format and
    failing it — it must not buy the split legacy leniency."""
    sections = _sections(tmp_path, {
        "01-a": "# a\nRequirements:\n",             # adopted, names nothing
        "02-b": "# b\n## Overview\nx\n",            # no field at all
    })
    rep = coverage_report(sections, {"FR-01.01"})
    assert rep.adopted is True
    assert rep.untraced_sections == ["01-a", "02-b"]


def test_a_split_that_never_uses_the_field_is_not_adopted(tmp_path):
    sections = _sections(tmp_path, {
        "01-a": "# a\n## Overview\nx\n",
        "02-b": "# b\n## Overview\ny\n",
    })
    rep = coverage_report(sections, {"FR-01.01"})
    assert rep.adopted is False
    # …but the facts are still reported, so a lenient caller can WARN with them.
    assert rep.uncovered_frs == ["FR-01.01"]
    assert rep.untraced_sections == ["01-a", "02-b"]


def test_one_adopting_section_makes_the_whole_split_adopted(tmp_path):
    sections = _sections(tmp_path, {
        "01-a": "# a\nRequirements: FR-01.01\n",
        "02-b": "# b\n## Overview\nx\n",
    })
    rep = coverage_report(sections, {"FR-01.01"})
    assert rep.adopted is True
    assert rep.untraced_sections == ["02-b"]


def test_no_live_requirements_means_nothing_to_cover(tmp_path):
    sections = _sections(tmp_path, {"01-a": "# a\nRequirements: FR-01.01\n"})
    rep = coverage_report(sections, set())
    assert rep.uncovered_frs == []


def test_report_lists_are_sorted_for_stable_diagnostics(tmp_path):
    sections = _sections(tmp_path, {"02-b": "# b\n", "01-a": "# a\n"})
    rep = coverage_report(sections, {"FR-01.02", "FR-01.01"})
    assert rep.uncovered_frs == ["FR-01.01", "FR-01.02"]
    assert rep.untraced_sections == ["01-a", "02-b"]
