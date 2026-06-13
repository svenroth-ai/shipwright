"""Atomic, lock-coordinated persistence primitives for ``shipwright_run_config.json``.

Three writer families mutate the run config:

  * the orchestrator (``orchestrator_pkg.config_io.save_run_config`` /
    ``orchestrator_pkg.step_planning.update_step``),
  * the phase-task lifecycle (``phase_task_lifecycle``), and
  * ``shared/scripts/tools/append_phase_history.py``.

Audit 2026-06-10 WP2 (F11/F12) found the orchestrator family wrote *unlocked*
and *non-atomically* (``Path.write_text`` of a multi-KB document): a reader
could observe a half-written file (``JSONDecodeError`` -> silent
pipeline->standalone demotion), and a 30 s-stale in-memory copy could clobber
a concurrent locked write.

This module is the single home for the two primitives that close that gap:

  * :func:`atomic_write_json` -- ``tmp + os.replace`` so a write is
    all-or-nothing (mirrors ``append_phase_history._atomic_write_json``).
  * :func:`run_config_lock` -- an advisory lock on the canonical
    ``shipwright_run_config.json.lock`` path.

Coordination is **by lock-file path, not by shared code**: this lock,
``phase_task_lifecycle._PhaseTasksLock`` and ``append_phase_history``'s
``file_lock`` all target the same ``*.lock`` file with the same
``fcntl.flock`` / ``msvcrt.locking`` primitive, so they mutually exclude
regardless of which implementation acquired the lock.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

# The shared cross-platform advisory lock is the single lock implementation.
# ``shared/scripts/lib`` sits at parents[4] of this file in BOTH the dev repo
# (plugins/shipwright-run/scripts/lib/) and the runtime plugin cache
# (cache/shipwright/plugins/shipwright-run/scripts/lib/) -- ``shared/`` is a
# sibling of ``plugins/`` in both, mirroring the parents[5] offset
# orchestrator_pkg/constants.py relies on from one dir deeper. ``file_lock``
# is a unique top-level module name, so this import never collides with the
# plugin's own ``lib`` package.
_SHARED_LIB = Path(__file__).resolve().parents[4] / "shared" / "scripts" / "lib"
if str(_SHARED_LIB) not in sys.path:
    sys.path.insert(0, str(_SHARED_LIB))

from file_lock import LockTimeout, file_lock  # noqa: E402

RUN_CONFIG_NAME = "shipwright_run_config.json"
LOCK_NAME = RUN_CONFIG_NAME + ".lock"

# Generous default -- the read-modify-write critical section is fast (no
# subprocess runs inside it). A timeout this long only trips on a genuinely
# stuck holder, where a loud failure beats silent corruption or an unbounded
# hang.
DEFAULT_LOCK_TIMEOUT_SECONDS = 30.0

__all__ = [
    "LockTimeout",
    "RUN_CONFIG_NAME",
    "LOCK_NAME",
    "DEFAULT_LOCK_TIMEOUT_SECONDS",
    "lock_path",
    "run_config_lock",
    "atomic_write_json",
]


def lock_path(project_root: Path) -> Path:
    """Canonical advisory-lock path shared by every run-config writer."""
    return Path(project_root) / LOCK_NAME


@contextmanager
def run_config_lock(
    project_root: Path,
    *,
    timeout_seconds: float = DEFAULT_LOCK_TIMEOUT_SECONDS,
) -> Iterator[None]:
    """Hold the advisory run-config lock across a read-modify-write window.

    Raises :class:`LockTimeout` if the lock can't be acquired in time -- a
    loud failure is preferred over a silent stale-copy clobber.
    """
    with file_lock(lock_path(project_root), timeout_seconds=timeout_seconds):
        yield


def atomic_write_json(target: Path, data: dict[str, Any]) -> None:
    """Serialise ``data`` and replace ``target`` atomically (tmp + os.replace).

    The temp file is created in the destination directory so ``os.replace``
    is a same-filesystem rename (atomic on POSIX and Windows) -- a concurrent
    reader sees either the old file or the new one, never a partial write.
    """
    target = Path(target)
    content = json.dumps(data, indent=2) + "\n"
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        prefix=target.name + ".", suffix=".tmp", dir=str(target.parent),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(content)
        os.replace(tmp_path, target)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
