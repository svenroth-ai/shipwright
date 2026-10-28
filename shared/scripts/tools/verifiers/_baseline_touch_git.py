"""Git-facing half of the baseline touched-set library (BP, unit BL0).

One ``GitRev`` is one comparison: the merge base against the head (in the replay,
a squash commit's first parent against the squash commit). Every read has three
answers - text, ``""`` (absent at that side), ``None`` (git could not answer) - because
collapsing "unreadable" into "absent" would turn a broken repository into "nothing
changed", the failure the baseline gate exists to prevent.
"""

from __future__ import annotations

import re
import subprocess
from functools import lru_cache
from pathlib import Path

__all__ = ["GitRev", "is_test_path"]

_HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
_TEST_DIRS = frozenset({"tests", "test", "__tests__", "integration-tests"})


def is_test_path(path: str) -> bool:
    """A Python file under a real test root (``tests/``, ``integration-tests/``)."""
    parts = path.replace("\\", "/").split("/")
    return path.endswith(".py") and bool(_TEST_DIRS & set(parts[:-1])) and "fixtures" not in parts


class GitRev:
    def __init__(self, root: str | Path, base: str, head: str) -> None:
        self.root, self.head = str(root), head
        self._cache: dict[tuple[str, str], str | None] = {}
        # Three-dot semantics (brief section 2): compare against the MERGE BASE of base and head,
        # so a base that moved on (origin/main) never leaks its own changes into the diff.
        rc, out = self.git("merge-base", base, head)
        if rc != 0 or not out.strip():
            raise RuntimeError(f"no merge base between {base} and {head} in {self.root}")
        self.base = out.strip()

    def git(self, *args: str) -> tuple[int, str]:
        proc = subprocess.run(["git", "-C", self.root, "-c", "core.quotePath=false", *args], capture_output=True, check=False)
        return proc.returncode, proc.stdout.decode("utf-8", errors="replace")

    def sha(self, side: str) -> str:
        return self.base if side == "base" else self.head

    def read(self, path: str, side: str) -> str | None:
        key = (path, side)
        if key not in self._cache:
            sha = self.sha(side)
            rc, out = self.git("show", f"{sha}:{path}")
            if rc == 0:
                self._cache[key] = out
            else:
                rc_exists, _ = self.git("cat-file", "-e", f"{sha}:{path}")
                rc_commit, _ = self.git("rev-parse", "--verify", f"{sha}^{{commit}}")
                self._cache[key] = "" if rc_exists != 0 and rc_commit == 0 else None
        return self._cache[key]

    def changed(self) -> list[tuple[str, str, str]]:
        """``(status, old path, new path)`` per changed file; renames are detected, so a
        moved test file reads as one rename and not as a deletion plus an addition."""
        rc, out = self.git("diff", "--no-ext-diff", "--no-color", "--name-status", "-M", self.base, self.head)
        if rc != 0:
            raise RuntimeError(f"git diff {self.base}..{self.head} failed in {self.root}")
        rows = []
        for line in out.splitlines():
            cols = line.split("\t")
            status = cols[0][:1]
            old, new = (cols[1], cols[-1]) if len(cols) > 2 else (cols[1], cols[1])
            rows.append((status, old, new))
        return rows

    @lru_cache(maxsize=None)  # noqa: B019 - one GitRev lives for one comparison
    def listing(self, side: str) -> tuple[str, ...]:
        rc, out = self.git("ls-tree", "-r", "--name-only", self.sha(side))
        if rc != 0:
            raise RuntimeError(f"git ls-tree {self.sha(side)} failed in {self.root}")
        return tuple(out.splitlines())

    def line_changes(self, old: str, new: str) -> tuple[list[int], list[int]]:
        """``(base lines removed or replaced, head lines added or replaced)`` for one file."""
        args = ["diff", "--no-ext-diff", "--no-color", "-U0", "-M", self.base, self.head, "--"]
        rc, out = self.git(*args, old, *([new] if new != old else []))
        removed: list[int] = []
        added: list[int] = []
        if rc != 0:  # never "no lines changed": an unreadable diff must fail closed
            raise RuntimeError(f"git diff -U0 failed for {old} in {self.root}")
        for line in out.splitlines():
            m = _HUNK.match(line)
            if m:
                o_start, o_len = int(m[1]), int(m[2] if m[2] is not None else 1)
                n_start, n_len = int(m[3]), int(m[4] if m[4] is not None else 1)
                removed += range(o_start, o_start + o_len)
                added += range(n_start, n_start + n_len)
        return removed, added
