"""FR-01.09 criterion 3 — the ``--fail-if-empty`` flag stays wired into the
documented release command.

This codebase has no separate compiled release/tagging script — Step 4's
``aggregate_changelog.py`` invocation IS the release path
``/shipwright-changelog`` follows (an agent executes the documented command
verbatim). External review (round 1, e4-checks-deploy-changelog) correctly
flagged that a flag which merely exists on the CLI enforces nothing unless
its one caller actually passes it; this test pins that the SKILL.md command
block still does, so a future edit to Step 4 cannot silently drop it without
a test failing.
"""

from pathlib import Path

SKILL_PATH = (
    Path(__file__).resolve().parent.parent / "skills" / "changelog" / "SKILL.md"
)


def _step_4_block() -> str:
    text = SKILL_PATH.read_text(encoding="utf-8")
    start = text.index("## Step 4: Generate Changelog Entry")
    end = text.index("\n## Step 5", start) if "\n## Step 5" in text[start:] else len(text)
    return text[start:end]


def test_step_4_command_names_fail_if_empty():
    block = _step_4_block()
    assert "--fail-if-empty" in block


def test_step_4_instructs_always_passing_it():
    block = _step_4_block()
    assert "Always pass `--fail-if-empty`" in block
