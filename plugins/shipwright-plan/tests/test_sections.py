"""Tests for shipwright-plan sections module."""

from lib.sections import (
    get_missing_sections,
    get_section_files,
    parse_section_manifest,
)


def test_parse_valid_manifest(planning_with_plan):
    result = parse_section_manifest(planning_with_plan / "plan.md")
    assert result.is_valid
    assert result.sections == ["01-auth", "02-api", "03-frontend"]


def test_parse_missing_plan(tmp_path):
    result = parse_section_manifest(tmp_path / "nonexistent.md")
    assert not result.is_valid


def test_parse_no_manifest_block(tmp_path):
    plan = tmp_path / "plan.md"
    plan.write_text("# Just a plan\n")
    result = parse_section_manifest(plan)
    assert not result.is_valid
    assert "No SECTION_MANIFEST" in result.errors[0]


def test_parse_invalid_section_name(tmp_path):
    plan = tmp_path / "plan.md"
    plan.write_text("<!-- SECTION_MANIFEST\n01-auth\nBad Name\nEND_MANIFEST -->\n")
    result = parse_section_manifest(plan)
    assert not result.is_valid
    assert any("Invalid" in e for e in result.errors)


def test_get_section_files_empty(tmp_planning):
    files = get_section_files(tmp_planning)
    assert files == []


def test_get_section_files(planning_with_sections):
    files = get_section_files(planning_with_sections)
    assert files == ["01-auth", "02-api", "03-frontend"]


def test_get_missing_sections(planning_with_plan):
    # No sections written yet
    missing = get_missing_sections(planning_with_plan, ["01-auth", "02-api", "03-frontend"])
    assert missing == ["01-auth", "02-api", "03-frontend"]


def test_get_missing_sections_partial(planning_with_plan):
    # Write one section
    sections = planning_with_plan / "sections"
    sections.mkdir(exist_ok=True)
    (sections / "01-auth.md").write_text("# Section\n")

    missing = get_missing_sections(planning_with_plan, ["01-auth", "02-api"])
    assert missing == ["02-api"]
