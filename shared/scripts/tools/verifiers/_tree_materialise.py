"""Materialise a commit's tracked tree into a directory for the traceability gates (R3).

Built from ``git ls-tree`` + ``git cat-file`` rather than ``git archive``, which drops every path a
``.gitattributes`` ``export-ignore`` names. Blobs are written raw: no eol/autocrlf, ident or
filter (LFS smudge) conversion, so base and head are scanned the same way on every OS. A symlink
whose relative target is a regular file in the same tree is written as a copy of that file (what the
old tar extraction produced); a link that leaves the tree, a directory link and a submodule are
left out. Stdlib only."""

from __future__ import annotations

import posixpath
import subprocess
from pathlib import Path

_REGULAR_MODES = frozenset({b"100644", b"100755"})
_LINK_MODE = b"120000"


def _write_blobs(dest: Path, entries: list[tuple[bytes, bytes]], blobs: dict[bytes, bytes]) -> None:
    """Write ``(sha, path)`` entries under ``dest``, skipping any path that resolves outside it.
    Path CONTAINMENT, never a string prefix (``/tmp/foo-evil`` starts with ``/tmp/foo``): the tree is
    our own, but a traversal member is refused regardless."""
    dest_r = dest.resolve()
    for sha, rel in entries:
        target = (dest / rel.decode("utf-8", "surrogateescape")).resolve()
        if dest_r not in target.parents:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(blobs[sha])


def _read_blobs(root: str, wanted: list[bytes]) -> dict[bytes, bytes] | None:
    """Contents of ``wanted`` blob ids through one ``cat-file --batch``; ``None`` on any irregularity."""
    if not wanted:
        return {}
    cat = subprocess.run(["git", "-C", root, "cat-file", "--batch"], input=b"\n".join(wanted) + b"\n",
                         capture_output=True, timeout=180)
    if cat.returncode != 0:
        return None
    blobs: dict[bytes, bytes] = {}
    out, pos = cat.stdout, 0
    for want in wanted:
        end = out.find(b"\n", pos)
        header = out[pos:end].split(b" ") if end != -1 else []
        if len(header) != 3 or header[0] != want or header[1] != b"blob":
            return None
        size = int(header[2])
        if end + 1 + size > len(out):  # truncated final blob
            return None
        blobs[want] = out[end + 1:end + 1 + size]
        pos = end + 1 + size + 1
    return blobs


def _tree_blobs(project_root: Path, sha: str) -> tuple[list[tuple[bytes, bytes]], dict[bytes, bytes]] | None:
    """Files of the tree at ``sha`` (``ls-tree``) and their contents; in-tree file symlinks resolved."""
    root = str(project_root)
    try:
        ls = subprocess.run(["git", "-C", root, "ls-tree", "-r", "-z", "--full-tree", sha],
                            capture_output=True, timeout=180)
        if ls.returncode != 0:
            return None
        files: dict[bytes, bytes] = {}  # path -> blob id
        links: list[tuple[bytes, bytes]] = []  # (blob id holding the target, path)
        for record in ls.stdout.split(b"\0"):
            meta, _, rel = record.partition(b"\t")
            parts = meta.split(b" ")
            if len(parts) != 3 or parts[1] != b"blob":  # submodules (commit) and trees are skipped
                continue
            if parts[0] in _REGULAR_MODES:
                files[rel] = parts[2]
            elif parts[0] == _LINK_MODE:
                links.append((parts[2], rel))
        blobs = _read_blobs(root, list(dict.fromkeys([*files.values(), *(b for b, _ in links)])))
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    if blobs is None:
        return None
    entries = [(b, p) for p, b in files.items()]
    for blob_id, rel in links:
        target = posixpath.normpath(posixpath.join(posixpath.dirname(rel), blobs[blob_id]))
        if target in files:  # a target leaving the tree normalises to `..`/absolute and never matches
            entries.append((files[target], rel))
    return entries, blobs


def _archive_tree(project_root: Path, sha: str, dest: Path) -> bool:
    """Materialise the tracked tree at ``sha`` into ``dest`` (tracked files only - ``.worktrees`` /
    gitignored churn are excluded). Returns False on any git failure.

    Built from ``ls-tree`` + ``cat-file`` rather than ``git archive``, which drops every path a
    ``.gitattributes`` ``export-ignore`` names: a change could then hide a new test by ignoring its
    folder, and the head tree would shrink relative to the commit it vets."""
    got = _tree_blobs(project_root, sha)
    if got is None:
        return False
    try:
        _write_blobs(dest, got[0], got[1])
    except OSError:
        return False
    return True
