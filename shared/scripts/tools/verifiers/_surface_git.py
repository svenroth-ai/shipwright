"""The text the surface detector scans: each changed file's changed lines AND its whole content.

Changed lines alone miss the common case of an edit inside an existing
handler's body (the ``@app.get(...)`` decorator is unchanged, so it is not in
the hunk). So for every changed code file that still exists at the verified
commit, its full content at that commit is scanned too; for a deleted file,
its removed lines are what is left. One ``git diff -U0`` and one
``git cat-file --batch`` call cover the whole branch. ``base`` is the full
merge-base sha (``measure_diff``). :func:`object_ids` is the same reader in
``--batch-check`` form, for the freshness rule (:mod:`._surface_revision`).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from ._surface_detect import is_test_or_prose, split_patch
from .git_helpers import _run_git

__all__ = ["object_ids", "surface_texts"]

_T = 30.0
_MAX_BYTES = 2_000_000  # a file larger than this is scanned by its changed lines only


def _changed_lines(project_root: Path, base: str, commit: str) -> dict[str, str] | None:
    rc, full, _ = _run_git(project_root, "rev-parse", commit, timeout=10.0)
    on_trunk = rc == 0 and full.strip() == base  # measure_diff's squash-merged-PR shape
    args = ["show", "--format=", commit] if on_trunk else ["diff", f"{base}..{commit}"]
    rc, out, _ = _run_git(project_root, "-c", "core.quotePath=false", args[0], "-U0", "--no-renames",
                          "--no-color", *args[1:], timeout=_T)
    return split_patch(out) if rc == 0 else None


def _batch(project_root: Path, specs: list[str], fmt: str, *, check_only: bool) -> bytes | None:
    request = "".join(f"{spec}\n" for spec in specs).encode("utf-8")
    mode = "--batch-check" if check_only else "--batch"
    try:
        proc = subprocess.run(["git", "-C", str(project_root), "cat-file", f"{mode}={fmt}"],
                              input=request, capture_output=True, timeout=_T, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return proc.stdout if proc.returncode == 0 else None


def _header(out: bytes, pos: int, spec: str) -> tuple[list[bytes] | None, int] | None:
    """``(fields or None when missing, next pos)`` for one response header; ``None`` if malformed.

    A missing object echoes the request back (``<rev>:<path> missing``), so it is
    matched against the request first: a path with spaces never reaches the split.
    """
    end = out.find(b"\n", pos)
    if end < 0:
        return None
    line = out[pos:end]
    if line == spec.encode("utf-8") + b" missing":
        return None, end + 1
    return line.split(b" "), end + 1


def object_ids(project_root: Path, specs: list[str]) -> dict[str, str | None] | None:
    """``{"<rev>:<path>": blob id, or None when absent there}``; ``None`` if git failed."""
    if not specs:
        return {}
    out = _batch(project_root, specs, "%(objectname)", check_only=True)
    if out is None:
        return None
    ids, pos = {}, 0
    for spec in specs:
        parsed = _header(out, pos, spec)
        if parsed is None:
            return None
        fields, pos = parsed
        ids[spec] = fields[0].decode("ascii", errors="replace") if fields else None
    return ids


def _contents(project_root: Path, commit: str, paths: list[str]) -> dict[str, str] | None:
    """``{path: text}`` at ``commit`` for the paths that exist there; ``None`` if git failed."""
    if not paths:
        return {}
    specs = [f"{commit}:{p}" for p in paths]
    out = _batch(project_root, specs, "%(objectname) %(objecttype) %(objectsize)", check_only=False)
    if out is None:
        return None
    pos, texts = 0, {}
    for path, spec in zip(paths, specs):
        parsed = _header(out, pos, spec)
        if parsed is None:
            return None
        fields, pos = parsed
        if fields is None:
            continue  # deleted at this commit: its removed lines still count
        if len(fields) != 3 or not fields[2].isdigit():
            return None
        size = int(fields[2])
        if fields[1] == b"blob" and size <= _MAX_BYTES:
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
