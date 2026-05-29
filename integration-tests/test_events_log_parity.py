"""Parity: the shared event-log resolver agrees with the compliance copy.

``shared/scripts/lib/events_log.py::resolve_events_path`` and
``plugins/shipwright-compliance/.../data_collector.py::_resolve_events_path``
are intentionally separate implementations — the compliance plugin is a
standalone distributable that cannot import ``shared/scripts/lib`` without a
cross-plugin path bootstrap. This test is the drift-guard that keeps the two
returning the SAME path so the event-log producer (record_event, shared) and
the compliance RTM consumer never disagree on where the log lives.

(The shared helper deliberately drops ``--path-format=absolute`` for Git
2.31 compatibility; both still resolve to the same path on a modern git.)
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO / "shared" / "scripts"))

from lib.events_log import resolve_events_path  # noqa: E402

_GIT_ENV = {
    **os.environ,
    "GIT_AUTHOR_NAME": "T", "GIT_AUTHOR_EMAIL": "t@t.invalid",
    "GIT_COMMITTER_NAME": "T", "GIT_COMMITTER_EMAIL": "t@t.invalid",
}


def _load_compliance_resolver():
    """Import ``_resolve_events_path`` from the compliance plugin.

    Campaign-B B2 moved the resolver from ``data_collector.py`` into
    the ``collectors/change_history.py`` submodule. ``data_collector.py``
    is now a re-export shim that uses relative imports — those don't
    resolve under ``spec_from_file_location`` (no parent package). The
    canonical fix is to add the compliance plugin root onto sys.path
    and import via the package machinery.
    """
    compliance_plugin = _REPO / "plugins" / "shipwright-compliance"
    sys.path.insert(0, str(compliance_plugin))
    try:
        from scripts.lib.collectors.change_history import (  # type: ignore[import-not-found]
            _resolve_events_path,
        )
    finally:
        sys.path.remove(str(compliance_plugin))
    return _resolve_events_path


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(cwd), *args], env=_GIT_ENV,
                   capture_output=True, text=True, check=True)


@pytest.fixture
def main_repo(tmp_path):
    main = tmp_path / "main"
    main.mkdir()
    subprocess.run(["git", "init", "-b", "main", str(main)], env=_GIT_ENV,
                   capture_output=True, text=True, check=True)
    (main / "README.md").write_text("x\n", encoding="utf-8")
    _git(main, "add", "-A")
    _git(main, "commit", "-m", "init")
    return main


def test_parity_in_main_repo(main_repo):
    compliance_resolve = _load_compliance_resolver()
    shared = resolve_events_path(main_repo).resolve()
    compliance = compliance_resolve(main_repo).resolve()
    assert shared == compliance == (main_repo / "shipwright_events.jsonl").resolve()


def test_parity_inside_worktree(main_repo):
    """The case that matters: from a linked worktree both resolvers must agree
    on the WORKTREE's own log — events.jsonl is a per-tree, PR-committed
    artifact (F6 stages it, it merges to main via the PR). Parity is what this
    guard pins; the shared target flipped to worktree-local in
    iterate-2026-05-29-events-jsonl-worktree-commit, and the compliance copy
    must flip in lockstep."""
    compliance_resolve = _load_compliance_resolver()
    wt = main_repo / ".worktrees" / "probe"
    _git(main_repo, "worktree", "add", str(wt), "-b", "iterate/probe", "main")
    shared = resolve_events_path(wt).resolve()
    compliance = compliance_resolve(wt).resolve()
    assert shared == compliance == (wt / "shipwright_events.jsonl").resolve()


def test_parity_non_git_dir(tmp_path):
    compliance_resolve = _load_compliance_resolver()
    shared = resolve_events_path(tmp_path).resolve()
    compliance = compliance_resolve(tmp_path).resolve()
    assert shared == compliance == (tmp_path / "shipwright_events.jsonl").resolve()
