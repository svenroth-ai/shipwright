"""The fork prep script of the e2e harness: boundary detection, cleanup of later files, plugin identity."""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parent / "e2e-webui" / "fork" / "fork_run.py"
spec = importlib.util.spec_from_file_location("fork_run", SCRIPT)
fork_run = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fork_run)


def git(repo: Path, *args: str) -> str:
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    return subprocess.run(["git", "-C", str(repo), "-c", "commit.gpgsign=false", *args], capture_output=True, text=True, check=True, env=env).stdout


def config(*tasks: tuple[str, str, str, list[str]]) -> str:
    return json.dumps({"phase_tasks": [
        {"phaseTaskId": i, "phase": ph, "splitId": sp, "status": st, "prerequisites": pre} for i, (ph, sp, st, pre) in [(f"t{n}", t) for n, t in enumerate(tasks)]
    ]})


def commit_config(repo: Path, text: str, message: str) -> str:
    (repo / "shipwright_run_config.json").write_text(text, encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", message)
    return git(repo, "rev-parse", "HEAD").strip()


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    repo = tmp_path / "project"
    repo.mkdir()
    git(repo, "init", "-q")
    (repo / ".gitignore").write_text("cache/\n", encoding="utf-8")
    return repo


def test_boundary_is_the_first_commit_where_all_prerequisites_are_done(project: Path) -> None:
    commit_config(project, config(("plan", "01", "in_progress", []), ("build", "01", "backlog", ["t0"])), "plan running")
    ready = commit_config(project, config(("plan", "01", "done", []), ("build", "01", "awaiting_launch", ["t0"])), "plan done")
    commit_config(project, config(("plan", "01", "done", []), ("build", "01", "in_progress", ["t0"])), "build running")
    commit, task = fork_run.boundary_commit(project, "build", "01")
    assert commit == ready
    assert task["phase"] == "build"


def test_a_phase_that_never_became_ready_is_an_error(project: Path) -> None:
    commit_config(project, config(("plan", "01", "in_progress", []), ("build", "01", "backlog", ["t0"])), "plan running")
    with pytest.raises(SystemExit):
        fork_run.boundary_commit(project, "build", "01")


def test_ignored_files_newer_than_the_boundary_go_and_dependency_folders_stay(project: Path) -> None:
    boundary = commit_config(project, config(("plan", "01", "done", [])), "boundary")
    when = int(git(project, "log", "-1", "--format=%ct", boundary))
    (project / "cache").mkdir()
    (project / "node_modules").mkdir()
    old, new, deps = project / "cache" / "old.json", project / "cache" / "new.json", project / "node_modules" / "x.js"
    for f in (old, new, deps):
        f.write_text("x", encoding="utf-8")
    os.utime(old, (when - 5, when - 5))
    os.utime(new, (when + 300, when + 300))
    os.utime(deps, (when + 300, when + 300))
    (project / ".gitignore").write_text("cache/\nnode_modules/\n", encoding="utf-8")
    removed, kept = fork_run.drop_later_ignored(project, when)
    assert (removed, kept) == (1, 1)
    assert old.exists() and deps.exists() and not new.exists()


def test_plugin_identity_is_the_trees_of_plugins_and_shared_and_refuses_a_dirty_tree(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    for d in ("plugins", "shared", "integration-tests"):
        (repo / d).mkdir(parents=True)
        (repo / d / "f.txt").write_text("1", encoding="utf-8")
    git(repo, "init", "-q")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "one")
    first = fork_run.plugin_identity(repo)
    assert first.startswith("plugins:") and " shared:" in first
    (repo / "integration-tests" / "f.txt").write_text("2", encoding="utf-8")
    git(repo, "commit", "-qam", "harness only")
    assert fork_run.plugin_identity(repo) == first
    (repo / "plugins" / "f.txt").write_text("2", encoding="utf-8")
    with pytest.raises(SystemExit):
        fork_run.plugin_identity(repo)


def test_a_project_copy_without_its_own_repo_is_refused(tmp_path: Path) -> None:
    outer = tmp_path / "outer"
    inner = outer / "project"
    inner.mkdir(parents=True)
    git(outer, "init", "-q")
    with pytest.raises(SystemExit):
        fork_run.require_own_repo(inner)
    git(inner, "init", "-q")
    fork_run.require_own_repo(inner)  # its own repo: fine
