"""FR-01.09 — a release tells existing projects what they must do.

The release-time check lives in ``references/release-workflow.md`` because
``SKILL.md`` sits at its size cap. These tests pin that the skill still sends the
reader there at the top of Step 4 (before any aggregator call), that the check
names the pages it reads, and that the migration page for the event-file layout
keeps its answer to the one question a maintainer asks ("do I have to do
anything?").
"""

from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
SKILL_DIR = HERE.parent / "skills" / "changelog"
SKILL = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
WORKFLOW = (SKILL_DIR / "references" / "release-workflow.md").read_text(encoding="utf-8")
MIGRATION = next(
    (p / "docs" / "migrations" / "events-drop-files.md" for p in HERE.parents if (p / "docs" / "migrations").is_dir()),
    None,
)


@pytest.mark.covers("FR-01.09/AC01")
def test_step_4_runs_the_upgrade_notes_check_before_any_aggregator_call():
    """A drop added after the real aggregate run would ship one release late, so the pointer sits at the top of Step 4."""
    step4 = SKILL.split("## Step 4: Generate Changelog Entry", 1)[1].split("\n## ", 1)[0]
    assert "upgrade-notes check" in step4
    assert step4.index("upgrade-notes check") < step4.index("aggregate_changelog.py")


@pytest.mark.covers("FR-01.09/AC01")
def test_the_check_reads_changed_migration_pages_and_files_a_changed_drop():
    section = WORKFLOW.split("## Upgrade-notes check", 1)[1].split("\n## ", 1)[0]
    assert "docs/migrations" in section
    assert "Do you have to do anything?" in section
    assert "CHANGELOG-unreleased.d/Changed/" in section
    assert "BEFORE\nthe first `aggregate_changelog.py` call" in section


@pytest.mark.covers("FR-01.09/AC01")
def test_the_event_file_migration_page_answers_the_question_and_keeps_ci_optional():
    if MIGRATION is None:
        pytest.skip("docs/ is not shipped with the plugin cache; this guard runs in the monorepo")
    text = MIGRATION.read_text(encoding="utf-8")
    assert "**Do you have to do anything?**" in text
    assert "not part of any\nshipped CI template" in text and "fetch-depth: 0" in text
    assert "events_layout" in text and "WebUI" in text
