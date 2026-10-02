#!/usr/bin/env python3
"""F0 resume - bring a saved coverage data file back, minus what the fix made stale.

A saved `.coverage.<label>` records line NUMBERS of the files as they were. Where the fix
edited a file those numbers describe a file that no longer exists, and diff-cover would
grade the NEW lines against them - a false green is the failure to avoid here. So every
measured file whose content differs from the saved tree (or whose path cannot be mapped
onto a hashed file at all) has its rows deleted before the restored data is used; the
red tests' re-run then appends fresh data. Unknown = stale: a path form this module does
not understand costs coverage, never certifies it.

If the purged data cannot satisfy the diff-coverage gate the runner falls back to a full
run (`run_test_suite._run_locked`) and records why - the operator's decision, not a
refusal to resume.

Direct sqlite, not the `coverage` API: the runner's own interpreter does not carry
coverage.py. Tables used (`file`, `line_bits`, `arc`) are the stable coverage 5+ schema,
the same one `test_f0_failed_only_real_pytest` already reads.
"""

from __future__ import annotations

import os
import re
import shutil
import sqlite3
from pathlib import Path

_DRIVE = re.compile(r"^[A-Za-z]:/")


def _candidates(path: str, unit, root: Path) -> list[str]:
    """Where in the tree a measured path can live. Plugin units measure relative to
    their own cwd, so a bare `scripts/x.py` must NOT be matched against the repo-root
    `scripts/` directory."""
    posix = path.replace("\\", "/")
    if os.path.isabs(posix) or _DRIVE.match(posix):
        try:
            return [Path(posix).resolve().relative_to(root).as_posix()]
        except (ValueError, OSError):
            return []
    return [posix] if unit.cwd in ("", ".") else [f"{unit.cwd}/{posix}"]


def is_stale(path: str, unit, root: Path, prior: dict[str, str], now: dict[str, str]) -> bool:
    for candidate in _candidates(path, unit, root):
        digest = now.get(candidate)
        if digest is not None:
            return digest == "-" or digest != prior.get(candidate)
    return True


def restore_coverage(src: Path, dest: Path, unit, root: Path,
                     prior: dict[str, str], now: dict[str, str]) -> bool:
    """Copy `src` to `dest` and drop the stale files' rows; False = unusable, run in full."""
    try:
        shutil.copyfile(src, dest)
        db = sqlite3.connect(dest)
        try:
            files = db.execute("select id, path from file").fetchall()
            stale = [(fid,) for fid, path in files if is_stale(path, unit, root, prior, now)]
            db.executemany("delete from line_bits where file_id = ?", stale)
            if db.execute("select 1 from sqlite_master where name = 'arc'").fetchone():
                db.executemany("delete from arc where file_id = ?", stale)
            db.commit()
            left = db.execute("select distinct f.path from line_bits l "
                              "join file f on f.id = l.file_id").fetchall()
        finally:
            db.close()
    except (OSError, sqlite3.Error):
        return False
    return not any(is_stale(path, unit, root, prior, now) for (path,) in left)
