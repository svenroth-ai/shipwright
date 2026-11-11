"""Shared fixtures for the release-fold tests (``test_events_fold_for_release*.py``)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(_SCRIPTS))
sys.path.append(str(Path(__file__).resolve().parent))   # after shared/scripts: tests/ has its own `tools`

from _events_fold_helpers import NEW, OLD, archive_names, commit, drop, ev, git, make_repo  # noqa: E402
from lib import events_fold  # noqa: E402,F401
from lib.events_fold_io import event_hash  # noqa: E402
from lib.events_log import DROPS_DIR  # noqa: E402
from lib.events_read import read_events_assembled  # noqa: E402
from tools import fold_events_for_release as tool  # noqa: E402



def _repo(tmp_path, layout: str | None = "drops"):
    root = make_repo(tmp_path)
    if layout:
        (root / "shipwright_sync_config.json").write_text(json.dumps({"events_layout": layout}), encoding="utf-8")
    drop(root, "run-old", ev("e1"), ev("e2", OLD))
    drop(root, "run-new", ev("e3", NEW))
    commit(root, "drops")
    return root


def _run(root, **kw) -> dict:
    return tool.fold_for_release(str(root), base_ref="main", **kw)


def _head_files(root) -> list[str]:
    return sorted(git(root, "show", "--no-renames", "--name-only", "--format=", "HEAD").split())


def _hashes(root) -> list[str]:
    return sorted(event_hash(r) for r in read_events_assembled(root).records)


def _tree_state(root) -> tuple:
    """What a failed fold must leave untouched: HEAD, the index, the work tree and the file lists."""
    return (git(root, "rev-parse", "HEAD").strip(), git(root, "status", "--porcelain").strip(), archive_names(root),
            sorted(p.name for p in (root / DROPS_DIR).iterdir()))


def _failing_hook(root, tmp_path, body: str = "#!/bin/sh\necho no >&2\nexit 1\n") -> None:
    hooks = tmp_path / "hooks"
    hooks.mkdir()
    (hooks / "pre-commit").write_text(body, encoding="utf-8", newline="\n")
    (hooks / "pre-commit").chmod(0o755)   # git ignores a hook without the executable bit (Linux CI)
    git(root, "config", "core.hooksPath", str(hooks))
