"""A git tree id for the working tree exactly as it is now, without touching the real index.

The staged test evidence names the commit it was staged at, but F0 runs on an
uncommitted tree: the commit is only the base, and the tested content is that
base plus every edit not committed yet. A tree id fingerprints that content.
:func:`working_tree_id` writes one the way a commit would see it: the real
index is copied to a temporary index (so its stat cache keeps this fast), every
tracked and untracked-but-not-ignored change is added there with the same
filters a commit applies (line endings), and ``git write-tree`` returns the id.
The real index, the working tree and every ref stay untouched; the only side
effect is loose objects in the object store, which ``git gc`` prunes later.

The F11 surface check compares this tree with the verified commit, per path,
for the paths the branch itself changed. A difference means the code that was
committed is not the code that was tested.

Standard library only. ``None`` whenever git cannot answer: the consumer then
reads the evidence as unfingerprinted, which is stale, never as fresh.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

__all__ = ["working_tree_id"]

_TIMEOUT = 120.0


def _git(root: Path, *args: str, env: dict | None = None) -> str | None:
    try:
        proc = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=_TIMEOUT, env=env, check=False)
        return proc.stdout.strip() if proc.returncode == 0 else None
    except Exception:  # noqa: BLE001 - a fingerprint that cannot be taken is absent, never a crashed stage
        return None


def working_tree_id(project_root: Path | str) -> str | None:
    """The tree id of the working tree (tracked + untracked, ignore rules applied), or ``None``."""
    root = Path(project_root)
    index = _git(root, "rev-parse", "--path-format=absolute", "--git-path", "index")
    if not index:
        return None
    try:
        with tempfile.TemporaryDirectory(prefix="sw-tree-") as tmp:
            temp_index = Path(tmp) / "index"
            if Path(index).is_file():
                shutil.copyfile(index, temp_index)
            env = {**os.environ, "GIT_INDEX_FILE": str(temp_index)}
            if _git(root, "add", "-A", env=env) is None:
                return None
            tree = _git(root, "write-tree", env=env)
    except OSError:  # the temp copy could not be made or removed: no fingerprint
        return None
    return tree or None
