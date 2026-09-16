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

Tier-3 PR review round 8: the single combined command block used to show
``--fail-if-empty`` as a bare (always-passed) argument on the SAME line as
``[--dry-run]``, contradicting the prose exception ("except the --dry-run
preview pass") — and ``aggregate_changelog.py`` itself raises on an empty
release regardless of ``--dry-run``, so following the fenced example
verbatim during a preview would fail instead of previewing. Step 4 now
documents two separate invocations (preview, real release); these tests
were split to pin each fence's flags independently.
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


def _aggregate_changelog_fences() -> list[str]:
    """All fenced ``bash`` blocks in Step 4 invoking ``aggregate_changelog.py``
    — deliberately NOT the surrounding prose, so a flag mentioned only there
    cannot satisfy these assertions."""
    block = _step_4_block()
    return [
        fence
        for fence in re.findall(r"```bash\n(.*?)\n```", block, re.DOTALL)
        if "aggregate_changelog.py" in fence
    ]


def _release_command() -> str:
    """The real-release invocation — the fence that carries
    ``--fail-if-empty``, distinct from the ``--dry-run`` preview fence which
    must NOT carry it."""
    for fence in _aggregate_changelog_fences():
        if "--fail-if-empty" in fence:
            return fence
    raise AssertionError("no aggregate_changelog.py fence carries --fail-if-empty")


def _preview_command() -> str:
    """The ``--dry-run`` preview invocation."""
    for fence in _aggregate_changelog_fences():
        if "--dry-run" in fence:
            return fence
    raise AssertionError("no aggregate_changelog.py fence carries --dry-run")


def test_step_4_command_names_fail_if_empty():
    command = _release_command()
    assert "--fail-if-empty" in command


def test_step_4_command_is_not_only_optional_flags():
    """Regression pin for the exact gap Tier-3 review round 6 named: the
    flag must be a bare argument on the command, not bracketed as optional
    the way ``[--release-date ...]`` is — a truly optional
    ``[--fail-if-empty]`` would defeat criterion 3 just as thoroughly as
    dropping it outright.
    """
    command = _release_command()
    assert "[--fail-if-empty]" not in command
    assert "--fail-if-empty" in command


def test_dry_run_preview_command_omits_fail_if_empty():
    """Regression pin for Tier-3 review round 8: the aggregator raises on an
    empty release regardless of ``--dry-run``, so the documented preview
    command must never carry ``--fail-if-empty`` — combining them would turn
    a preview of "nothing pending" into a hard failure."""
    command = _preview_command()
    assert "--fail-if-empty" not in command


def test_step_4_instructs_never_combining_fail_if_empty_with_dry_run():
    block = _step_4_block()
    assert "Always pass `--fail-if-empty`" in block
    assert "dry-run" in block.lower()
    assert "Never pass `--fail-if-empty` alongside `--dry-run`" in block
