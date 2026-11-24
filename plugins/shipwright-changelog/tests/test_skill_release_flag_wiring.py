"""FR-01.09 criterion 3: ``--fail-if-empty`` is wired into the release command, and never into the preview.

A flag that merely exists on the aggregator enforces nothing unless its one caller passes it. Until unit P5 this file read the fenced
``aggregate_changelog.py`` commands out of ``SKILL.md`` Step 4; the skill now calls ``release.py aggregate`` and the flags are the CLI's
(``lib/release_aggregate.py``, finding A4), so the four old pins are four tests of the argv the CLI builds. They run in-process with an
injected runner, and one reads ``SKILL.md`` to pin that the prose still sends the model through that command.
"""


from datetime import datetime, timezone
from pathlib import Path

import pytest

from lib import release_aggregate
from lib.release_runner import Recorder

from .test_release_cli import AGG_OK, Fake

SKILL_PATH = Path(__file__).resolve().parent.parent / "skills" / "changelog" / "SKILL.md"
NOW = datetime(2026, 11, 23, 9, 30, 0, tzinfo=timezone.utc)


def _argv(tmp_path: Path, plugin_root: Path, *, dry_run: bool) -> list[str]:
    fake = Fake(**{"aggregate-dry": AGG_OK, "aggregate": AGG_OK, "tag-check": {"exit": 1}, "decisions": {}, "decisions-dry": {}})
    release_aggregate.aggregate(Recorder(fake, tmp_path), plugin_root, version="1.3.0", dry_run=dry_run, clock=lambda: NOW)
    return fake.argv("aggregate-dry" if dry_run else "aggregate")


@pytest.mark.covers("FR-01.09/AC03")
def test_the_real_run_names_fail_if_empty(tmp_path, plugin_root):
    """was test_step_4_command_names_fail_if_empty"""
    assert "--fail-if-empty" in _argv(tmp_path, plugin_root, dry_run=False)


@pytest.mark.covers("FR-01.09/AC03")
def test_fail_if_empty_is_a_bare_argument_never_an_optional_one(tmp_path, plugin_root):
    """was test_step_4_command_is_not_only_optional_flags: the flag is one whole argv item, not bracketed text inside another."""
    argv = _argv(tmp_path, plugin_root, dry_run=False)
    assert argv.count("--fail-if-empty") == 1 and not any("[" in a for a in argv)


@pytest.mark.covers("FR-01.09/AC03")
def test_the_preview_omits_fail_if_empty(tmp_path, plugin_root):
    """was test_dry_run_preview_command_omits_fail_if_empty: the aggregator raises on an empty release even with --dry-run."""
    argv = _argv(tmp_path, plugin_root, dry_run=True)
    assert "--dry-run" in argv and "--fail-if-empty" not in argv


@pytest.mark.covers("FR-01.09/AC03")
def test_the_skill_sends_the_model_through_the_one_command_that_owns_the_flags():
    """was test_step_4_instructs_never_combining_...: the prose names no aggregator flag, only the CLI call, so the two cannot be combined by hand."""
    text = SKILL_PATH.read_text(encoding="utf-8")
    block = text[text.index("## Step 4: Generate Changelog Entry"):text.index("\n## Step 5")]
    assert block.count('release.py" aggregate') == 2 and "--dry-run" in block
    assert "--fail-if-empty" not in block and "aggregate_changelog.py" not in block
