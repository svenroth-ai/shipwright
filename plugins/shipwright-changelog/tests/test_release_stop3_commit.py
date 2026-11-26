"""Stop 3 (FINDINGS D21, D22, D23, D25): what ``commit-and-tag`` commits and when it refuses, on real git.

git runs for real; the three tools the chain calls after the commit (release audit, manifest verify, tag check) are stubs that
pass, so each test is about the commit itself. ``sync`` and ``aggregate`` are run with their tools stubbed to write exactly what
the real ones write (a ``grade_snapshot`` drop, a consumed tracked drop), so the facts they keep in the run state are the ones
Step 6 then reads.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from lib import release_aggregate, release_commit, release_runstate, release_sync
from lib.release_runner import CmdResult, Recorder, subprocess_runner

pytestmark = pytest.mark.covers("FR-01.09/AC01")
VERSION = "1.3.0"
PLUGIN = Path(__file__).resolve().parents[1]
EVIDENCE = ".shipwright/compliance/dashboard.md"
DROP = "CHANGELOG-unreleased.d/Added/iterate-2026-11-01-a_001.md"
GRADE = ".shipwright/events/drops/release--s1--0001.jsonl"


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True, encoding="utf-8").stdout.strip()


def write(root: Path, rel: str, text: str) -> None:
    (root / rel).parent.mkdir(parents=True, exist_ok=True)
    (root / rel).write_text(text, encoding="utf-8", newline="\n")


@pytest.fixture
def work(tmp_path, monkeypatch):
    """A project after Step 5.5: CHANGELOG and the decision log rewritten, the evidence staged; no decision-drops/ or adr/ folder."""
    config = tmp_path / "gitconfig"
    config.write_text("[user]\n\tname = t\n\temail = t@example.com\n[commit]\n\tgpgsign = false\n[init]\n\tdefaultBranch = main\n", encoding="utf-8")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(config))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    root = tmp_path / "work"
    root.mkdir()
    git(root, "init", "-q")
    for rel in ("CHANGELOG.md", ".shipwright/agent_docs/decision_log.md", EVIDENCE, "app.txt"):
        write(root, rel, "before\n")
    write(root, ".gitignore", ".shipwright/runtime/\n")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "chore: project")
    write(root, "CHANGELOG.md", f"# Changelog\n\n## [{VERSION}] - 2026-11-26\n\n### Added\n\n- x\n")
    write(root, ".shipwright/agent_docs/decision_log.md", "after\n")
    write(root, ".shipwright/agent_docs/decision_log_index.md", "index\n")
    write(root, EVIDENCE, "regenerated\n")
    git(root, "add", "--", EVIDENCE)
    return root


def state(root: Path, **extra) -> None:
    release_runstate.save(root, {"schema": 1, "version": VERSION, "release_date": "2026-11-26", "run_id": "release-v1-3-0",
                                 "created_at": "2026-11-26T00:00:00+00:00", "evidence_pathspec": [EVIDENCE], "manifest_pathspec": [],
                                 **extra})


def passing_tools(key, argv, cwd, **opts):
    if key in ("verify-evidence", "verify-manifests"):
        return CmdResult(key, tuple(argv), 0, "{}")
    if key == "verify-tag":
        return CmdResult(key, tuple(argv), 0, json.dumps({"checks": {"tag_exists": {"ok": True}}}))
    return subprocess_runner(key, argv, cwd, **opts)


def commit_and_tag(root: Path) -> tuple[int, dict]:
    return release_commit.commit_and_tag(Recorder(passing_tools, root), PLUGIN, version=VERSION)


def test_d21_a_project_without_decision_folders_is_committed_and_tagged(work):
    state(work)
    code, out = commit_and_tag(work)
    assert code == 0 and out["status"] == "ok", out.get("reason")
    assert git(work, "log", "-1", "--format=%s") == f"chore(release): v{VERSION}" and git(work, "tag") == f"v{VERSION}"
    assert git(work, "status", "--porcelain") == ""
    assert not any(c["argv"][:3] == ["git", "add", "-A"] and len(c["argv"]) <= 4 for c in out["commands"])  # never a bare `git add -A`


def test_d21_the_pathspec_names_only_paths_that_exist_in_the_tree_or_the_index(work):
    _, _, paths = release_commit.commit_pathspec(work, {"evidence_pathspec": [EVIDENCE], "manifest_pathspec": ["package.json"]})
    assert paths == ["CHANGELOG.md", ".shipwright/agent_docs/decision_log.md", ".shipwright/agent_docs/decision_log_index.md", EVIDENCE]
    write(work, ".shipwright/planning/adr/ADR-001.md", "a\n")  # an untracked ADR file: the folder is named again
    assert ".shipwright/planning/adr/" in release_commit.commit_pathspec(work, {})[2]


def test_d22_the_deletion_of_a_consumed_tracked_drop_is_part_of_the_release_commit(work):
    write(work, DROP, "- x\n")
    git(work, "add", "--", DROP)
    git(work, "commit", "-q", "-m", "docs(changelog): a tracked drop", "--", DROP)
    (work / DROP).unlink()  # the aggregate consumed it
    state(work, consumed_drops=[DROP, "CHANGELOG-unreleased.d/Fixed/untracked_001.md"])  # an untracked one is simply gone
    code, out = commit_and_tag(work)
    assert code == 0, out
    assert f"D\t{DROP}" in git(work, "show", "--name-status", "--format=", "HEAD").splitlines()
    assert git(work, "status", "--porcelain") == ""


def test_d22_a_drop_the_aggregate_could_not_delete_is_not_committed_but_named(work):
    """D105: the aggregator only warns when it cannot unlink a consumed drop; such a file is not the release's to commit."""
    write(work, "CHANGELOG-unreleased.d/Fixed/stuck_001.md", "- y\n")
    state(work, consumed_drops=["CHANGELOG-unreleased.d/Fixed/stuck_001.md"])
    code, out = commit_and_tag(work)
    assert code == 1 and out["reason"] == "unrelated_changes" and out["unrelated"] == ["CHANGELOG-unreleased.d/Fixed/stuck_001.md"]


