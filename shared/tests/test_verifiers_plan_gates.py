"""The four Step-9 gates, as phase-completion checks.

`SKILL.md` Step 9 lists seven "verification gates (all must pass)"; four of
them existed only as instructions. These pin them as code, and pin the thing
a new hard gate must get right: a plan written before the format existed is
flagged, not stranded.
"""

import pytest

import sys
from pathlib import Path

# APPEND, never insert(0): shared/tests/ contains its own `tools/`
# directory, which shadows shared/scripts/tools when it comes first.
sys.path.append(str(Path(__file__).resolve().parent))
from _plan_gate_fixtures import LEGACY, WELL_FORMED, seed
from tools.verifiers.common import Severity
from tools.verifiers.plan_gate_checks import (
    check_fr_coverage_in_sections,
    check_section_dependency_order,
    check_section_quality,
    check_section_traces_to_requirement,
    find_planning_split_dirs,
)

def _ok(tmp_path):
    return seed(
        tmp_path,
        manifest="01-a\n02-b: 01-a",
        sections={
            "01-a": WELL_FORMED.format(name="01-a", frs="FR-01.01"),
            "02-b": WELL_FORMED.format(name="02-b", frs="FR-01.01"),
        },
    )


# --- nothing to verify ------------------------------------------------------

@pytest.mark.parametrize(
    "check",
    [
        check_section_dependency_order,
        check_fr_coverage_in_sections,
        check_section_traces_to_requirement,
        check_section_quality,
    ],
)
def test_a_project_with_no_plan_is_vacuously_green(tmp_path, check):
    assert check(tmp_path).ok is True


def test_find_planning_split_dirs_skips_iterate_and_dotdirs(tmp_path):
    planning = tmp_path / ".shipwright" / "planning"
    for name in ("01-auth", "iterate", ".hidden", "02-api"):
        d = planning / name
        d.mkdir(parents=True)
        (d / "plan.md").write_text("x", encoding="utf-8")
    (planning / "03-nothing").mkdir()
    assert [d.name for d in find_planning_split_dirs(tmp_path)] == ["01-auth", "02-api"]


# --- dependency order -------------------------------------------------------

def test_consistent_order_passes(tmp_path):
    r = check_section_dependency_order(_ok(tmp_path))
    assert r.ok is True
    assert "1 declared dependenc" in r.detail


def test_prerequisite_after_its_user_fails(tmp_path):
    root = seed(
        tmp_path,
        manifest="01-a: 02-b\n02-b",
        sections={
            "01-a": WELL_FORMED.format(name="01-a", frs="FR-01.01"),
            "02-b": WELL_FORMED.format(name="02-b", frs="FR-01.01"),
        },
    )
    r = check_section_dependency_order(root)
    assert r.ok is False
    assert r.severity == Severity.ERROR.value
    assert "numbered after it" in r.detail


def test_a_manifest_declaring_nothing_has_nothing_to_contradict(tmp_path):
    root = seed(
        tmp_path,
        manifest="03-c\n01-a\n02-b",
        sections={n: LEGACY.format(name=n) for n in ("01-a", "02-b", "03-c")},
    )
    assert check_section_dependency_order(root).ok is True


# --- FR coverage (AC6) and section trace (AC7) ------------------------------

def test_full_coverage_passes(tmp_path):
    root = _ok(tmp_path)
    assert check_fr_coverage_in_sections(root).ok is True
    assert check_section_traces_to_requirement(root).ok is True


def test_an_uncovered_requirement_fails(tmp_path):
    root = seed(
        tmp_path,
        manifest="01-a",
        sections={"01-a": WELL_FORMED.format(name="01-a", frs="FR-01.01")},
        frs=("FR-01.01", "FR-01.02"),
    )
    r = check_fr_coverage_in_sections(root)
    assert r.ok is False
    assert r.severity == Severity.ERROR.value
    assert "FR-01.02" in r.detail


