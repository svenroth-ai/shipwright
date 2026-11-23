"""The gate answers (second pass A2) and the upgrade-notes check (A3), each with a case the old prose behaviour fails.

Old behaviour: the answers were two prose copies the model read (Step 3 and Step 5 of ``SKILL.md``), and the upgrade-notes check
was four steps the model carried out; a catalog edit changed neither, and a skipped step left no trace. The tests below
change the catalog row / add a migration page and look at what the CODE answers or writes.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
pytestmark = pytest.mark.covers("FR-01.09/AC01")  # the tests prove the release steps behave as the requirement says; finer tags where a test names its AC

from lib import release_gates, release_upgrade_notes as notes
from lib.release_runner import CmdResult, Recorder, subprocess_runner

SHARED = Path(__file__).resolve().parents[3] / "shared"
ROWS = [{"gate_id": g, "policy": "auto-default"} for g in ("changelog.version-suggestion", "changelog.entry-preview")] + [
    {"gate_id": "changelog.out-of-sequence-continue", "policy": "orchestrator-approve"}]


def edited(gate: str, policy: str) -> list[dict]:
    return [{**r, "policy": policy} if r["gate_id"] == gate else r for r in ROWS]


@pytest.mark.parametrize(("mode", "autonomy", "want"), [("standalone", "guided", "ask"), ("standalone", None, "ask"),
                                                        ("standalone", "autonomous", "auto"), ("standalone", "unattended", "auto"),
                                                        ("pipeline", "guided", "auto")])
def test_a_gate_the_catalog_auto_defaults_is_auto_only_when_driven_or_autonomous(mode, autonomy, want):
    assert release_gates.answers(ROWS, mode=mode, autonomy=autonomy)["version"] == want


@pytest.mark.covers("FR-01.09/AC04")
def test_a_catalog_edit_changes_the_answer_and_no_prose_does():
    assert release_gates.answers(ROWS, mode="pipeline", autonomy=None)["version"] == "auto"
    assert release_gates.answers(edited("changelog.version-suggestion", "orchestrator-approve"), mode="pipeline", autonomy=None)["version"] == "ask"
    assert release_gates.answers(edited("changelog.entry-preview", "hard-stop"), mode="standalone", autonomy="autonomous")["preview"] == "ask"
    assert release_gates.answers(edited("changelog.out-of-sequence-continue", "auto-default"), mode="pipeline", autonomy=None)["out_of_sequence"] == "auto"


def test_a_missing_row_or_an_unknown_policy_asks():
    assert release_gates.answers([], mode="pipeline", autonomy="autonomous") == {"version": "ask", "preview": "ask", "out_of_sequence": "ask"}
    assert release_gates.answers(edited("changelog.entry-preview", "made-up"), mode="pipeline", autonomy=None)["preview"] == "ask"


def test_the_real_resolver_and_catalog_give_the_answers_the_prose_stated():
    """Boundary: the resolver CLI over the real catalog, no fake."""
    done = subprocess.run(["uv", "run", str(SHARED / "scripts/tools/resolve_gate_policy.py"), "--phase", "changelog", "--list"],
                          capture_output=True, text=True, encoding="utf-8")
    assert done.returncode == 0, done.stderr
    rows = json.loads(done.stdout)["gates"]
    assert {r["gate_id"] for r in rows} >= set(release_gates.GATE_IDS.values())
    catalog = {g["id"]: g["policy"] for g in json.loads((SHARED / "config/gate_catalog.json").read_text(encoding="utf-8"))["gates"]}
    assert all(r["policy"] == catalog[r["gate_id"]] for r in rows)
    assert release_gates.answers(rows, mode="standalone", autonomy="guided") == {"version": "ask", "preview": "ask", "out_of_sequence": "ask"}
    assert release_gates.answers(rows, mode="pipeline", autonomy="guided") == {"version": "auto", "preview": "auto", "out_of_sequence": "ask"}


# ---- the upgrade-notes check -------------------------------------------------------------------

ACTION = "**Do you have to do anything?** Update the WebUI first, then the plugins.\nSecond line of the answer.\n\nMore text.\n"
NO = "**Do you have to do anything?** No.\n"


class Git:
    """Answers the two git calls of the check from a table of pages."""

    def __init__(self, listing: str, write_drops: bool = True):
        self.listing, self.drops, self.write_drops = listing, [], write_drops

    def __call__(self, key, argv, cwd):
        if key == "migration-pages":
            return CmdResult(key, tuple(argv), 0, self.listing)
        self.drops.append(list(argv))
        if self.write_drops:  # stands for write_changelog_drop.py
            run_id, bullet = argv[argv.index("--run-id") + 1], argv[argv.index("--bullet") + 1]
            target = cwd / "CHANGELOG-unreleased.d" / "Changed"
            target.mkdir(parents=True, exist_ok=True)
            (target / f"{run_id}_001.md").write_text(bullet + "\n", encoding="utf-8")
        return CmdResult(key, tuple(argv), 0)


def project(tmp_path, **pages: str) -> Path:
    (tmp_path / "docs" / "migrations").mkdir(parents=True)
    for name, text in pages.items():
        (tmp_path / "docs" / "migrations" / f"{name}.md").write_text(text, encoding="utf-8")
    return tmp_path


def check(root, git, last_tag="v1.0.0", version="1.1.0"):
    return notes.check(Recorder(git, root), SHARED, last_tag, version)


@pytest.mark.covers("FR-01.09/AC01")
def test_a_page_with_an_action_gets_its_drop_written_by_code_with_its_own_words_and_the_link(tmp_path):
    root = project(tmp_path, **{"events-drop-files": ACTION})
    git = Git("docs/migrations/events-drop-files.md\n")
    out = check(root, git)
    drop = (root / "CHANGELOG-unreleased.d/Changed/upgrade-notes-events-drop-files_001.md").read_text(encoding="utf-8")
    assert out["status"] == "action_drop_written" and out["pages"][0]["action"] is True
    assert drop.startswith("Existing projects: Update the WebUI first, then the plugins. Second line of the answer.")
    assert drop.strip().endswith("(see docs/migrations/events-drop-files.md)")
    argv = git.drops[0]
    assert argv[argv.index("--category") + 1] == "Changed" and "write_changelog_drop.py" in " ".join(argv)
    assert "review the upgrade-note drop" in out["sentence"]


@pytest.mark.covers("FR-01.09/AC01")
def test_no_migration_page_changed_returns_the_sentence_and_writes_nothing(tmp_path):
    out = check(project(tmp_path), Git(""))
    assert out["status"] == "none_changed" and out["sentence"] == "No migration page changed since v1.0.0: no upgrade note added."
    assert not (tmp_path / "CHANGELOG-unreleased.d").exists()


def test_a_page_that_answers_a_plain_no_needs_no_drop(tmp_path):
    root = project(tmp_path, quiet=NO)
    git = Git("docs/migrations/quiet.md\n")
    out = check(root, git)
    assert out["status"] == "no_action" and git.drops == [] and "none needs an action" in out["sentence"]


@pytest.mark.parametrize("answer", ["No.", "no", "Nothing.", "No action needed.", "**No**"])
def test_plain_no_spellings(answer):
    assert notes.needs_action(answer) is False


@pytest.mark.parametrize("answer", [None, "Not to upgrade. Update the plugins.", "No, but check the catalog first.", "Yes", ""])
def test_everything_else_counts_as_an_action(answer):
    assert notes.needs_action(answer) is True


def test_a_page_without_the_question_is_an_action_and_the_drop_says_it_is_unanswered(tmp_path):
    root = project(tmp_path, bare="# A page\n\nNothing about upgrading here.\n")
    out = check(root, Git("docs/migrations/bare.md\n"))
    drop = (root / "CHANGELOG-unreleased.d/Changed/upgrade-notes-bare_001.md").read_text(encoding="utf-8")
    assert out["pages"][0]["answer"] is None and "does not say whether anything has to be done" in drop


def test_a_second_run_writes_no_second_drop(tmp_path):
    root = project(tmp_path, page=ACTION)
    git = Git("docs/migrations/page.md\n")
    check(root, git)
    again = check(root, git)
    assert again["status"] == "action_drop_exists" and len(git.drops) == 1


def test_a_rerun_after_the_section_was_rendered_adds_no_drop(tmp_path):
    root = project(tmp_path, page=ACTION)
    (tmp_path / "CHANGELOG.md").write_text("# Changelog\n\n## [1.1.0] - 2026-10-01\n", encoding="utf-8")
    git = Git("docs/migrations/page.md\n")
    out = check(root, git)
    assert out["status"] == "skipped_release_written" and git.drops == []


def test_a_failed_drop_write_is_reported_not_swallowed(tmp_path):
    root = project(tmp_path, page=ACTION)
    out = notes.check(Recorder(lambda k, a, c: CmdResult(k, tuple(a), 0 if k == "migration-pages" else 1, "docs/migrations/page.md\n" if k == "migration-pages" else ""), root), SHARED, "v1.0.0", "1.1.0")
    assert out["status"] == "action_drop_failed" and out["pages"][0]["drop"] == "failed"


def test_without_a_tag_every_page_is_listed_and_a_deleted_page_is_skipped(tmp_path):
    root = project(tmp_path, kept=NO)
    git = Git("docs/migrations/kept.md\ndocs/migrations/gone.md\n")
    out = check(root, git, last_tag=None)
    assert [p["page"] for p in out["pages"]] == ["docs/migrations/kept.md"] and "in this repository" in out["sentence"]


def test_the_check_with_real_git_and_the_real_drop_writer(tmp_path):
    """Boundary: git diff since a tag and ``write_changelog_drop.py``, no fake."""
    def git(*a):
        subprocess.run(["git", *a], cwd=tmp_path, check=True, capture_output=True, encoding="utf-8")
    git("init", "-b", "main"), git("config", "user.email", "t@t"), git("config", "user.name", "T")
    (tmp_path / "README.md").write_text("x\n", encoding="utf-8")
    git("add", "."), git("commit", "-m", "chore: init"), git("tag", "v1.0.0")
    project(tmp_path, **{"new-layout": ACTION, "quiet": NO})
    git("add", "."), git("commit", "-m", "docs: migration pages")
    out = notes.check(Recorder(subprocess_runner, tmp_path), SHARED, "v1.0.0", "1.1.0")
    assert [(p["page"], p["action"], p["drop"]) for p in out["pages"]] == [
        ("docs/migrations/new-layout.md", True, "written"), ("docs/migrations/quiet.md", False, None)]
    files = list((tmp_path / "CHANGELOG-unreleased.d" / "Changed").glob("upgrade-notes-new-layout_*.md"))
    assert len(files) == 1 and "Update the WebUI first" in files[0].read_text(encoding="utf-8")


def test_an_answer_in_the_paragraph_after_the_question_is_read(tmp_path):
    q = "**Do you have to do anything?**"
    assert notes.answer_of(q + "\n\nNo.\n") == "No." and not notes.needs_action("No.")
    assert notes.answer_of(q + "\n\nUpdate the WebUI.\nThen the plugins.\n\nOther.\n") == "Update the WebUI. Then the plugins."


def test_a_failed_page_listing_stops_the_check_instead_of_reporting_no_change(tmp_path):
    root = project(tmp_path, page=ACTION)
    out = notes.check(Recorder(lambda k, a, c: CmdResult(k, tuple(a), 128, "", "fatal: bad revision"), root), SHARED, "v9.9.9", "1.1.0")
    assert out["status"] == "query_failed" and out["pages"] == []


def test_a_rendered_section_keeps_the_stored_date_on_a_later_day_and_an_unrendered_one_takes_today(tmp_path):
    from datetime import datetime, timezone
    from lib import release_runstate as rs
    rs.save(tmp_path, {"schema": 1, "version": "1.3.0", "release_date": "2026-10-01", "run_id": "r", "created_at": "2026-10-01T08:00:00+00:00"})
    later = lambda: datetime(2026, 11, 23, 9, 0, tzinfo=timezone.utc)  # noqa: E731
    assert rs.resolve(tmp_path, "1.3.0", tag_exists=False, require_fresh=False, released=True, clock=later)["release_date"] == "2026-10-01"
    assert rs.resolve(tmp_path, "1.3.0", tag_exists=False, require_fresh=False, clock=later)["release_date"] == "2026-11-23"
    (tmp_path / "CHANGELOG.md").write_text("# Changelog\n\n## [1.3.0] - 2026-10-01\n", encoding="utf-8")
    assert notes.released(tmp_path, "1.3.0") and not notes.released(tmp_path, "1.4.0")
