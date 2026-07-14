"""The cross-repo contract must stay STATED, not just enforced.

The gates (``test_report_model_contract.py`` / ``test_snapshot_contract.py``) stop a
silent shape change. They do not stop someone from deleting the paragraph that explains
*why the gate exists and who is on the other end of it* — and a gate whose rationale has
been tidied away is one "this test is annoying" away from being deleted too.

The original finding was precisely this: **nobody in this repo had a reason to know the
WebUI was watching.** These assertions are the documentation half of the fix. They check
substance — the consumer is named, the rule is stated, the version semantics are spelled
out — rather than the presence of a heading, which a refactor could keep while gutting
everything under it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent

GRADE_SKILL = _REPO_ROOT / "plugins/shipwright-grade/skills/grade/SKILL.md"
ADOPT_SKILL = _REPO_ROOT / "plugins/shipwright-adopt/skills/adopt/SKILL.md"
# Adopt's Kern SKILL.md is capped at 300 LOC and holds only a pointer; the contract
# itself lives in references/, per that skill's own thin-index architecture. The gate
# below therefore reads BOTH — what matters is that a maintainer following the trail
# from the producer arrives at the full contract, not which file it is stored in.
ADOPT_CONTRACT_REF = (
    _REPO_ROOT / "plugins/shipwright-adopt/skills/adopt/references/cross-repo-contract.md")
GRADE_PRODUCER = _REPO_ROOT / "plugins/shipwright-grade/scripts/lib/report_model.py"
ADOPT_PRODUCER = _REPO_ROOT / "plugins/shipwright-adopt/scripts/tools/analyze_codebase.py"

CONSUMER_MARKERS = ("Command Center", "shipwright-webui")


def _text(path: Path) -> str:
    assert path.is_file(), f"{path} is missing"
    return path.read_text(encoding="utf-8")


GRADE_CONTRACT = [GRADE_SKILL]
ADOPT_CONTRACT = [ADOPT_SKILL, ADOPT_CONTRACT_REF]


@pytest.mark.parametrize("paths", [GRADE_CONTRACT, ADOPT_CONTRACT],
                         ids=["grade", "adopt"])
class TestTheSkillPointsAtTheConsumer:
    """Whichever file it lives in, the trail from the producer must reach the contract."""

    def test_the_skill_itself_flags_the_contract(self, paths: list[Path]):
        # The Kern is what a maintainer skims. It must at minimum RAISE THE FLAG, even
        # when the detail is one hop away in references/.
        skill = _text(paths[0])
        assert "Cross-repo contract" in skill
        assert "requires a corresponding WebUI change" in skill


@pytest.mark.parametrize("path", [GRADE_SKILL, ADOPT_CONTRACT_REF], ids=["grade", "adopt"])
class TestSkillStatesTheContract:
    def test_it_has_a_cross_repo_contract_section(self, path: Path):
        assert "Cross-repo contract" in _text(path), (
            f"{path.name} no longer states that its output has an external consumer. "
            "That paragraph IS the fix — without it, the next person to rename a field "
            "has no reason to know the WebUI renders it."
        )

    def test_it_names_the_consumer(self, path: Path):
        text = _text(path)
        assert all(marker in text for marker in CONSUMER_MARKERS), (
            "the contract section must name the consumer and point at its repo — "
            '"an external consumer" with no address is not actionable'
        )

    def test_it_states_that_a_change_here_needs_a_change_there(self, path: Path):
        text = _text(path)
        assert "requires a corresponding WebUI change" in text, (
            "the contract section must state the RULE, not merely describe the consumer"
        )

    def test_it_explains_the_failure_mode(self, path: Path):
        # The reason this is dangerous is that it does NOT fail loudly. Say so.
        assert "half-empty card" in _text(path)

    def test_it_spells_out_the_version_semantics(self, path: Path):
        text = _text(path)
        for token in ("MAJOR", "MINOR", "schema_version"):
            assert token in text, f"the contract section must explain {token}"

    def test_it_says_the_baseline_is_frozen_against_main(self, path: Path):
        # The one property that makes the gate a mechanism rather than a reminder.
        text = _text(path)
        assert "origin/main" in text and "frozen" in text


class TestProducerCarriesTheWarning:
    """The SKILL.md is where you read; the producer is where you EDIT."""

    @pytest.mark.parametrize("path", [GRADE_PRODUCER, ADOPT_PRODUCER],
                             ids=["report_model", "analyze_codebase"])
    def test_the_module_docstring_warns_before_the_first_field(self, path: Path):
        text = _text(path)
        assert "CROSS-REPO CONTRACT" in text, (
            f"{path.name} must warn in its module docstring. Someone renaming a field "
            "opens THIS file — not the SKILL.md."
        )
        assert any(marker in text for marker in CONSUMER_MARKERS)
        assert "SKILL.md" in text, "point the reader at the full contract"


class TestGradeDocumentsTheCloneCost:
    """The WebUI surfaces the clone step and its network cost — 'a URL is not free'."""

    def test_target_resolution_is_stated_as_part_of_the_contract(self):
        text = _text(GRADE_SKILL)
        section = text[text.index("Cross-repo contract"):]
        assert "--no-clone" in section
        assert "tempdir" in section or "throwaway" in section

    def test_the_network_receipt_is_named_load_bearing(self):
        section = _text(GRADE_SKILL)
        assert "network_enrichments" in section
        assert "left the machine" in section


class TestAdoptDocumentsTheOpaqueSubtrees:
    def test_the_consumer_is_told_to_iterate_not_index(self):
        # A detector-keyed map is not a record: indexing `stack.frontend.react` is a bug
        # waiting for the first Vue repo.
        assert "ITERATE them, never index" in _text(ADOPT_CONTRACT_REF)

    def test_schema_version_is_documented_as_additive(self):
        text = _text(ADOPT_CONTRACT_REF)
        assert "additive" in text
        assert "older adopt" in text, (
            "a snapshot written before the version existed must stay readable — say so"
        )

    def test_nullability_is_documented_as_breaking(self):
        # The subtlest break in the whole contract: no key changes, and the consumer
        # dereferences null. If it is not written down, the next person will "helpfully"
        # make a field optional and ship it as a minor.
        text = _text(ADOPT_CONTRACT_REF)
        assert "becoming nullable is BREAKING" in text