@pytest.mark.parametrize("layout", ["drops", "legacy"])
def test_d23_the_event_step_5_5_wrote_is_part_of_the_release_commit(work, layout):
    if layout == "legacy":
        write(work, "shipwright_events.jsonl", '{"type":"work_completed"}\n')
        git(work, "add", "--", "shipwright_events.jsonl")
        git(work, "commit", "-q", "-m", "chore: events", "--", "shipwright_events.jsonl")
        with open(work / "shipwright_events.jsonl", "a", encoding="utf-8") as handle:
            handle.write('{"type":"grade_snapshot"}\n')
        events = ["shipwright_events.jsonl"]
    else:
        write(work, GRADE, '{"type":"grade_snapshot"}\n')
        events = [GRADE]
    state(work, events_pathspec=events)
    code, out = commit_and_tag(work)
    assert code == 0, out
    assert events[0] in git(work, "show", "--name-only", "--format=", "HEAD").splitlines()
    assert git(work, "status", "--porcelain") == ""


@pytest.mark.parametrize("dirt", ["staged", "unstaged", "untracked"])
def test_d25_unrelated_changes_stop_the_release_before_anything_is_committed(work, dirt):
    if dirt == "staged":
        write(work, "wip.txt", "a person was in the middle of this\n")
        git(work, "add", "--", "wip.txt")
        name = "wip.txt"
    elif dirt == "unstaged":
        write(work, "app.txt", "changed\n")
        name = "app.txt"
    else:
        write(work, "notes/stray.txt", "not part of the release\n")
        name = "notes/stray.txt"
    state(work)
    head, index = git(work, "rev-parse", "HEAD"), git(work, "diff", "--cached", "--name-only")
    code, out = commit_and_tag(work)
    assert code == 1 and out["status"] == "failed" and out["reason"] == "unrelated_changes"
    assert out["unrelated"] == [name] and name in out["message"]
    assert git(work, "rev-parse", "HEAD") == head and git(work, "tag") == ""  # no commit, no tag
    assert git(work, "diff", "--cached", "--name-only") == index  # and nothing staged: the person's index is as it was
    assert [c["key"] for c in out["commands"]] == ["tree-check"]


def test_d25_what_the_release_wrote_is_never_unrelated(work):
    write(work, ".shipwright/agent_docs/decision-drops/run_001.md", "d\n")  # swept by the decision-drops folder
    write(work, GRADE, '{"type":"grade_snapshot"}\n')
    state(work, events_pathspec=[GRADE])
    code, out = commit_and_tag(work)
    assert code == 0, out
    assert git(work, "status", "--porcelain") == ""


def test_d25_a_rename_names_both_sides():
    assert release_commit.unrelated_changes("R  new.txt\0old.txt\0 M CHANGELOG.md\0", ["CHANGELOG.md"]) == ["new.txt", "old.txt"]


def test_d25_a_tree_check_git_cannot_answer_stops_before_anything_is_staged(work):
    """External review (stop 3): a failed ``git status`` is never read as a clean tree."""
    def failing_status(key, argv, cwd, **opts):
        return CmdResult(key, tuple(argv), 128, "") if key == "tree-check" else passing_tools(key, argv, cwd, **opts)
    state(work)
    before = git(work, "diff", "--cached", "--name-only")
    code, out = release_commit.commit_and_tag(Recorder(failing_status, work), PLUGIN, version=VERSION)
    assert (code, out["reason"]) == (128, "tree_check_failed")
    assert [c["key"] for c in out["commands"]] == ["tree-check"] and git(work, "diff", "--cached", "--name-only") == before
    assert git(work, "log", "-1", "--format=%s") == "chore: project"


