"""Shared primitives of the drop-folder housekeeping (issue 978, campaign unit S6).

Used by the fold / emergency fold / quarantine tool (``events_fold``), the full fold
(``events_fold_full``) and the integrity check (``events_integrity``): the one definition of

* what a legal file NAME in each folder looks like (key validation, path-traversal refusal),
* how raw bytes become records plus a status (the same ``split_records`` recovery every reader uses),
* the per-event hash two files are compared by (a fold is only legal when every deleted event is
  present, with an equal hash, in an added archive file),
* how a blob is read from git. ``git cat-file blob <rev>:<path>``, never ``git show``: ``show`` dies with
  "Filename too long" on the Windows CI runner for long paths.

Stdlib + sibling imports only. Never prints.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .events_log import ARCHIVE_DIR, DROPS_DIR, QUARANTINE_DIR
from .events_read import instant
from .jsonl_records import split_records

#: ``<key>--<wt8>--<nonce8>.jsonl``, key ``[A-Za-z0-9._-]{1,80}`` and not hidden (``sanitize_key`` strips leading dots).
DROP_NAME = re.compile(r"^(?P<key>[A-Za-z0-9_-][A-Za-z0-9._-]{0,79})--[0-9a-f]{8}--[0-9a-f]{8}\.jsonl$")
#: ``fold-<hash>.jsonl`` (and any other single-segment, non-hidden name a person gave an archive file).
ARCHIVE_NAME = re.compile(r"^[A-Za-z0-9_-][A-Za-z0-9._-]{0,119}\.jsonl$")
FOLDERS = (DROPS_DIR, ARCHIVE_DIR, QUARANTINE_DIR)
#: The empty, tracked file that keeps the drops folder from ever being EMPTY on any side of a merge. A fold that
#: removed every drop would otherwise look like a directory rename (drops -> archive) to the merge machinery and
#: turn an open PR's new drop into a "file location" conflict. Not a ``*.jsonl``: no reader sees it.
KEEP_NAME = ".keep"
EMPTY_BLOB = "e69de29bb2d1d6434b8b29ae775ad8c2e48c5391"


class GitError(RuntimeError):
    """A git call the caller cannot continue without failed."""


@dataclass
class Parsed:
    """What a byte string holds: ``status`` is ok / corrupt / empty (``unreadable`` is the caller's)."""

    records: list[dict]
    fragments: int
    status: str


def name_problem(folder: str, name: str) -> str | None:
    """Why ``name`` may not be a file directly under ``folder`` (``None`` = legal)."""
    if name == KEEP_NAME and folder == DROPS_DIR:
        return None
    if not name or "/" in name or "\\" in name or name in (".", "..") or "\x00" in name:
        return f"{name!r} is not a single path segment"
    pattern = ARCHIVE_NAME if folder == ARCHIVE_DIR else DROP_NAME
    return None if pattern.match(name) else f"{name!r} does not match the {folder} file-name shape"


def drop_key_of(name: str) -> str | None:
    match = DROP_NAME.match(name)
    return match.group("key") if match else None


def parse_text(text: str) -> Parsed:
    """Records of a file's text, exactly as ``read_jsonl_records`` recovers them."""
    records: list[dict] = []
    fragments = 0
    for raw in text.split("\n"):
        stripped = raw.strip()
        if stripped:
            got, remainder = split_records(stripped)
            records.extend(got)
            fragments += 1 if remainder else 0
    return Parsed(records, fragments, "corrupt" if fragments else ("ok" if records else "empty"))


def parse_bytes(data: bytes) -> Parsed:
    return parse_text(data.decode("utf-8", errors="surrogateescape"))


def event_hash(record: dict) -> str:
    """The per-event hash a fold is judged by (content AND the stamped ``run`` -- nothing is stripped)."""
    body = json.dumps(record, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)
    return hashlib.sha256(body.encode("utf-8", errors="surrogateescape")).hexdigest()


def content_hash(record: dict) -> str:
    """:func:`event_hash` without the stamped ``run`` (what the full fold dedups and the checker compares by)."""
    return event_hash({k: v for k, v in record.items() if k != "run"})


def same_bytes(a: bytes, b: bytes) -> bool:
    """Equal modulo line endings: ``core.autocrlf`` checks a committed LF file out as CRLF on Windows."""
    return a.replace(b"\r\n", b"\n") == b.replace(b"\r\n", b"\n")


def sort_key(record: dict) -> tuple:
    """Archive order = the reader's order: parsed instant, then id."""
    return (instant(record.get("ts")), str(record.get("id", "")))


def dump_line(record: dict) -> str:
    return json.dumps(record, ensure_ascii=False, separators=(",", ":"))


def git(root: Path | str, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    proc = subprocess.run(["git", "-C", str(root), *args], capture_output=True, timeout=120)
    if check and proc.returncode:
        raise GitError(f"git {' '.join(args)} failed: {proc.stderr.decode('utf-8', 'replace').strip()[-400:]}")
    return proc


def blob(root: Path | str, rev: str, path: str) -> bytes | None:
    """The bytes of ``path`` at ``rev`` (``cat-file``), ``None`` when it does not exist there."""
    proc = git(root, "cat-file", "blob", f"{rev}:{path}", check=False)
    return proc.stdout if proc.returncode == 0 else None


def tree_names(root: Path | str, rev: str, folder: str) -> set[str] | None:
    """File names directly under ``folder`` at ``rev`` (empty set: none; ``None``: the probe failed)."""
    if git(root, "rev-parse", "--verify", "-q", f"{rev}^{{commit}}", check=False).returncode:
        return None
    proc = git(root, "ls-tree", "--name-only", rev, folder + "/", check=False)
    if proc.returncode:
        return None
    return {line.rsplit("/", 1)[-1] for line in proc.stdout.decode("utf-8", "replace").splitlines() if line}
