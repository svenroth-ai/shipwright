"""SECTION_MANIFEST parsing + dependency-order rule.

The manifest is the plan phase's build order. Before this module it was a flat
list of names, so "the numbering is the build order" was a promise nothing
could check. A section may now name what it presupposes, which turns the
promise into an oracle: a numbering that places a prerequisite after its user
fails here.
"""

from pathlib import Path

import pytest

from lib.plan_manifest import (
    SECTION_NAME_RE,
    parse_manifest,
    parse_manifest_text,
    validate_dependency_order,
)


def _plan(tmp_path: Path, body: str) -> Path:
    plan = tmp_path / "plan.md"
    plan.write_text(
        f"<!-- SECTION_MANIFEST\n{body}\nEND_MANIFEST -->\n\n# Plan\n",
        encoding="utf-8",
    )
    return plan


# ---------------------------------------------------------------------------
# Backward compatibility — every manifest written before dependencies existed
# ---------------------------------------------------------------------------


def test_bare_manifest_still_parses(tmp_path):
    res = parse_manifest(_plan(tmp_path, "01-auth\n02-api\n03-frontend"))
    assert res.is_valid
    assert res.sections == ["01-auth", "02-api", "03-frontend"]
    assert res.dependencies == {"01-auth": [], "02-api": [], "03-frontend": []}


def test_missing_plan_file_is_an_error_not_a_crash(tmp_path):
    res = parse_manifest(tmp_path / "nope.md")
    assert not res.is_valid
    assert "not found" in res.errors[0].lower()


def test_absent_manifest_block(tmp_path):
    plan = tmp_path / "plan.md"
    plan.write_text("# Just a plan\n", encoding="utf-8")
    res = parse_manifest(plan)
    assert not res.is_valid
    assert "No SECTION_MANIFEST" in res.errors[0]


def test_empty_manifest_block(tmp_path):
    res = parse_manifest(_plan(tmp_path, ""))
    assert not res.is_valid


def test_invalid_section_name_keeps_the_historic_wording(tmp_path):
    # plugins/shipwright-plan/tests/test_sections.py asserts on "Invalid".
    res = parse_manifest(_plan(tmp_path, "01-auth\nBad Name"))
    assert not res.is_valid
    assert any("Invalid" in e for e in res.errors)


def test_comment_lines_are_skipped(tmp_path):
    res = parse_manifest(_plan(tmp_path, "# ordering note\n01-auth\n02-api"))
    assert res.is_valid
    assert res.sections == ["01-auth", "02-api"]


# ---------------------------------------------------------------------------
# The declaration format
# ---------------------------------------------------------------------------


def test_dependencies_are_parsed(tmp_path):
    res = parse_manifest(_plan(tmp_path, "01-auth\n02-db\n03-api: 01-auth, 02-db"))
    assert res.is_valid
    assert res.dependencies["03-api"] == ["01-auth", "02-db"]
    assert res.dependencies["01-auth"] == []


@pytest.mark.parametrize(
    "body",
    [
        "01-auth\n02-api:01-auth",          # no space after colon
        "01-auth\n02-api :  01-auth  ",     # space before colon, padded value
        "01-auth\n02-api: 01-auth,",        # trailing comma
    ],
)
def test_whitespace_and_trailing_comma_tolerated(tmp_path, body):
    res = parse_manifest(_plan(tmp_path, body))
    assert res.is_valid, res.errors
    assert res.dependencies["02-api"] == ["01-auth"]


def test_entries_carry_their_manifest_line_number(tmp_path):
    res = parse_manifest(_plan(tmp_path, "01-auth\n02-api: 01-auth"))
    assert [e.line_no for e in res.entries] == [1, 2]


def test_empty_dependency_token_rejected(tmp_path):
    res = parse_manifest(_plan(tmp_path, "01-auth\n02-api: 01-auth, , 01-auth"))
    assert not res.is_valid
    assert any("empty dependency" in e for e in res.errors)


