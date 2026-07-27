"""Unit tests for the requirement-impact declaration predicates.

The mechanism the change workflow already runs — declare a requirement impact,
then refuse to finish unless a requirements file was touched or a one-line
reason was given for touching none — given to the design feedback round and the
build section (trg-e9e5188e; FR-01.04, FR-01.05).

These cover the pure **rule**. Identity and damage-on-disk live in
``test_requirement_impact_store.py``; the git-derived touch evidence and the CLI
write boundary live in ``test_record_requirement_impact.py``.
"""

from __future__ import annotations

import pytest

from lib.requirement_impact import (
    PHASE_VALUES,
    declaration_error,
    is_requirement_spec,
    normalize_extras,
    touch_error,
)


# --------------------------------------------------------------------------
# is_requirement_spec — what counts as "a requirements file was touched"
# --------------------------------------------------------------------------

@pytest.mark.parametrize("path", [
    ".shipwright/planning/01-adopted/spec.md",
    ".shipwright/planning/02-billing/spec.md",
    ".shipwright/planning/a/b/c/spec.md",
    ".shipwright\\planning\\01-adopted\\spec.md",  # Windows separators
    "./.shipwright/planning/01-adopted/spec.md",
])
def test_requirement_spec_recognized(path):
    assert is_requirement_spec(path) is True


@pytest.mark.parametrize("path", [
    ".shipwright/planning/iterate/2026-07-27-thing.md",   # an iterate spec is not an FR spec
    ".shipwright/planning/spec.md",                        # needs a split directory
    ".shipwright/designs/screens/01-login.html",
    "src/spec.md",
    # Deliberate negative case: the pre-migration path must NOT be accepted.
    "planning/01-adopted/spec.md",  # artifact-path-canon: legacy
    ".shipwright/planning/01-adopted/spec.md.bak",
    "",
    None,
])
def test_non_requirement_paths_rejected(path):
    assert is_requirement_spec(path) is False


def test_spec_md_directory_name_is_not_a_spec_file():
    """A path *under* something called spec.md is not itself the spec."""
    assert is_requirement_spec(".shipwright/planning/01/spec.md/nested.md") is False


# --------------------------------------------------------------------------
# declaration_error — is the declaration itself well-formed?
# --------------------------------------------------------------------------

def _decl(**over):
    base = dict(
        run_id="iterate-2026-07-27-x",
        phase="design",
        scope="round-2",
        impact="none",
        reason="feedback was appearance-only: spacing and colour tokens",
        frs=[],
        extras=[],
    )
    base.update(over)
    return base


def test_valid_none_declaration_passes():
    assert declaration_error(**_decl()) is None


def test_valid_behavior_declaration_passes():
    assert declaration_error(**_decl(impact="modify", reason=None,
                                     frs=["FR-01.04"])) is None


def test_impact_outside_vocabulary_rejected():
    err = declaration_error(**_decl(impact="tweak"))
    assert err["error"] == "requirement_impact_invalid_impact"


def test_none_without_reason_rejected():
    """The whole point of the mechanism: 'none' costs one line of justification."""
    err = declaration_error(**_decl(reason=None))
    assert err["error"] == "requirement_impact_none_requires_reason"


def test_none_with_blank_reason_rejected():
    assert declaration_error(**_decl(reason="   "))["error"] == \
        "requirement_impact_none_requires_reason"


def test_none_with_multiline_reason_rejected():
    """One LINE — a wall of text is how this check gets defeated in practice."""
    err = declaration_error(**_decl(reason="because\nof reasons"))
    assert err["error"] == "requirement_impact_none_requires_reason"


def test_behavior_affecting_without_fr_rejected():
    err = declaration_error(**_decl(impact="modify", reason=None, frs=[]))
    assert err["error"] == "requirement_impact_requires_fr"


@pytest.mark.parametrize("bad", ["FR", "FR-1", "01.04", "FR-01", "FR-01.04.05",
                                 "fr-01.04", "FR-01.04 ", 17, None])
def test_malformed_fr_id_rejected(bad):
    """'at least one FR' must mean an FR id, not any non-empty string (GPT-7)."""
    err = declaration_error(**_decl(impact="add", reason=None, frs=[bad]))
    assert err["error"] == "requirement_impact_malformed_fr"


@pytest.mark.parametrize("good", ["FR-01.04", "FR-1.4", "FR-123.456"])
def test_wellformed_fr_ids_accepted(good):
    assert declaration_error(**_decl(impact="add", reason=None, frs=[good])) is None


def test_unknown_phase_rejected():
    err = declaration_error(**_decl(phase="deploy"))
    assert err["error"] == "requirement_impact_invalid_phase"


def test_known_phases_are_design_and_build():
    assert set(PHASE_VALUES) == {"design", "build"}


def test_blank_scope_rejected():
    assert declaration_error(**_decl(scope="  "))["error"] == \
        "requirement_impact_invalid_scope"


def test_blank_run_id_rejected():
    assert declaration_error(**_decl(run_id=""))["error"] == \
        "requirement_impact_invalid_run_id"


# --------------------------------------------------------------------------
# touch_error — did a behaviour-affecting declaration touch a requirements file?
# --------------------------------------------------------------------------

def test_behavior_affecting_with_spec_touch_passes():
    assert touch_error(
        impact="modify",
        changed_paths=[".shipwright/planning/01-adopted/spec.md", "src/a.py"],
    ) is None


def test_behavior_affecting_without_spec_touch_rejected():
    err = touch_error(impact="modify", changed_paths=["src/a.py"])
    assert err["error"] == "requirement_impact_no_spec_touched"


def test_none_impact_never_needs_a_touch():
    assert touch_error(impact="none", changed_paths=[]) is None


def test_touch_check_skipped_when_evidence_unavailable():
    """Fail-open on *unavailable* is not fail-open on *unknown* (GPT-8).

    ``changed_paths=None`` means git could not tell us; that must not block.
    An empty LIST means git told us nothing changed, which must block.
    """
    assert touch_error(impact="modify", changed_paths=None) is None
    assert touch_error(impact="modify", changed_paths=[])["error"] == \
        "requirement_impact_no_spec_touched"


# --------------------------------------------------------------------------
# normalize_extras — part (3)'s attributed extras
# --------------------------------------------------------------------------

def test_extras_normalized_to_structured_records():
    out = normalize_extras(["src/shared/util.py=needed a new export for the form"])
    assert out == [{"path": "src/shared/util.py",
                    "reason": "needed a new export for the form"}]


def test_extras_accept_dict_form():
    out = normalize_extras([{"path": "a/b.py", "reason": "smallest change"}])
    assert out == [{"path": "a/b.py", "reason": "smallest change"}]


def test_extra_without_reason_rejected():
    """An unexplained extra is exactly the unrequested work the rule forbids."""
    with pytest.raises(ValueError, match="reason"):
        normalize_extras(["src/shared/util.py"])


def test_extra_with_blank_reason_rejected():
    with pytest.raises(ValueError, match="reason"):
        normalize_extras(["src/shared/util.py=   "])


def test_extra_paths_normalized_and_deduped():
    out = normalize_extras([
        r".\src\shared\util.py=first",
        "src/shared/util.py=duplicate of the same path",
    ])
    assert out == [{"path": "src/shared/util.py", "reason": "first"}]


def test_extra_escaping_project_root_rejected():
    with pytest.raises(ValueError, match="escapes"):
        normalize_extras(["../../../etc/passwd=nope"])


def test_absolute_extra_path_rejected():
    with pytest.raises(ValueError, match="relative"):
        normalize_extras(["/etc/passwd=nope"])


