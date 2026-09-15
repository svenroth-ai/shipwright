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

Tier-3 PR review round 6: the original version of this test only checked
the ENTIRE Step 4 section's text (prose + code fence together) for the
substring ``--fail-if-empty`` — it would keep passing even if the flag were
dropped from the actual ``aggregate_changelog.py`` invocation as long as the
word survived somewhere in the surrounding prose. These tests now extract
the fenced ``aggregate_changelog.py`` command block itself and assert the
flag is a real argument INSIDE it.
"""

import re
from pathlib import Path

SKILL_PATH = (
    Path(__file__).resolve().parent.parent / "skills" / "changelog" / "SKILL.md"
)


def _step_4_block() -> str:
    text = SKILL_PATH.read_text(encoding="utf-8")
    start = text.index("## Step 4: Generate Changelog Entry")
    end = text.index("\n## Step 5", start) if "\n## Step 5" in text[start:] else len(text)
    return text[start:end]


def _aggregate_changelog_command() -> str:
    """The fenced ``bash`` block invoking ``aggregate_changelog.py`` within
    Step 4 — deliberately NOT the whole section, so a flag mentioned only in
    surrounding prose cannot satisfy these assertions."""
    block = _step_4_block()
    for fence in re.findall(r"```bash\n(.*?)\n```", block, re.DOTALL):
        if "aggregate_changelog.py" in fence:
            return fence
    raise AssertionError("no ```bash fence invoking aggregate_changelog.py found in Step 4")


def test_step_4_command_names_fail_if_empty():
    command = _aggregate_changelog_command()
    assert "--fail-if-empty" in command


def test_step_4_command_is_not_only_optional_flags():
    """Regression pin for the exact gap Tier-3 review round 6 named: the
    flag must be a bare argument on the command, not bracketed as optional
    the way ``[--release-date ...]`` and ``[--dry-run]`` are — a truly
    optional ``[--fail-if-empty]`` would defeat criterion 3 just as
    thoroughly as dropping it outright.
    """
    command = _aggregate_changelog_command()
    assert "[--fail-if-empty]" not in command
    assert "--fail-if-empty" in command


def test_step_4_instructs_always_passing_it_except_the_dry_run_preview():
    block = _step_4_block()
    assert "Always pass `--fail-if-empty`" in block
    assert "dry-run" in block.lower()