def test_duplicate_dependency_token_rejected(tmp_path):
    res = parse_manifest(_plan(tmp_path, "01-auth\n02-api: 01-auth, 01-auth"))
    assert not res.is_valid
    assert any("duplicate dependency" in e for e in res.errors)


def test_duplicate_section_id_rejected(tmp_path):
    res = parse_manifest(_plan(tmp_path, "01-auth\n01-auth"))
    assert not res.is_valid
    assert any("duplicate section" in e for e in res.errors)


def test_dependency_must_match_the_section_grammar(tmp_path):
    # A path traversal payload is not a section id.
    res = parse_manifest(_plan(tmp_path, "01-auth\n02-api: ../../etc/passwd"))
    assert not res.is_valid
    assert any("Invalid dependency" in e for e in res.errors)


def test_errors_name_the_manifest_line(tmp_path):
    res = parse_manifest(_plan(tmp_path, "01-auth\n02-api: 01-auth, 01-auth"))
    assert any("line 2" in e for e in res.errors)


# ---------------------------------------------------------------------------
# The order rule — what the declaration buys
# ---------------------------------------------------------------------------


def test_prerequisite_before_its_user_passes(tmp_path):
    res = parse_manifest(_plan(tmp_path, "01-auth\n02-db\n03-api: 01-auth, 02-db"))
    assert validate_dependency_order(res.entries) == []


def test_prerequisite_after_its_user_fails(tmp_path):
    res = parse_manifest(_plan(tmp_path, "01-api: 02-db\n02-db"))
    errors = validate_dependency_order(res.entries)
    assert errors
    assert "02-db" in errors[0] and "01-api" in errors[0]


def test_dependency_on_an_undeclared_section_fails(tmp_path):
    res = parse_manifest(_plan(tmp_path, "01-auth\n02-api: 09-ghost"))
    errors = validate_dependency_order(res.entries)
    assert any("09-ghost" in e and "not declared" in e for e in errors)


def test_self_dependency_fails(tmp_path):
    res = parse_manifest(_plan(tmp_path, "01-auth\n02-api: 02-api"))
    errors = validate_dependency_order(res.entries)
    assert any("itself" in e for e in errors)


def test_a_cycle_cannot_satisfy_the_order_rule(tmp_path):
    # No explicit cycle detector: "every dependency is earlier" subsumes it.
    res = parse_manifest(_plan(tmp_path, "01-a: 02-b\n02-b: 01-a"))
    assert validate_dependency_order(res.entries)


def test_order_errors_name_their_line(tmp_path):
    res = parse_manifest(_plan(tmp_path, "01-api: 02-db\n02-db"))
    assert all("line " in e for e in validate_dependency_order(res.entries))


def test_bare_manifest_has_no_order_errors(tmp_path):
    """A plan written before dependencies existed declares none, so the order
    rule is vacuously satisfied — no migration is required of it."""
    res = parse_manifest(_plan(tmp_path, "03-api\n01-auth\n02-db"))
    assert validate_dependency_order(res.entries) == []


# ---------------------------------------------------------------------------
# Grammar + text entry point
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["01-auth", "02-api-v2", "10-a1b2"])
def test_grammar_accepts(name):
    assert SECTION_NAME_RE.match(name)


@pytest.mark.parametrize(
    "name", ["1-auth", "01_auth", "01-Auth", "auth", "01-", "01-auth-", "../01-auth"]
)
def test_grammar_rejects(name):
    assert not SECTION_NAME_RE.match(name)


def test_parse_manifest_text_is_the_same_parser(tmp_path):
    text = "<!-- SECTION_MANIFEST\n01-a\n02-b: 01-a\nEND_MANIFEST -->"
    from_text = parse_manifest_text(text)
    from_file = parse_manifest(_plan(tmp_path, "01-a\n02-b: 01-a"))
    assert from_text.sections == from_file.sections
    assert from_text.dependencies == from_file.dependencies