def test_a_section_nobody_asked_for_fails(tmp_path):
    root = seed(
        tmp_path,
        manifest="01-a\n02-b",
        sections={
            "01-a": WELL_FORMED.format(name="01-a", frs="FR-01.01"),
            "02-b": LEGACY.format(name="02-b"),   # declares no requirement
        },
    )
    r = check_section_traces_to_requirement(root)
    assert r.ok is False
    assert r.severity == Severity.ERROR.value
    assert "02-b" in r.detail


def test_a_section_naming_only_a_dead_id_fails_and_says_which(tmp_path):
    root = seed(
        tmp_path,
        manifest="01-a\n02-b",
        sections={
            "01-a": WELL_FORMED.format(name="01-a", frs="FR-01.01"),
            "02-b": WELL_FORMED.format(name="02-b", frs="FR-09.99"),
        },
    )
    r = check_section_traces_to_requirement(root)
    assert r.ok is False
    assert "FR-09.99" in r.detail


# --- a plan written before the format is flagged, not stranded (AC11) -------

def _legacy_split(tmp_path):
    return seed(
        tmp_path,
        manifest="01-a\n02-b",
        sections={n: LEGACY.format(name=n) for n in ("01-a", "02-b")},
    )


@pytest.mark.parametrize(
    "check", [check_fr_coverage_in_sections, check_section_traces_to_requirement]
)
def test_a_split_that_never_adopted_the_field_warns(tmp_path, check):
    r = check(_legacy_split(tmp_path))
    assert r.ok is False
    assert r.severity == Severity.WARNING.value
    assert r.strict_exempt is True          # --strict must not mass-false-red
    assert "section-index.md" in r.detail   # …and it names the migration


def test_one_adopting_section_holds_the_whole_split_to_the_format(tmp_path):
    root = seed(
        tmp_path,
        manifest="01-a\n02-b",
        sections={
            "01-a": WELL_FORMED.format(name="01-a", frs="FR-01.01"),
            "02-b": LEGACY.format(name="02-b"),
        },
    )
    r = check_section_traces_to_requirement(root)
    assert r.severity == Severity.ERROR.value


def test_a_legacy_split_is_not_warned_when_it_is_actually_complete(tmp_path):
    """Leniency is for what the format cannot know, not a blanket pass: a
    legacy split whose sections are well-formed still passes outright."""
    root = seed(
        tmp_path,
        manifest="01-a\n02-b",
        sections={n: LEGACY.format(name=n) for n in ("01-a", "02-b")},
    )
    assert check_section_quality(root).ok is True


# --- section quality (AC8) --------------------------------------------------

def test_well_formed_sections_pass(tmp_path):
    assert check_section_quality(_ok(tmp_path)).ok is True


def test_a_section_missing_its_test_strategy_fails(tmp_path):
    root = seed(
        tmp_path,
        manifest="01-a",
        sections={
            "01-a": (
                "# Section: 01-a\n\nRequirements: FR-01.01\n\n"
                "## Overview\nx\n\n## Implementation Steps\n1. one\n2. two\n"
            )
        },
    )
    r = check_section_quality(root)
    assert r.ok is False
    assert r.severity == Severity.ERROR.value
    assert "Tests First" in r.detail


def test_a_split_using_no_recognised_heading_only_warns(tmp_path):
    root = seed(
        tmp_path,
        manifest="01-a",
        sections={"01-a": "# Section: 01-a\n\nRequirements: FR-01.01\n\nJust prose.\n"},
    )
    r = check_section_quality(root)
    assert r.ok is False
    assert r.severity == Severity.WARNING.value
    assert r.strict_exempt is True
    assert "section-index.md" in r.detail


def test_heading_adoption_is_decided_per_split_not_per_section(tmp_path):
    """One modern section makes the whole split adopting, so the prose one
    beside it is a real failure — the same rule the Requirements field uses.
    Deciding per section would let one unrecognised file hide as legacy."""
    root = seed(
        tmp_path,
        manifest="01-a\n02-b",
        sections={
            "01-a": WELL_FORMED.format(name="01-a", frs="FR-01.01"),
            "02-b": "# Section: 02-b\n\nRequirements: FR-01.01\n\nJust prose.\n",
        },
    )
    r = check_section_quality(root)
    assert r.ok is False
    assert r.severity == Severity.ERROR.value
    assert "02-b" in r.detail
