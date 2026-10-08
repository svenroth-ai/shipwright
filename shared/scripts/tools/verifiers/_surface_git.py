"""The text the surface detector scans: each changed file's changed lines AND its whole content.

Changed lines alone miss the common case of an edit inside an existing
handler's body (the ``@app.get(...)`` decorator is unchanged, so it is not in
the hunk). So for every changed code file that still exists at the verified
commit, its full content at that commit is scanned too; for a deleted file,
its removed lines are what is left. One ``git diff -U0`` and one
``git cat-file --batch`` call cover the whole branch.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from ._surface_detect import is_test_or_prose, split_patch
from .git_helpers import _run_git

__all__ = ["surface_texts"]

_T = 30.0
_MAX_BYTES = 2_000_000  # a file larger than this is scanned by its changed lines only


def _changed_lines(project_root: Path, base: str, commit: str) -> dict[str, str] | None:
    rc, full, _ = _run_git(project_root, "rev-parse", commit, timeout=10.0)
    on_trunk = rc == 0 and full.strip().startswith(base)  # measure_diff's squash-merged-PR shape
    args = ["show", "--format=", commit] if on_trunk else ["diff", f"{base}..{commit}"]
    rc, out, _ = _run_git(project_root, "-c", "core.quotePath=false", args[0], "-U0", "--no-renames",
                          "--no-color", *args[1:], timeout=_T)
    return split_patch(out) if rc == 0 else None


def _contents(project_root: Path, commit: str, paths: list[str]) -> dict[str, str] | None:
    """``{path: text}`` at ``commit`` for the paths that exist there; ``None`` if git failed."""
    if not paths:
        return {}
    request = "".join(f"{commit}:{p}\n" for p in paths).encode("utf-8")
    try:
        proc = subprocess.run(["git", "-C", str(project_root), "cat-file", "--batch"], input=request,
                              capture_output=True, timeout=_T, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    out, pos, texts = proc.stdout, 0, {}
    for path in paths:
        end = out.find(b"\n", pos)
        if end < 0:
            return None
        header = out[pos:end].split()
        pos = end + 1
        if len(header) == 2 and header[1] == b"missing":
            continue  # deleted at this commit: its removed lines still count
        if len(header) != 3:
            return None
        size = int(header[2])
        if header[1] == b"blob" and size <= _MAX_BYTES:
            texts[path] = out[pos:pos + size].decode("utf-8", errors="replace")
        pos += size + 1
    return texts


def surface_texts(project_root: Path, base: str, commit: str, paths: list[str]) -> dict[str, str] | None:
    """Changed lines + full content per changed, non-test path; ``None`` when git could not answer."""
    changed = _changed_lines(project_root, base, commit)
    if changed is None:
        return None
    scan = [p for p in paths if not is_test_or_prose(p)]
    contents = _contents(project_root, commit, scan)
    if contents is None:
        return None
    return {p: changed.get(p, "") + "\n" + contents.get(p, "") for p in set(changed) | set(contents)}
