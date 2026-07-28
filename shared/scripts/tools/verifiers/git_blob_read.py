"""Read a file's content out of a commit — safely, and without the ``MAX_PATH`` trap.

Own module because ``git show <commit>:<path>`` has two defects that are easy to
reintroduce, and both were live in this repo (iterate-2026-07-28-ci-ack-per-run-home;
the second found by Stage-2 review after the first was fixed one function away):

1. **It is a Windows trap.** git first stats the whole argument as a possible
   filename, probing ``<cwd>/<sha>:<path>`` — 40 + 1 + the relpath on top of the
   repo root. Measured in this repo's own test suite, that crosses the 260-char
   ``MAX_PATH`` and git returns ``Filename too long``, indistinguishable from a real
   read failure. A gate built on it passes on a shallow checkout and fails on a deep
   one. Reading by blob OID carries no path in the argument at all.
2. **It conflates "absent" with "broken".** Both surface as a non-zero exit, so a
   caller that treats every failure as absence turns an infrastructure fault into a
   trust path. :func:`blob_oid` answers presence separately from content, so the two
   stay distinguishable.

Content is available as text (:func:`read_committed_text`) or as raw bytes
(:func:`committed_bytes_reader`). Prefer bytes for anything hashed: the text path
decodes with ``errors="ignore"`` while a worktree read may use ``errors="replace"``,
so one invalid byte yields two different digests across the seam.
"""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

from .git_helpers import _run_git

__all__ = [
    "GitReadError",
    "blob_oid",
    "committed_bytes_reader",
    "content_fingerprint",
    "read_committed_text",
    "worktree_bytes_reader",
]

#: Regular-file modes. A SYMLINK is mode 120000 with type ``blob``, so a type-only
#: check would hand its link TARGET to the caller as file content.
_REGULAR_MODES = ("100644", "100755")


class GitReadError(RuntimeError):
    """A genuine git failure while reading committed content — NOT an absence.

    Exists so a hashed input can never be silently synthesised from a broken read:
    the caller must fail closed rather than substitute a sentinel.
    """


def blob_oid(project_root: Path, commit: str, rel: str) -> tuple[str | None, str | None]:
    """``(oid, error)`` for ``rel`` at ``commit``. ``(None, None)`` == genuinely absent.

    Only genuine absence may license a fallback to the working tree; every other
    outcome is an error.
    """
    if not commit:
        return None, None
    # --literal-pathspecs, and core.quotePath=false so the returned path can be
    # compared. `git show <rev>:<path>` resolved a LITERAL path; `ls-tree -- <path>`
    # takes a PATHSPEC with wildmatch, so swapping one for the other silently made
    # `ci[1].yml` glob-match `ci1.yml` — a regression the rewrite introduced
    # (Stage-3 doubt review).
    rc, out, _ = _run_git(project_root, "-c", "core.quotePath=false",
                          "--literal-pathspecs", "ls-tree", commit, "--", rel)
    if rc != 0:
        return None, (f"cannot read {rel} at {commit[:8]} — refusing to certify "
                      "it on an unreadable tree")
    line = out.strip()
    if not line:
        return None, None
    # "<mode> SP <type> SP <oid> TAB <path>" — split on the FIRST tab, so spaces and
    # non-ASCII in the path cannot perturb the metadata fields.
    head, _, got = line.partition("\t")
    meta = head.split()
    if len(meta) < 3 or meta[1] != "blob" or meta[0] not in _REGULAR_MODES:
        return None, f"{rel} at {commit[:8]} is not a regular file"
    # Verify the entry is the one asked for. Without this, ANY entry the pathspec
    # happened to return would be hashed under `rel`'s label.
    if got.strip().strip('"') != rel:
        return None, (f"{rel} at {commit[:8]} resolved to a different entry "
                      f"({got.strip()[:60]}) — refusing to certify it")
    return meta[2], None


def read_committed_text(
    project_root: Path, commit: str, rel: str
) -> tuple[str | None, str | None]:
    """``(body, error)`` — decoded content of ``rel`` at ``commit``.

    ``(None, None)`` means genuinely absent from that tree.
    """
    oid, err = blob_oid(project_root, commit, rel)
    if err or oid is None:
        return None, err
    rc, body, _ = _run_git(project_root, "cat-file", "blob", oid)
    if rc != 0:
        return None, f"{rel} is present in {commit[:8]} but unreadable"
    return body, None


def _git_bytes(project_root: Path, *args: str) -> tuple[int, bytes]:
    """``git`` without text decoding. Never raises."""
    try:
        proc = subprocess.run(["git", "-C", str(project_root), *args],
                              capture_output=True, check=False)
        return proc.returncode, proc.stdout
    except (OSError, ValueError):
        return 1, b""


def committed_bytes_reader(project_root: Path, commit: str):
    """A content reader over a committed tree, for hashing.

    Returns ``None`` for a genuinely absent path and RAISES :class:`GitReadError`
    on any real failure. The raise is the point: the reader this replaced mapped
    every failure to ``None``, and its caller hashed ``None`` as an ``<absent>``
    sentinel — the same value recorded for a genuinely DELETED path. A read failure
    therefore did not merely red-line spuriously, it could make an acknowledgement
    recorded against a deleted file license arbitrary committed content for that
    path (Stage-2 review).
    """
    def read(rel: str) -> bytes | None:
        oid, err = blob_oid(project_root, commit, rel)
        if err:
            raise GitReadError(err)
        if oid is None:
            return None
        rc, body = _git_bytes(project_root, "cat-file", "blob", oid)
        if rc != 0:
            raise GitReadError(f"{rel} is present in {commit[:8]} but unreadable")
        return body
    return read


def worktree_bytes_reader(project_root: Path):
    """The working-tree counterpart of :func:`committed_bytes_reader`.

    Bytes, so the two sides of a write-then-verify seam hash identically. While
    this side decoded with ``errors="replace"`` and the git side with
    ``errors="ignore"``, one invalid byte produced two different digests and the
    comparison failed permanently, naming the wrong cause (Stage-2 review).
    """
    def read(rel: str) -> bytes | None:
        try:
            return (project_root / rel).read_bytes()
        except OSError:
            return None
    return read


def content_fingerprint(rel_paths, content_reader) -> str:
    """sha256 over ``<path>TAB<sha256 of content>`` lines, in the given order.

    A path the reader reports absent hashes as a sentinel, so DELETING a file is a
    distinct fingerprint rather than an absent one. The reader must RAISE on a
    failed read rather than return ``None``: ``None`` means "deleted", and
    conflating the two let a failed read license arbitrary content.

    ``bytes`` or ``str`` both accepted; identical for well-formed UTF-8. CRLF is
    normalized because text mode used to hide it — under ``core.autocrlf`` a CRLF
    worktree file and its LF blob are the same file to git, so they must hash alike.
    """
    parts = []
    for rel in rel_paths:
        body = content_reader(rel)
        if body is None:
            digest = "<absent>"
        else:
            raw = body.encode("utf-8") if isinstance(body, str) else body
            digest = hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest()
        parts.append(rel + "\t" + digest)
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()
