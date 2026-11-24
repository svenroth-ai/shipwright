"""The closed fix list carried from the P3 reviews (PR #1099), each with a case the P3 code fails.

Old behaviour, per test: the upgrade-note drop was written before the questions were answered; the page id used SHA-1;
``--from`` and the task id went to a tool unvalidated; the orchestrator lookup took an orphaned cache version first; the run
state was keyed by the git directory only; the preview named no ADR numbers.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path

import pytest

from lib import release_aggregate, release_paths, release_prepare, release_runstate, release_upgrade_notes
from lib.release_runner import Recorder

import release

from .test_release_cli import NOW, ROWS, Fake, ok_runner, run_prepare

pytestmark = pytest.mark.covers("FR-01.09/AC01")

PAGE = "docs/migrations/0.9.md"
PAGE_TEXT = "# 0.9\n\n**Do you have to do anything?** Yes, rename the config key.\n"


def _with_page(tmp_path: Path) -> None:
    (tmp_path / "docs/migrations").mkdir(parents=True)
    (tmp_path / PAGE).write_text(PAGE_TEXT, encoding="utf-8")


def _runner(tmp_path: Path, **over) -> Fake:
    _with_page(tmp_path)
    return ok_runner(**{"migration-pages": {"stdout": PAGE + "\0"}, **over})


def test_an_open_question_leaves_the_tree_clean_and_aggregate_files_the_note(tmp_path, plugin_root):
    fake = _runner(tmp_path)  # standalone + guided: the version question is open
    code, out = run_prepare(tmp_path, plugin_root, fake)
    assert code == 0 and out["gates"]["version"] == "ask"
    assert out["upgrade_notes"]["status"] == "action_drop_deferred" and "upgrade-note-drop" not in fake.keys()
    assert not (tmp_path / "CHANGELOG-unreleased.d").exists()
    agg = Fake(**{"tag-check": {"exit": 1}, "aggregate": {"stdout": json.dumps({"version": "1.3.0", "section_action": "inserted"})}})
    preview = release_aggregate.aggregate(Recorder(agg, tmp_path), plugin_root, version="1.3.0", dry_run=True, clock=lambda: NOW)[1]
    assert "upgrade-note-drop" not in agg.keys() and len(preview["upgrade_notes_pending"]) == 1
    code, _ = release_aggregate.aggregate(Recorder(agg, tmp_path), plugin_root, version="1.3.0", clock=lambda: NOW)
    assert code == 0 and agg.keys().count("upgrade-note-drop") == 1
    assert agg.keys().index("upgrade-note-drop") < agg.keys().index("aggregate")  # filed before the aggregator reads the drops


def test_an_answered_question_writes_the_note_at_prepare_as_before(tmp_path, plugin_root):
    rows = [{**r, "policy": "auto-default"} if r["gate_id"].endswith("out-of-sequence-continue") else r for r in ROWS]
    fake = _runner(tmp_path, context={"stdout": json.dumps({"mode": "pipeline", "requires_out_of_sequence_warning": True})},
                   gates={"stdout": json.dumps({"gates": rows})})
    _, out = run_prepare(tmp_path, plugin_root, fake)
    assert out["upgrade_notes"]["status"] == "action_drop_written" and "upgrade-note-drop" in fake.keys()


def test_an_out_of_sequence_question_that_asks_defers_the_note_even_when_the_version_is_auto(tmp_path, plugin_root):
    fake = _runner(tmp_path, context={"stdout": json.dumps({"mode": "pipeline", "requires_out_of_sequence_warning": True})})
    _, out = run_prepare(tmp_path, plugin_root, fake)
    assert out["gates"] == {"version": "auto", "preview": "auto", "out_of_sequence": "ask"}
    assert out["upgrade_notes"]["status"] == "action_drop_deferred" and "upgrade-note-drop" not in fake.keys()


def test_the_page_id_is_a_sha256_prefix():
    run_id = release_upgrade_notes._run_id("docs/migrations/a/b.md")
    want = hashlib.sha256(b"a/b").hexdigest()[:8]
    assert run_id == f"upgrade-notes-a-b-{want}" and re.fullmatch(r"upgrade-notes-a-b-[0-9a-f]{8}", run_id)


@pytest.mark.parametrize(("flag", "bad"), [("--from", "v1; rm -rf ."), ("--from", "main"), ("--phase-task-id", "a b"),
                                           ("--phase-task-id", "$(id)"), ("--phase-task-id", "-x")])
def test_a_malformed_from_or_task_id_is_refused_before_any_tool_runs(tmp_path, flag, bad):
    fake = ok_runner()
    with pytest.raises(SystemExit) as stop:
        release.main(["prepare", "--project-root", str(tmp_path), flag, bad], runner=fake)
    assert stop.value.code == 2 and fake.calls == []


def test_a_well_formed_from_and_task_id_pass(tmp_path):
    fake = ok_runner()
    release.main(["prepare", "--project-root", str(tmp_path), "--from", "v0.1.0", "--phase-task-id", "pt-1.a:b"], runner=fake)
    assert "--from" in fake.argv("setup") and "pt-1.a:b" in fake.argv("context")


def _cache(tmp_path: Path, own: str, run_versions: dict[str, bool]) -> Path:
    base = tmp_path / "cache" / "shipwright"
    plugin = base / "shipwright-changelog" / own
    plugin.mkdir(parents=True)
    for version, orphaned in run_versions.items():
        target = base / "shipwright-run" / version
        (target / "scripts" / "lib").mkdir(parents=True)
        (target / "scripts" / "lib" / "orchestrator.py").write_text("", encoding="utf-8")
        if orphaned:
            (target / ".orphaned_at").write_text("1", encoding="utf-8")
    return plugin


def test_the_same_version_run_plugin_wins_and_an_orphaned_one_is_never_used(tmp_path):
    plugin = _cache(tmp_path, "0.20.0", {"0.20.0": False, "0.30.0": False})
    assert release_paths.orchestrator_path(plugin).parts[-4] == "0.20.0"  # newer exists, the sibling of the same version wins
    plugin = _cache(tmp_path / "b", "0.20.0", {"0.10.0": False, "0.30.0": True})
    assert release_paths.orchestrator_path(plugin).parts[-4] == "0.10.0"  # the newest is orphaned: skipped


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, encoding="utf-8")


def test_the_run_state_belongs_to_its_project_root_not_to_the_shared_git_directory(tmp_path):
    _git(tmp_path, "init", "-q")
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    state = release_runstate.resolve(tmp_path / "a", "1.0.0", tag_exists=False, clock=lambda: NOW)
    release_runstate.save(tmp_path / "a", state)
    assert release_runstate.state_path(tmp_path / "a").resolve() == release_runstate.state_path(tmp_path / "b").resolve()  # one git directory
    assert release_runstate.load(tmp_path / "a")["run_id"] == state["run_id"]
    assert release_runstate.load(tmp_path / "b") is None
    other = release_runstate.resolve(tmp_path / "b", "1.0.0", tag_exists=False, clock=lambda: NOW)
    assert other["reused"] is False


def test_the_preview_names_the_adr_numbers_the_real_run_will_give(tmp_path, plugin_root):
    fake = Fake(**{"tag-check": {"exit": 1}, "aggregate-dry": {"stdout": json.dumps({"version": "1.3.0"})},
                   "decisions-dry": {"stdout": "[dry-run] aggregated 2 decision-drop(s): ADR-007, ADR-008\n"}})
    code, out = release_aggregate.aggregate(Recorder(fake, tmp_path), plugin_root, version="1.3.0", dry_run=True, clock=lambda: NOW)
    assert code == 0 and "ADR-007, ADR-008" in out["decisions_preview"]["summary"]
    assert "--dry-run" in fake.argv("decisions-dry") and "decisions" not in fake.keys()


def test_prepare_still_writes_nothing_for_a_release_with_no_page(tmp_path, plugin_root):
    _, out = release_prepare.prepare(Recorder(ok_runner(), tmp_path), plugin_root, clock=lambda: NOW)
    assert out["upgrade_notes"]["status"] == "none_changed" and out["upgrade_notes"]["pending"] == []
