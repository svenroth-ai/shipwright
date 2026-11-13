"""The event-folder move: the migration tool, the ``.gitignore`` parent re-include and the integrity check's
recognition of the one-off move."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

sys.path.append(str(Path(__file__).resolve().parent))   # the kit; appended so it never shadows scripts/tools
from events_move_kit import DROP, LINE, git as _git, old_drop as _old_drop  # noqa: E402
from lib.events_gitignore import apply_reinclude, reinclude_lines  # noqa: E402
from lib.events_integrity import check_integrity  # noqa: E402
from lib.events_log import ARCHIVE_DIR, DROPS_DIR, QUARANTINE_DIR  # noqa: E402
from lib.events_sentinel import old_event_folders  # noqa: E402
from tools.migrate_events_folder import main as migrate_main, migrate  # noqa: E402

pytest_plugins = ["events_move_kit"]   # the repo / move_pr fixtures
pytestmark = pytest.mark.covers("FR-01.11")


def test_migrate_moves_tracked_files_with_git_mv(repo):
    _old_drop(repo)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "old layout")
    result = migrate(repo)
    assert result["status"] == "migrated" and result["still_at_old_location"] == []
    assert not (repo / "shipwright_events.d").exists()
    assert (repo / DROPS_DIR / DROP).read_text(encoding="utf-8") == LINE
    assert f"R  shipwright_events.d/{DROP} -> {DROPS_DIR}/{DROP}" in _git(repo, "status", "--short")


def test_migrate_moves_untracked_files_and_every_folder(repo):
    _old_drop(repo)
    for old in ("shipwright_events.archive", "shipwright_events.quarantine"):
        (repo / old).mkdir()
        (repo / old / "f.jsonl").write_text(LINE, encoding="utf-8")
    assert migrate(repo)["status"] == "migrated"
    for new in (DROPS_DIR, ARCHIVE_DIR, QUARANTINE_DIR):
        assert any((repo / new).iterdir())
    assert old_event_folders(repo) == []


def test_migrate_is_rerunnable_and_dry_run_changes_nothing(repo):
    _old_drop(repo)
    dry = migrate(repo, dry_run=True)
    assert dry["status"] == "dry_run" and dry["moves"] == [
        {"from": f"shipwright_events.d/{DROP}", "to": f"{DROPS_DIR}/{DROP}"}]
    assert (repo / "shipwright_events.d" / DROP).exists()
    assert migrate(repo)["status"] == "migrated"
    assert migrate(repo)["status"] == "nothing_to_migrate"


def test_migrate_refuses_a_name_that_exists_in_both_places_and_moves_nothing(repo):
    _old_drop(repo)
    _old_drop(repo, "run-b--aaaaaaaa--cccccccc.jsonl")
    (repo / DROPS_DIR).mkdir(parents=True)
    (repo / DROPS_DIR / DROP).write_text(LINE + LINE.replace('"e1"', '"e2"'), encoding="utf-8")   # DIFFERENT content
    result = migrate(repo)
    assert result["status"] == "refused_name_exists_in_both_places" and result["files"] == [f"{DROPS_DIR}/{DROP}"]
    assert (repo / "shipwright_events.d" / "run-b--aaaaaaaa--cccccccc.jsonl").exists()


def test_migrate_cli_exit_codes(repo, capsys):
    _old_drop(repo)
    assert migrate_main(["--project-root", str(repo)]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "migrated"
    assert migrate_main(["--project-root", str(repo / "nope")]) == 2


def test_gitignore_heal_re_includes_the_parent_chain(repo):
    (repo / ".gitignore").write_text("/.shipwright/*\n", encoding="utf-8")
    (repo / "shipwright_sync_config.json").write_text(json.dumps({"events_layout": "drops"}), encoding="utf-8")
    lines = reinclude_lines(repo)
    assert "!/.shipwright/events/" in lines and "!/.shipwright/events/drops/" in lines
    assert lines.index("!/.shipwright/events/") < lines.index("!/.shipwright/events/drops/")
    healed, _ = apply_reinclude((repo / ".gitignore").read_text(encoding="utf-8"), lines)
    (repo / ".gitignore").write_text(healed, encoding="utf-8")
    probe = subprocess.run(["git", "-C", str(repo), "check-ignore", "-q", "--no-index", "--",
                            f"{DROPS_DIR}/x.jsonl"], capture_output=True, timeout=30)
    assert probe.returncode == 1  # no longer ignored


def test_integrity_accepts_the_byte_identical_move(move_pr):
    assert migrate(move_pr)["status"] == "migrated"
    _git(move_pr, "add", "-A")
    _git(move_pr, "commit", "-q", "-m", "move")
    assert check_integrity(move_pr, "base", "HEAD", own_keys=("run-mine",)) == []


def test_integrity_rejects_a_deletion_at_the_old_location_that_is_not_a_move(move_pr):
    _git(move_pr, "rm", "-q", f"shipwright_events.d/{DROP}")
    _git(move_pr, "commit", "-q", "-m", "delete")
    assert [v.code for v in check_integrity(move_pr, "base", "HEAD")] == ["bad_path"]


def test_integrity_rejects_a_new_file_at_the_old_location(move_pr):
    _old_drop(move_pr, "run-b--aaaaaaaa--cccccccc.jsonl")
    _git(move_pr, "add", "-A")
    _git(move_pr, "commit", "-q", "-m", "late writer")
    found = check_integrity(move_pr, "base", "HEAD")
    assert [v.code for v in found] == ["bad_path"] and "moved to" in found[0].detail


def test_integrity_rejects_a_changed_file_even_if_it_claims_to_be_a_move(move_pr):
    migrate(move_pr)
    (move_pr / DROPS_DIR / DROP).write_text(LINE + LINE.replace('"e1"', '"e2"'), encoding="utf-8")
    _git(move_pr, "add", "-A")
    _git(move_pr, "commit", "-q", "-m", "move + edit")
    found = check_integrity(move_pr, "base", "HEAD", own_keys=("run-a",))
    assert any(v.path == f"shipwright_events.d/{DROP}" for v in found)   # the old file is still reported as deleted, not as a move


def test_integrity_rejects_a_move_across_kinds(move_pr):
    (move_pr / QUARANTINE_DIR).mkdir(parents=True)
    _git(move_pr, "mv", f"shipwright_events.d/{DROP}", f"{QUARANTINE_DIR}/{DROP}")
    _git(move_pr, "commit", "-q", "-m", "drop moved into quarantine")
    found = check_integrity(move_pr, "base", "HEAD", own_keys=("run-a",))
    assert any(v.path == f"shipwright_events.d/{DROP}" for v in found)


def test_integrity_rejects_a_rename_during_the_move(move_pr):
    (move_pr / DROPS_DIR).mkdir(parents=True)
    _git(move_pr, "mv", f"shipwright_events.d/{DROP}", f"{DROPS_DIR}/run-a--aaaaaaaa--dddddddd.jsonl")
    _git(move_pr, "commit", "-q", "-m", "moved and renamed")
    found = check_integrity(move_pr, "base", "HEAD", own_keys=("run-a",))
    assert any(v.path == f"shipwright_events.d/{DROP}" for v in found)


def test_the_heal_writes_nothing_where_it_cannot_work(repo):
    (repo / ".gitignore").write_text(".shipwright/\n", encoding="utf-8")  # the whole directory is excluded
    (repo / "shipwright_sync_config.json").write_text(json.dumps({"events_layout": "drops"}), encoding="utf-8")
    assert reinclude_lines(repo) == []


def test_a_nested_old_path_is_never_accepted_as_a_move(move_pr):
    nested = move_pr / "shipwright_events.d" / "sub"
    nested.mkdir()
    (nested / DROP).write_text(LINE, encoding="utf-8")
    _git(move_pr, "add", "-A")
    _git(move_pr, "commit", "-q", "-m", "trunk-side nested file")
    _git(move_pr, "branch", "-f", "base")
    (move_pr / DROPS_DIR).mkdir(parents=True, exist_ok=True)
    _git(move_pr, "mv", f"shipwright_events.d/sub/{DROP}", f"{DROPS_DIR}/{DROP}")
    _git(move_pr, "commit", "-q", "-m", "move out of a nested old path")
    found = check_integrity(move_pr, "base", "HEAD", own_keys=("run-mine",))
    assert any(v.path.endswith(f"sub/{DROP}") for v in found)


def test_the_heal_keeps_the_legacy_log_rule_even_when_the_folder_rules_cannot_work(repo):
    (repo / ".gitignore").write_text(".shipwright/\nshipwright_events.jsonl\n", encoding="utf-8")
    (repo / "shipwright_events.jsonl").write_text("", encoding="utf-8")
    _git(repo, "add", "-f", "shipwright_events.jsonl")
    (repo / "shipwright_sync_config.json").write_text(json.dumps({"events_layout": "drops"}), encoding="utf-8")
    assert reinclude_lines(repo) == ["!/shipwright_events.jsonl"]


def test_migrate_works_when_the_new_folder_already_exists(repo):
    (repo / DROPS_DIR).mkdir(parents=True)
    (repo / DROPS_DIR / "run-z--aaaaaaaa--eeeeeeee.jsonl").write_text(LINE, encoding="utf-8")
    _old_drop(repo)
    assert migrate(repo)["status"] == "migrated"
    assert (repo / DROPS_DIR / DROP).exists()
    assert not (repo / DROPS_DIR / "shipwright_events.d").exists()   # never nested


def test_migrate_drops_os_junk_and_treats_identical_duplicates_as_moved(repo):
    old = _old_drop(repo)
    (old.parent / "Thumbs.db").write_text("x", encoding="utf-8")
    (repo / DROPS_DIR).mkdir(parents=True)
    (repo / DROPS_DIR / DROP).write_text(LINE, encoding="utf-8")   # byte-identical copy already at the new place
    result = migrate(repo)
    assert result["status"] == "migrated"
    assert not (repo / "shipwright_events.d").exists()
    assert not (repo / DROPS_DIR / "Thumbs.db").exists()


def test_a_drop_committed_in_an_ignored_folder_still_passes_the_committed_check(repo):
    from tools.verifiers._events_committed import drops_committed_state, event_stuck_in_ignored_drop
    event = json.dumps({"v": 1, "id": "w1", "ts": "2026-11-06T10:00:00+00:00", "type": "work_completed",
                        "adr_id": "run-a", "commit": "abc1234"}) + chr(10)
    (repo / DROPS_DIR).mkdir(parents=True)
    (repo / DROPS_DIR / DROP).write_text(event, encoding="utf-8")
    (repo / ".gitignore").write_text("/.shipwright/*\n", encoding="utf-8")
    _git(repo, "add", "-f", DROPS_DIR)
    _git(repo, "add", ".gitignore")
    _git(repo, "commit", "-q", "-m", "tracked inside an ignored folder")
    assert drops_committed_state(repo, "abc1234", "run-a", None) is True
    # an uncommitted drop in the ignored folder fails, and the hint applies
    (repo / DROPS_DIR / "run-b--aaaaaaaa--cccccccc.jsonl").write_text(
        event.replace("run-a", "run-b").replace("abc1234", "def5678"), encoding="utf-8")
    assert drops_committed_state(repo, "def5678", "run-b", None) is False
    assert event_stuck_in_ignored_drop(repo, "def5678", "run-b") is True
    assert event_stuck_in_ignored_drop(repo, "zzz", "run-none") is False



def test_a_tracked_old_file_with_an_untracked_identical_copy_keeps_the_copy_tracked(repo):
    _old_drop(repo)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "old layout")
    (repo / DROPS_DIR).mkdir(parents=True)
    (repo / DROPS_DIR / DROP).write_text(LINE, encoding="utf-8")   # copied by hand, never added
    assert migrate(repo)["status"] == "migrated"
    _git(repo, "commit", "-q", "-m", "move")
    assert DROP in _git(repo, "ls-files", DROPS_DIR)               # the commit lost nothing
    assert _git(repo, "ls-files", "shipwright_events.d").strip() == ""


def test_an_untracked_event_is_staged_so_a_plain_commit_ships_it(repo):
    _old_drop(repo)
    assert migrate(repo)["status"] == "migrated"
    _git(repo, "commit", "-q", "-m", "move")
    assert DROP in _git(repo, "ls-tree", "-r", "--name-only", "HEAD", DROPS_DIR)


def test_a_sub_directory_in_an_old_folder_is_refused_and_nothing_moves(repo):
    _old_drop(repo)
    (repo / "shipwright_events.d" / "sub").mkdir()
    result = migrate(repo)
    assert result["status"] == "refused_unexpected_entry" and result["entries"] == ["shipwright_events.d/sub"]
    assert (repo / "shipwright_events.d" / DROP).exists()
