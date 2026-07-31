"""Schema-header bootstrap for the tracked triage store.

A NEUTRAL LEAF (same rationale as :mod:`lib.sweep_text` / :mod:`lib.jsonl_records`):
header detection and creation are a self-contained concern that only
``triage._append_line`` and the scaffolder need, and parking them in ``triage.py``
kept that module — already carrying an ADR-100 bloat exception — growing.

``triage.py`` re-exports both under their historical private names, so
``from triage import _ensure_header`` keeps resolving for existing consumers.
"""

from __future__ import annotations

import json
from pathlib import Path

__all__ = ["ensure_header", "has_header"]


def _durable_atomic_write(path: Path, data: bytes) -> None:
    """``lib.atomic_write.durable_atomic_write``, resolved WITHOUT an intra-package import.

    ``triage.py`` reaches this module through ``shared_lib_loader.load_shared_lib``,
    whose docstring is explicit: the by-file-location fallback is *"only safe for lib
    modules with no intra-package imports"*, because a ``from lib.sibling import …``
    still resolves against whichever shadowing ``lib`` package won — the very ADR-045
    collision that loader exists to survive. So this module stays a stdlib-only leaf
    (like its siblings ``jsonl_records`` and ``file_lock``) and goes back through the
    loader for the one helper it needs. ``atomic_write`` is itself stdlib-only, so it
    satisfies the same constraint.
    """
    from shared_lib_loader import load_shared_lib  # noqa: PLC0415

    load_shared_lib("atomic_write").durable_atomic_write(path, data)


def has_header(path: Path) -> bool:
    """True iff line 1 of ``path`` is a triage schema header.

    Reads ONE line, as BYTES, and decodes it with ``surrogateescape``. Both halves
    are load-bearing:

    * A strict decode raised ``UnicodeDecodeError`` on a store truncated mid
      multi-byte sequence — and that is a ``ValueError``, not an ``OSError``, so it
      escaped the handler below, out through ``ensure_header`` and
      ``triage._append_line``, which has none. Measured: it fired on a store whose
      BAD byte was on line 44, i.e. nowhere near the header this function inspects.
    * ``read_text()`` pulled the WHOLE file in to look at line 1, on an append-only
      log that only grows, on every tracked append.
    """
    if not path.exists():
        return False
    try:
        with path.open("rb") as fh:
            first_raw = fh.readline().decode("utf-8", errors="surrogateescape").strip()
    except (OSError, ValueError):
        return False
    if not first_raw:
        return False
    try:
        first = json.loads(first_raw)
    except json.JSONDecodeError:
        return False
    # isinstance: a bare scalar (`42`, `"x"`, `null`) is VALID json, and `.get` on it
    # raises AttributeError past the JSONDecodeError handler above. jsonl_records
    # treats exactly that shape as a recognised corruption fragment, so it occurs.
    return isinstance(first, dict) and first.get("schema") == "triage" and "v" in first


def ensure_header(path: Path, *, schema_version: int, now: str) -> None:
    """Create ``path`` with the schema header if it lacks one.

    Idempotent — never overwrites an existing header. Caller must hold the file lock.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    if has_header(path):
        return
    header = {"v": schema_version, "schema": "triage", "created": now}
    line = json.dumps(header, ensure_ascii=False, separators=(",", ":"))
    # File exists but has no header (corrupted bootstrap) → prepend; else create.
    #
    # Durable + atomic + in BYTES, not read_text/write_text. Three defects, all on a
    # RECOVERY path operating on the git-tracked SSoT:
    #
    # * ``write_text`` truncates and then writes, so an interruption left the log
    #   empty or half-written. This was the ONLY whole-file rewrite in the store
    #   that bypassed the shared durable primitive.
    # * ``read_text``/``write_text`` translate newlines on BOTH sides, so the file
    #   came back re-encoded in the platform's line ending — a whole-file diff on a
    #   ``merge=union`` artifact, which is where a whole-file diff costs the most.
    # * a strict decode would raise on a store truncated mid multi-byte sequence,
    #   which is precisely the interrupted-write state this recovery path exists for.
    #
    # Reading BYTES answers all three at once and is strictly stronger than a
    # verbatim text round-trip: nothing is decoded, so nothing can be re-encoded
    # differently. Prepending now prepends — the existing bytes are carried across
    # untouched and only the header line is added.
    #
    # TWO different EOL rules, because the two cases have different neighbours:
    # PREPEND inherits the existing file's, CREATE matches the appender's (LF).
    #
    # On a pre-existing CRLF store those disagree, and that is unavoidable rather than
    # sloppy: ``_append_line`` is unconditionally LF now, so such a store becomes mixed
    # at its next append no matter what line 1 does. Inheriting keeps this function
    # from being the one that rewrites 1145 existing lines; ``reconcile_triage``
    # re-normalises the whole log on its next fold either way.
    existing = path.read_bytes() if path.exists() else b""
    if existing:
        eol = b"\r\n" if b"\r\n" in existing else b"\n"
    else:
        # CREATE: nothing to inherit, so match the writer of the NEXT line.
        # ``triage._append_line`` now opens the tracked store with ``newline=""`` — LF
        # on every platform, like the outbox — so a fresh store is uniform instead of
        # LF line 1 followed by CRLF records on Windows.
        eol = b"\n"
    _durable_atomic_write(path, line.encode("utf-8") + eol + existing)
