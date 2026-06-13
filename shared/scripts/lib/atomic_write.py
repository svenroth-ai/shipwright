"""Durable, atomic single-file writes — the shared ``tmp + fsync + os.replace``
primitive every ``shipwright_*`` config / state / log writer routes through.

``os.replace`` alone prevents a **torn read** (a concurrent reader sees either
the whole old file or the whole new one, never a partial write) but NOT a
**lost write**: a crash or power-loss after ``os.replace`` returns — but before
the OS flushes the page cache — can leave the file empty or stale. Closing that
gap requires two extra steps the bare ``tmp + replace`` pattern omits:

  * ``fsync`` the temp file *before* the rename, so its bytes are on stable
    storage when the rename publishes it, and
  * a best-effort ``fsync`` of the *containing directory* *after* the rename,
    so the directory entry (the rename itself) survives a crash too.

This is orthogonal to ``file_lock`` / ``run_config_store`` — those serialize
*concurrent* writers; this makes a *single* writer's bytes durable. The two
compose.

``atomic_write`` is a unique top-level module name (like ``file_lock``), so it
imports cleanly both as ``lib.atomic_write`` (when ``shared/scripts`` is on the
path) and as ``atomic_write`` (when ``shared/scripts/lib`` is, e.g. from a
plugin doing the ``parents[4]`` shared-lib insert).
"""
from __future__ import annotations

import contextlib
import os
import tempfile
from pathlib import Path

__all__ = ["durable_atomic_write"]


def durable_atomic_write(path: Path | str, data: str | bytes) -> None:
    """Write ``data`` to ``path`` durably and atomically.

    ``str`` is encoded UTF-8 and written verbatim — no newline translation, no
    invented trailing newline — so callers keep full control of line endings
    and serialization (each keeps its own ``json.dumps(...)`` line).

    Sequence: write to a same-directory temp file → ``fsync`` it → ``os.replace``
    onto ``path`` (atomic on POSIX and Windows) → best-effort directory fsync.
    On any failure the temp file is removed and the original error re-raised, so
    ``path`` is never left pointing at a half-written temp.
    """
    path = Path(path)
    raw = data.encode("utf-8") if isinstance(data, str) else data
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(raw)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise
    _fsync_parent_dir(path.parent)


def _fsync_parent_dir(directory: Path) -> None:
    """Best-effort ``fsync`` of ``directory`` so the rename survives a crash.

    POSIX-only: Windows cannot open a directory for ``fsync`` (and NTFS makes
    the replace durable on its own). Any error is swallowed — directory fsync is
    a durability nicety, not a correctness requirement, and some filesystems
    legitimately reject it.
    """
    if os.name == "nt":
        return
    dir_fd = None
    try:
        dir_fd = os.open(str(directory), os.O_RDONLY)
        os.fsync(dir_fd)
    except OSError:
        pass
    finally:
        if dir_fd is not None:
            with contextlib.suppress(OSError):
                os.close(dir_fd)
