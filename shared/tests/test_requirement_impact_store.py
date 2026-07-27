"""Storage tests for the requirement-impact declaration.

Split from ``test_requirement_impact.py`` (which covers the pure rule) along the
same seam as the modules themselves: this file is about *identity on disk* and
*what a damaged record does*, both of which the external review flagged as the
weak points of the original single-append-log design.

Origin: trg-e9e5188e (FR-01.04, FR-01.05).
"""

from __future__ import annotations

from lib.requirement_impact_store import (
    DECLARATION_DIRNAME,
    declaration_dir,
    declaration_filename,
    find_declaration,
    read_declarations,
)


def _write_decl(directory, run_id, phase, scope, reason="appearance only"):
    directory.mkdir(parents=True, exist_ok=True)
    (directory / declaration_filename(run_id, phase, scope)).write_text(
        f'{{"run_id": "{run_id}", "phase": "{phase}", "scope": "{scope}", '
        f'"impact": "none", "reason": "{reason}"}}',
        encoding="utf-8")


# --------------------------------------------------------------------------
# declaration_filename — identity is (run_id, phase, scope)
# --------------------------------------------------------------------------

def test_filename_encodes_full_identity():
    name = declaration_filename("iterate-2026-07-27-x", "design", "round-2")
    assert "iterate-2026-07-27-x" in name
    assert "design" in name
    assert "round-2" in name
    assert name.endswith(".json")


def test_same_scope_in_different_runs_gets_different_files():
    """A stale 'round-1' from an earlier run must never satisfy this run (GPT-1)."""
    assert (declaration_filename("run-a", "design", "round-1")
            != declaration_filename("run-b", "design", "round-1"))


def test_same_scope_in_different_phases_gets_different_files():
    assert (declaration_filename("run-a", "design", "01-auth")
            != declaration_filename("run-a", "build", "01-auth"))


def test_filename_is_path_safe():
    name = declaration_filename("a/../b", "build", "sections/01 auth")
    assert "/" not in name and "\\" not in name and ".." not in name


def test_filename_survives_empty_components():
    assert declaration_filename("", "build", "").endswith(".json")


def test_declaration_dir_is_under_canonical_planning_home(tmp_path):
    assert DECLARATION_DIRNAME.startswith(".shipwright/planning/")
    assert declaration_dir(tmp_path).name == "requirement-impact"


# --------------------------------------------------------------------------
# read_declarations — damage is named, never silently skipped (GPT-5)
# --------------------------------------------------------------------------

def test_read_declarations_returns_records_and_problems(tmp_path):
    d = tmp_path / "requirement-impact"
    _write_decl(d, "run-a", "design", "round-1", reason="colour only")
    (d / "run-a__design__round-2.json").write_text("{not json", encoding="utf-8")

    records, problems = read_declarations(d)

    assert [r["scope"] for r in records] == ["round-1"]
    assert len(problems) == 1
    assert "round-2" in problems[0]["path"]
    assert "invalid JSON" in problems[0]["error"]


def test_read_declarations_flags_merge_conflict_markers(tmp_path):
    """A conflicted file must say 'repair me', not look like 'never declared'."""
    d = tmp_path / "requirement-impact"
    d.mkdir()
    (d / "run-a__build__01-auth.json").write_text(
        '<<<<<<< HEAD\n{"a": 1}\n=======\n{"a": 2}\n>>>>>>> other\n',
        encoding="utf-8")

    records, problems = read_declarations(d)

    assert records == []
    assert "conflict" in problems[0]["error"].lower()


def test_read_declarations_flags_non_object_json(tmp_path):
    d = tmp_path / "requirement-impact"
    d.mkdir()
    (d / "run-a__build__01-auth.json").write_text("[1, 2, 3]", encoding="utf-8")

    records, problems = read_declarations(d)

    assert records == []
    assert "not a JSON object" in problems[0]["error"]


def test_read_declarations_ignores_non_json_files(tmp_path):
    d = tmp_path / "requirement-impact"
    _write_decl(d, "run-a", "design", "round-1")
    (d / "README.md").write_text("not a declaration", encoding="utf-8")

    records, problems = read_declarations(d)

    assert len(records) == 1 and problems == []


def test_read_declarations_on_missing_dir_is_empty_not_an_error(tmp_path):
    records, problems = read_declarations(tmp_path / "nope")
    assert records == [] and problems == []


# --------------------------------------------------------------------------
# find_declaration — the design-finalization gate's lookup
# --------------------------------------------------------------------------

def test_find_declaration_matches_exact_identity(tmp_path):
    d = tmp_path / "requirement-impact"
    _write_decl(d, "run-a", "design", "round-1")
    found, problems = find_declaration(d, run_id="run-a", phase="design", scope="round-1")
    assert found["reason"] == "appearance only"
    assert problems == []


def test_find_declaration_does_not_match_another_run(tmp_path):
    """The AC-4 gate must not be satisfied by a previous run's round (GPT-1)."""
    d = tmp_path / "requirement-impact"
    _write_decl(d, "run-a", "design", "round-1")
    found, _ = find_declaration(d, run_id="run-b", phase="design", scope="round-1")
    assert found is None


def test_find_declaration_does_not_match_another_phase(tmp_path):
    d = tmp_path / "requirement-impact"
    _write_decl(d, "run-a", "design", "round-1")
    found, _ = find_declaration(d, run_id="run-a", phase="build", scope="round-1")
    assert found is None


def test_find_declaration_on_empty_dir_is_none(tmp_path):
    found, problems = find_declaration(tmp_path, run_id="r", phase="design", scope="s")
    assert found is None and problems == []


def test_find_declaration_surfaces_damage_instead_of_reporting_absence(tmp_path):
    """A corrupt record must not read as 'you never declared this'."""
    d = tmp_path / "requirement-impact"
    d.mkdir()
    (d / "run-a__build__01-auth__deadbeef.json").write_text("{broken", encoding="utf-8")

    found, problems = find_declaration(d, run_id="run-a", phase="build", scope="01-auth")

    assert found is None
    assert len(problems) == 1 and "invalid JSON" in problems[0]["error"]


def test_a_reason_containing_equals_signs_is_not_mistaken_for_a_conflict(tmp_path):
    """Anchored marker detection — an unanchored scan condemns valid records."""
    d = tmp_path / "requirement-impact"
    d.mkdir()
    (d / "run-a__design__round-1__deadbeef.json").write_text(
        '{"run_id": "run-a", "phase": "design", "scope": "round-1", '
        '"impact": "none", "reason": "divider ======= in the copy, appearance only"}',
        encoding="utf-8")

    records, problems = read_declarations(d)

    assert problems == []
    assert len(records) == 1


def test_sanitization_collisions_get_distinct_filenames():
    """`round/1` and `round-1` sanitize alike; the digest keeps them apart."""
    assert (declaration_filename("run-a", "design", "round/1")
            != declaration_filename("run-a", "design", "round-1"))