def test_d21_a_staged_deletion_of_the_last_file_under_a_release_folder_is_committed(work):
    """External review (stop 3): a folder whose last tracked file is staged for deletion is still git's, so still in the pathspec."""
    write(work, ".shipwright/agent_docs/decision-drops/old_001.json", "{}\n")
    git(work, "add", "--", ".shipwright/agent_docs/decision-drops/old_001.json")
    git(work, "commit", "-q", "-m", "chore: a drop", "--", ".shipwright/agent_docs/decision-drops/old_001.json")
    git(work, "rm", "-q", "--", ".shipwright/agent_docs/decision-drops/old_001.json")
    assert ".shipwright/agent_docs/decision-drops/" in release_commit.commit_pathspec(work, {})[2]
    state(work)
    code, out = commit_and_tag(work)
    assert code == 0 and out["status"] == "ok", out
    assert "D\t.shipwright/agent_docs/decision-drops/old_001.json" in git(work, "show", "--name-status", "--format=", "HEAD")


def test_d25_a_project_in_a_subfolder_of_the_work_tree_is_released(work):
    """``git status`` names paths from the top of the work tree, the pathspec from the project root (code review, stop 3): a
    project in a subfolder is still released, and a change outside it is named as unrelated."""
    project = work / "app"
    for rel in ("CHANGELOG.md", ".shipwright/agent_docs/decision_log.md", EVIDENCE):
        write(project, rel, "before\n")
    git(work, "add", "-A")
    git(work, "commit", "-q", "-m", "chore: the app")
    write(project, "CHANGELOG.md", f"# Changelog\n\n## [{VERSION}] - 2026-11-26\n")
    write(project, EVIDENCE, "regenerated\n")
    git(project, "add", "--", EVIDENCE)
    write(work, "app.txt", "outside the project\n")
    state(project)
    code, out = commit_and_tag(project)
    assert (code, out["reason"], out["unrelated"]) == (1, "unrelated_changes", ["app.txt"])  # named from the top, outside the project
    git(work, "checkout", "--", "app.txt")
    code, out = commit_and_tag(project)
    assert code == 0 and out["status"] == "ok", out
    assert git(work, "show", "--name-only", "--format=", "HEAD").splitlines() == ["app/.shipwright/compliance/dashboard.md", "app/CHANGELOG.md"]
    assert release_commit.unrelated_changes(" M app/CHANGELOG.md\0?? CHANGELOG.md\0", ["CHANGELOG.md"], "app/") == ["CHANGELOG.md"]


def test_d23_sync_keeps_the_event_files_step_5_5_wrote(work):
    """``sync`` compares the event files before and after the compliance run; an event file that was there and unchanged is not named."""
    write(work, ".shipwright/events/drops/older--s0--0001.jsonl", '{"type":"work_completed"}\n')
    state(work)

    def tools(key, argv, cwd, **opts):
        if key == "fold-events":
            return CmdResult(key, tuple(argv), 0, json.dumps({"status": "not_applicable"}))
        if key == "sync":
            return CmdResult(key, tuple(argv), 0, json.dumps({"status": "ok", "manifest_pathspec": []}))
        if key == "evidence":
            write(Path(cwd), GRADE, '{"type":"grade_snapshot"}\n')  # what update_compliance's grade emitter does under the drops layout
            return CmdResult(key, tuple(argv), 0, json.dumps({"status": "ok", "evidence_pathspec": [EVIDENCE]}))
        raise AssertionError(key)

    code, out = release_sync.sync(Recorder(tools, work), PLUGIN, version=VERSION)
    assert code == 0 and out["events"]["pathspec"] == [GRADE]
    assert release_runstate.stored(work, VERSION)["events_pathspec"] == [GRADE]


def test_d22_aggregate_keeps_the_drops_it_consumed(work):
    state(work)

    def tools(key, argv, cwd, **opts):
        if key == "tag-check":
            return CmdResult(key, tuple(argv), 1)
        if key == "aggregate":
            return CmdResult(key, tuple(argv), 0, json.dumps({"version": VERSION, "section_written": "s", "processed_files": [DROP.replace("/", "\\")]}))
        if key == "decisions":
            return CmdResult(key, tuple(argv), 0)
        raise AssertionError(key)

    code, _ = release_aggregate.aggregate(Recorder(tools, work), PLUGIN, version=VERSION)
    assert code == 0 and release_runstate.stored(work, VERSION)["consumed_drops"] == [DROP]
