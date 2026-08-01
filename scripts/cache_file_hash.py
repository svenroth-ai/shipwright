#!/usr/bin/env python3
"""Content hashing for the plugin-cache drift check.

Split out of ``cache_tree_compare.py`` (iterate-2026-08-01-cache-sync-not-distributed)
when that module reached its 300-line ceiling. A deliberate split rather than a bloat
exception: the ADR template refuses an exception unless the file is honestly a deep
module that cannot be divided, and this is the opposite — a narrow interface
(``path -> digest | None``) over substantial, self-contained behaviour, with no
external caller to disturb.

Best-effort, like its caller: this backs a detective check that must never crash a
session, so filesystem errors degrade to "no hash" rather than propagating.
"""

from __future__ import annotations

import hashlib
from pathlib import Path


def file_hash(path: Path) -> str | None:
    """SHA-256 hex digest of a file, with CRLF→LF normalization for text.

    Returns ``None`` if unreadable.

    Reviewer-flagged Gemini-M1: a Windows checkout (CRLF) compared against a
    Linux-synced cache (LF) would produce false drift on every text file.

    Text is detected by CONTENT (a NUL byte in the first 8 KiB means binary),
    not suffix — a suffix rule normalized only the old allowlist's seven names,
    so it would have reported every ``.template`` and extensionless prompt file
    as drifted forever once the walk began including them. Binary hashes
    byte-exact in 64 KiB chunks.

    The normalization is LOSSY for anything misclassified as text: two blobs
    differing only in carriage-return bytes hash equal, so a wrong guess fails
    toward a false GREEN. Nothing here is binary today; if that changes, the
    sniff is what to revisit.

    Reviewer-flagged OpenAI-M7 / Gemini-S3: refuse to follow symlinks. They
    could escape the plugin root or form loops.
    """
    try:
        if path.is_symlink():
            return None
        h = hashlib.sha256()
        with path.open("rb") as fp:
            head = fp.read(8192)
            if b"\x00" in head:
                h.update(head)
                for chunk in iter(lambda: fp.read(65536), b""):
                    h.update(chunk)
                return h.hexdigest()
            raw = head + fp.read()
        h.update(raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n"))
        return h.hexdigest()
    except OSError:
        return None
