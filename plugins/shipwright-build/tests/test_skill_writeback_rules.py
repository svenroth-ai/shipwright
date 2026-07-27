"""Drift-protection for the build phase's contradiction + shared-touch rules.

Both rules were decided and neither existed, in code or in instruction. Both are
**human reads** — detecting a prose-vs-markup contradiction has no deterministic
check — so the instruction IS the mechanism for that half, and an instruction
with no test is one edit away from disappearing.

The shared-touch rule additionally has to hold in *every* place the "nothing
outside the section" criterion is stated. A carve-out present in one reviewer and
absent in another is worse than none: it makes the outcome depend on which
reviewer happened to run.

Origin: trg-e9e5188e (FR-01.05).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
BUILD = REPO_ROOT / "plugins" / "shipwright-build"
SKILL_MD = BUILD / "skills" / "build" / "SKILL.md"
SELF_REVIEW = BUILD / "skills" / "build" / "references" / "self-review-checklist.md"
SPEC_REVIEWER = BUILD / "agents" / "spec-reviewer.md"
SECTION_BUILDER = BUILD / "agents" / "section-builder.md"
#: SKILL.md carries short anchors; the rule bodies live here (the plugin keeps
#: its kern under 300 LOC by design — see its "Phase Index" table).
WRITEBACK = BUILD / "skills" / "build" / "references" / "requirement-writeback.md"

#: Every runtime prompt that states the "nothing outside the section" criterion
#: and therefore must also state the carve-out.
SCOPE_RULE_FILES = (SELF_REVIEW, SPEC_REVIEWER, SECTION_BUILDER, WRITEBACK)


#: Every script the prompts tell the phase to invoke, and where it must live.
#: Asserting only that the NAME appears in the markdown would pass just as
#: happily against a script that does not exist — the prompt reads fine and
#: fails at runtime with a non-zero exit and no useful error. Both directions
#: are pinned: the name is in the prompt AND the file is on disk.
REFERENCED_SCRIPTS = (
    Path("shared") / "scripts" / "tools" / "record_requirement_impact.py",
    Path("shared") / "scripts" / "tools" / "check_section_file_attribution.py",
)


def _read(path: Path) -> str:
    if not path.is_file():
        pytest.fail(f"missing runtime prompt: {path}")
    return path.read_text(encoding="utf-8")


def _locate(text: str, needle: str, path: Path) -> int:
    """``text.index`` with a described failure instead of a bare ValueError.

    An unguarded ``.index()`` on a renamed heading raises with no message, so a
    drift test that should say "this anchor moved" instead errors out opaquely.
    """
    if needle not in text:
        pytest.fail(
            f"{path.name} no longer contains {needle!r} — the anchor moved or was "
            "renamed, so the rule pinned to it is now unchecked"
        )
    return text.index(needle)


@pytest.mark.parametrize("script", REFERENCED_SCRIPTS, ids=lambda p: p.name)
def test_every_script_the_prompt_names_actually_exists(script):
    """A prompt naming a script that does not exist reads fine and does nothing."""
    if not (REPO_ROOT / script).is_file():
        pytest.fail(
            f"{script.as_posix()} is referenced by the build prompts but is not on "
            "disk. Merge the shared-mechanism PR first — these prompts call tools "
            "that land there."
        )


def _flat(path: Path) -> str:
    """Lower-cased with runs of whitespace collapsed.

    Prose assertions run against this so a rule that gets re-wrapped by an editor
    still matches — the test is meant to catch a rule being *removed*, not a line
    being reflowed.
    """
    return re.sub(r"\s+", " ", _read(path).lower())


# --------------------------------------------------------------------------
# AC-5 — the mockup-vs-section contradiction STOPS
# --------------------------------------------------------------------------

def test_skill_step_1_carries_the_contradiction_stop_rule():
    text = _read(SKILL_MD)
    assert "Mockup-vs-Section Contradiction" in text, (
        "SKILL.md Step 1 must name the contradiction case — without it the two "
        "criteria stay unsatisfiable and whichever the builder follows wins silently"
    )
    assert "requirement-writeback" in text, "the anchor must reach the rule body"


@pytest.mark.parametrize("path", [SKILL_MD, WRITEBACK], ids=lambda p: p.name)
def test_contradiction_rule_says_stop_and_asks_a_person(path):
    assert "STOP" in _read(path)
    flat = _flat(path)
    assert "stop building" in flat
    # One canonical phrase in both files, so a file cannot drop it and still pass.
    assert "put it to a person" in flat


@pytest.mark.parametrize("path", [SKILL_MD, WRITEBACK], ids=lambda p: p.name)
def test_contradiction_rule_names_the_expected_resolution(path):
    """Not merely 'ask someone' — the mockup is the side a human judged."""
    flat = _flat(path)
    assert "requirement is corrected to match the mockup" in flat
    assert "real use" in flat


@pytest.mark.parametrize("path", [SKILL_MD, WRITEBACK], ids=lambda p: p.name)
def test_contradiction_rule_is_honest_about_having_no_automatic_check(path):
    assert "no deterministic check" in _flat(path)


def test_contradiction_decision_is_recorded():
    assert "--contradiction" in _read(SKILL_MD)
    assert "--contradiction" in _read(WRITEBACK)


@pytest.mark.parametrize("path", [SPEC_REVIEWER, SECTION_BUILDER])
def test_reviewers_and_autonomous_path_also_stop_on_a_contradiction(path):
    flat = _flat(path)
    assert "contradict" in flat
    assert "mockup" in flat


def test_autonomous_priority_ladder_does_not_silently_settle_contradictions():
    """The ladder says Spec > Mockup; unqualified, it IS the silent resolution."""
    text = _read(SECTION_BUILDER)
    assert "Source-of-truth priority" in text
    ladder_at = _locate(text, "Source-of-truth priority", SECTION_BUILDER)
    window = text[ladder_at: ladder_at + 2000].lower()
    assert "stop" in window, (
        "the priority ladder must carve out the behavioural contradiction — "
        "otherwise the autonomous path resolves it automatically"
    )


# --------------------------------------------------------------------------
# AC-6 — the shared-touch carve-out, everywhere the scope rule is stated
# --------------------------------------------------------------------------

@pytest.mark.parametrize("path", SCOPE_RULE_FILES, ids=lambda p: p.name)
def test_every_scope_rule_site_carries_the_shared_touch_carve_out(path):
    flat = _flat(path)
    assert "carve-out" in flat, (
        f"{path.name} states the no-extra-work rule but not the carve-out; "
        "taken literally that makes a section needing a shared change unbuildable"
    )
    assert "shared" in flat


@pytest.mark.parametrize("path", SCOPE_RULE_FILES, ids=lambda p: p.name)
def test_carve_out_requires_the_change_to_be_smallest_and_recorded(path):
    flat = _flat(path)
    assert "smallest" in flat
    assert "recorded" in flat or "attributed extra" in flat


def test_carve_out_states_what_the_rule_actually_forbids():
    assert "unrequested extra work" in _flat(SELF_REVIEW)


# --------------------------------------------------------------------------
# AC-7 — the section declares, and the attribution check runs
# --------------------------------------------------------------------------

@pytest.mark.parametrize("path", [SKILL_MD, WRITEBACK], ids=lambda p: p.name)
def test_step_10b_declares_the_requirement_impact(path):
    text = _read(path)
    assert "record_requirement_impact.py" in text
    assert "--phase build" in text


@pytest.mark.parametrize("path", [SKILL_MD, WRITEBACK], ids=lambda p: p.name)
def test_attribution_check_is_wired(path):
    text = _read(path)
    assert "check_section_file_attribution.py" in text
    assert "--extra" in text


def test_declaration_is_recorded_after_the_section_commit():
    """The declaration describes a FINISHED section, so it is recorded after it.

    That ordering also makes `HEAD` the section's own commit, which is what lets
    the range be `HEAD^..HEAD`. Anchors on the step HEADINGS, not the first
    mention — Step 10b is also named in the Phase Index table at the top.
    """
    text = _read(SKILL_MD)
    step_10b = _locate(text, "### Step 10b", SKILL_MD)
    step_8 = _locate(text, "## Step 8: Commit", SKILL_MD)
    assert step_8 < step_10b
    window = text[step_10b: step_10b + 500].lower()
    assert "after" in window
    # The range must be the section's OWN commit. Passing the branch base put
    # every earlier section inside this section's range and false-failed it.
    assert "head^..head" in window or "--base-ref head^" in window


def test_autonomous_path_declares_and_checks_too():
    text = _read(SECTION_BUILDER)
    assert "record_requirement_impact.py" in text
    assert "check_section_file_attribution.py" in text
