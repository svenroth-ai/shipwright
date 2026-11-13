"""The event folders moved under ``.shipwright/events/``: hard abort on the old root location, readers, symlink guards."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

sys.path.append(str(Path(__file__).resolve().parent))   # the kit; appended so it never shadows scripts/tools
from events_move_kit import DROP, LINE, old_drop as _old_drop  # noqa: E402
from lib.events_log import ARCHIVE_DIR, DROPS_DIR, OLD_ROOT_FOLDERS, QUARANTINE_DIR  # noqa: E402
from lib.events_read import read_events_assembled  # noqa: E402
from lib.events_sentinel import (  # noqa: E402
    MOVED_FOLDERS, UnsupportedEventsLayout, evidence_refusal, old_event_folders, require_writable_layout,
)

pytest_plugins = ["events_move_kit"]   # the repo / move_pr fixtures
pytestmark = pytest.mark.covers("FR-01.11")
SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def test_new_constants_live_under_shipwright_events():
    assert (DROPS_DIR, ARCHIVE_DIR, QUARANTINE_DIR) == (
        ".shipwright/events/drops", ".shipwright/events/archive", ".shipwright/events/quarantine")
    assert list(MOVED_FOLDERS.values()) == [DROPS_DIR, ARCHIVE_DIR, QUARANTINE_DIR]


def test_old_root_folder_aborts_a_write_and_names_the_fix(repo):
    _old_drop(repo)
    assert old_event_folders(repo) == ["shipwright_events.d"]
    with pytest.raises(UnsupportedEventsLayout) as exc:
        require_writable_layout(repo, "drops")
    assert "git mv shipwright_events.d .shipwright/events/drops" in str(exc.value)


def test_old_root_folder_refuses_release_evidence(repo):
    _old_drop(repo)
    refusal = evidence_refusal(repo, "update_compliance")
    assert refusal is not None and refusal["status"] == "refused_events_folder_moved"
    assert refusal["old_folders"] == ["shipwright_events.d"]


def test_new_location_alone_is_fine(repo):
    new = repo / DROPS_DIR
    new.mkdir(parents=True)
    (new / DROP).write_text(LINE, encoding="utf-8")
    assert old_event_folders(repo) == []
    require_writable_layout(repo, "drops")
    assert evidence_refusal(repo, "update_compliance") is None


def test_a_file_or_symlink_named_like_the_old_folder_is_not_a_folder(repo):
    (repo / "shipwright_events.d").write_text("not a folder\n", encoding="utf-8")
    assert old_event_folders(repo) == []


def test_the_old_name_lists_agree_between_the_sentinel_and_the_log_module():
    assert tuple(MOVED_FOLDERS) == OLD_ROOT_FOLDERS


def test_a_reader_never_takes_an_old_root_folder_for_no_events(repo):
    _old_drop(repo)
    read = read_events_assembled(repo)
    assert [f.status for f in read.skipped_files] == ["unreadable"]
    assert read.absence_blockers("any-run")  # an absence gate cannot conclude "this run recorded nothing"
    assert read.records == []                # and nothing was read from the old location


def test_a_clean_repo_has_no_blockers(repo):
    assert read_events_assembled(repo).skipped_files == []


def test_the_real_writer_cli_aborts_with_a_visible_error_and_writes_nothing(repo):
    _old_drop(repo)
    (repo / "shipwright_sync_config.json").write_text(json.dumps({"events_layout": "drops"}), encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(SCRIPTS / "tools" / "record_event.py"), "--project-root", str(repo),
         "--type", "task_created", "--description", "d", "--run-id", "run-x"],
        capture_output=True, text=True, encoding="utf-8", timeout=120)
    assert proc.returncode == 1, proc.stderr
    out = json.loads(proc.stdout)
    assert out["success"] is False and out["error"] == "unsupported_events_layout"
    assert "git mv shipwright_events.d .shipwright/events/drops" in out["detail"]
    assert "plugin that predates the move" in out["detail"]
    assert not (repo / DROPS_DIR).exists()


@pytest.mark.parametrize("relative", [False, True])
def test_an_archive_file_is_an_archive_whatever_the_root_spelling(repo, monkeypatch, relative):
    arch = repo / ARCHIVE_DIR
    arch.mkdir(parents=True)
    (arch / "fold-aaaaaaaaaaaa.jsonl").write_text('{"id": "x"}' + chr(10), encoding="utf-8")  # no event: a non-ok archive file
    monkeypatch.chdir(repo)
    read = read_events_assembled(Path(".") if relative else repo)
    assert [f.kind for f in read.files if "fold-" in f.path] == ["archive"]
    assert read.absence_blockers("any-run") == []  # only drops can block a run's absence gate


def _link_or_skip(link: Path, target: Path) -> None:
    try:
        link.symlink_to(target, target_is_directory=True)
    except (OSError, NotImplementedError):
        if os.environ.get("CI", "").lower() in ("true", "1"):
            raise AssertionError("symlinks must work in CI") from None
        pytest.skip("no symlink privilege on this machine")


def test_a_symlink_anywhere_in_the_nested_path_hides_the_folder(repo, tmp_path):
    from lib.events_log import event_files, real_event_dir
    outside = tmp_path / "outside"
    (outside / "events" / "drops").mkdir(parents=True)
    (outside / "events" / "drops" / DROP).write_text(LINE, encoding="utf-8")
    _link_or_skip(repo / ".shipwright", outside)          # the PARENT is the link, the leaf is a real folder
    assert real_event_dir(repo, DROPS_DIR) is False
    assert [p for p in event_files(repo) if p.name == DROP] == []


def test_a_symlinked_events_dir_is_not_counted_as_open_drops(repo, tmp_path):
    from lib.events_open_warning import count_open_drop_files
    outside = tmp_path / "outside"
    (outside / "drops").mkdir(parents=True)
    (outside / "drops" / DROP).write_text(LINE, encoding="utf-8")
    (repo / ".shipwright").mkdir()
    _link_or_skip(repo / ".shipwright" / "events", outside)
    assert count_open_drop_files(repo) == 0


def test_a_folder_holding_only_os_junk_is_not_an_old_event_folder(repo):
    junk = repo / "shipwright_events.d"
    junk.mkdir()
    (junk / ".DS_Store").write_text("x", encoding="utf-8")
    assert old_event_folders(repo) == []
    require_writable_layout(repo, "drops")
    _old_drop(repo)
    assert old_event_folders(repo) == ["shipwright_events.d"]


def test_name_copies_in_the_sentinel_adopt_and_grade_match_the_log_module():
    import re
    from lib import events_sentinel
    root = Path(__file__).resolve().parents[2]
    assert events_sentinel.DROPS_DIR == DROPS_DIR
    from lib.events_log import OS_JUNK_NAMES
    assert events_sentinel.OS_JUNK_NAMES == OS_JUNK_NAMES
    layout_key = (root / "plugins/shipwright-adopt/scripts/lib/events_layout_key.py").read_text(encoding="utf-8")
    assert DROPS_DIR in layout_key
    adopt =(root / "plugins/shipwright-adopt/scripts/lib/event_seeder.py").read_text(encoding="utf-8")
    assert re.search(r'^_DROPS_DIR = "' + re.escape(DROPS_DIR) + '"', adopt, re.M)
    for rel in ("routing.py", "authoritative.py"):
        grade = (root / "plugins/shipwright-grade/scripts/lib" / rel).read_text(encoding="utf-8")
        assert f'("{DROPS_DIR}", "{ARCHIVE_DIR}")' in grade


def test_abort_message_leads_with_the_tool_and_warns_about_nesting(repo):
    _old_drop(repo)
    with pytest.raises(UnsupportedEventsLayout) as exc:
        require_writable_layout(repo, "drops")
    text = str(exc.value)
    assert text.index("migrate_events_folder.py") < text.index("git mv")
    assert "does not exist yet" in text


def test_the_tool_path_named_in_the_abort_message_exists(repo):
    _old_drop(repo)
    with pytest.raises(UnsupportedEventsLayout) as exc:
        require_writable_layout(repo, "drops")
    assert "<shipwright>/shared/scripts/tools/migrate_events_folder.py" in str(exc.value)
    assert (Path(__file__).resolve().parents[1] / "scripts" / "tools" / "migrate_events_folder.py").is_file()


def test_a_symlink_named_like_the_old_folder_is_not_an_old_folder(repo, tmp_path):
    real = tmp_path / "elsewhere"
    real.mkdir()
    (real / DROP).write_text(LINE, encoding="utf-8")
    _link_or_skip(repo / "shipwright_events.d", real)
    assert old_event_folders(repo) == []           # deliberate: a link is never followed, so it neither aborts nor is read
    require_writable_layout(repo, "drops")
