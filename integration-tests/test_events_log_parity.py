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
    """Import data_collector._resolve_events_path by file path (cross-plugin).

    The module is registered in ``sys.modules`` before execution: its
    ``@dataclass`` definitions resolve string annotations via
    ``sys.modules[cls.__module__]``, which would be ``None`` otherwise.
    """
    name = "_compliance_data_collector"
    if name in sys.modules:
        return sys.modules[name]._resolve_events_path
    path = (_REPO / "plugins" / "shipwright-compliance" / "scripts"
            / "lib" / "data_collector.py")
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod._resolve_events_path


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
    """The case that matters: from a linked worktree both resolvers must
    point at the MAIN repo's log, not the throwaway worktree copy."""
    compliance_resolve = _load_compliance_resolver()
    wt = main_repo / ".worktrees" / "probe"
    _git(main_repo, "worktree", "add", str(wt), "-b", "iterate/probe", "main")
    shared = resolve_events_path(wt).resolve()
    compliance = compliance_resolve(wt).resolve()
    assert shared == compliance == (main_repo / "shipwright_events.jsonl").resolve()


def test_parity_non_git_dir(tmp_path):
    compliance_resolve = _load_compliance_resolver()
    shared = resolve_events_path(tmp_path).resolve()
    compliance = compliance_resolve(tmp_path).resolve()
    assert shared == compliance == (tmp_path / "shipwright_events.jsonl").resolve()
