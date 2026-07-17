"""Snapshot test for plugins/shipwright-adopt/skills/adopt/SKILL.md.

Locks in the wording added by iterate-2026-05-03-adopt-env-local-scaffold:

- Step E.5 documents the .env.local scaffold call between Step E
  (artifact generation) and Step F (compliance seeding).
- Step H "Next steps" handoff banner mentions ``.env.local`` and tells
  the user to fill in profile-specific keys.

Substring-based assertions — unrelated edits to other sections must
not trigger false positives. Surface-only check; no behavior assertions.
"""

from __future__ import annotations

from pathlib import Path

import pytest


SKILL_MD = (
    Path(__file__).resolve().parents[1]
    / "skills" / "adopt" / "SKILL.md"
)


@pytest.fixture(scope="module")
def skill_text() -> str:
    return SKILL_MD.read_text(encoding="utf-8")


@pytest.mark.covers("FR-01.13")
def test_skill_md_exists(skill_text: str) -> None:
    """Sanity: file is non-empty markdown."""
    assert skill_text.startswith("---")
    assert "shipwright-adopt" in skill_text


class TestStepE5EnvScaffold:
    @pytest.mark.covers("FR-01.13")
    def test_step_e5_heading_present(self, skill_text: str) -> None:
        assert "### Step E.5" in skill_text

    @pytest.mark.covers("FR-01.13")
    def test_step_e5_mentions_env_local(self, skill_text: str) -> None:
        # Locate the Step E.5 block, confined to itself
        e5_start = skill_text.index("### Step E.5")
        # Step F is the next major heading after E.5
        e5_end = skill_text.index("### Step F", e5_start)
        e5_block = skill_text[e5_start:e5_end]
        assert ".env.local" in e5_block

    @pytest.mark.covers("FR-01.13")
    def test_step_e5_calls_validate_env_init(self, skill_text: str) -> None:
        e5_start = skill_text.index("### Step E.5")
        e5_end = skill_text.index("### Step F", e5_start)
        e5_block = skill_text[e5_start:e5_end]
        # Documents that adopt invokes the env scaffold via validate_env.
        # Path may use any of {plugin_root}, ${CLAUDE_PLUGIN_ROOT}, or
        # shared/scripts/ — accept any of them.
        assert "validate_env.py" in e5_block
        # Idempotence promise must be in the block.
        assert "idempotent" in e5_block.lower() or "never overwrite" in e5_block.lower()

    @pytest.mark.covers("FR-01.13")
    def test_step_e5_documents_gitignore_handling(self, skill_text: str) -> None:
        e5_start = skill_text.index("### Step E.5")
        e5_end = skill_text.index("### Step F", e5_start)
        e5_block = skill_text[e5_start:e5_end]
        assert ".gitignore" in e5_block


class TestStepHHandoffBanner:
    @pytest.mark.covers("FR-01.13")
    def test_step_h_mentions_edit_env_local(self, skill_text: str) -> None:
        # "Edit .env.local" is the literal handoff phrase the iterate spec locks in.
        h_start = skill_text.index("### Step H")
        # H is the last step in the procedure; banner runs to end of section.
        assert "Edit .env.local" in skill_text[h_start:]

    @pytest.mark.covers("FR-01.13")
    def test_step_h_documents_required_keys_dynamically(self, skill_text: str) -> None:
        """The handoff must say keys come from the profile, not hardcode them."""
        h_start = skill_text.index("### Step H")
        # Either substring counts as evidence the LLM is told to derive the list.
        h_block = skill_text[h_start:]
        derives = (
            "required_env_vars" in h_block
            or "profile" in h_block.lower()
        )
        assert derives, (
            "Step H must instruct the agent to derive the env-key list from "
            "the active profile rather than hardcoding it."
        )
