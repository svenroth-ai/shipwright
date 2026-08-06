"""Durable writer for the operator-review quarantine buffer.

Split from :mod:`lib.sweep_quarantine` (iterate-2026-08-06-triage-validate-deadends)
so the disposition RULES and the log WRITER each stay under the 300-LOC guideline —
the same reason ``sweep_quarantine`` was itself split out of ``lib.sweep_outbox``.
``sweep_quarantine`` re-exports every name here, so ``triage_repair``,
``sweep_outbox`` and ``sweep_result`` keep resolving unchanged.

The write reuses the same ``durable_atomic_write`` as the rest of the sweep, and the
caller invokes it under the canonical triage ``_FileLock`` — the same critical
section that decides, materializes and commits.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from lib.atomic_write import durable_atomic_write

#: Operator-review buffer for quarantined un-deliverable lines (gitignored, main-tree).
QUARANTINE_LOG = ".shipwright/triage.outbox.quarantine.jsonl"


def quarantine_path(main_root: Path | str) -> Path:
    return Path(main_root) / QUARANTINE_LOG


def append_quarantine(
    path: Path,
    lines: list[str],
    *,
    reason: str,
    now: str | None = None,
) -> None:
    """Durably append ``lines`` (each wrapped with ``quarantined_at`` / ``reason`` /
    ``original``) to the quarantine log. ``now`` overridable for deterministic tests."""
    ts = now or datetime.now(timezone.utc).isoformat()
    # Read BYTES. The previous text read needed an explicit ``newline=""`` open (the
    # log's existing EOLs must survive the round-trip, and ``Path.read_text(newline=)``
    # is 3.13+ only, which once took setup_iterate_worktree.py down AFTER the worktree
    # was already created). Bytes answer that and one more: this runs on the same
    # interrupted-write path as the rest of the sweep, and a strict decode of a store
    # truncated mid multi-byte sequence would raise straight out of step 5. Nothing is
    # decoded here, so nothing can fail to decode or be re-encoded differently.
    existing = path.read_bytes() if path.exists() else b""
    records = [
        json.dumps({"quarantined_at": ts, "reason": reason, "original": ln}, ensure_ascii=False)
        for ln in lines
    ]
    out = existing
    if out and not out.endswith(b"\n"):
        out += b"\n"
    # ``surrogateescape`` on the way out too: a quarantined line reached us through a
    # surrogate-escaped read, so a strict encode here would crash on exactly the
    # corrupt line the quarantine exists to preserve. This restores its original bytes.
    out += ("\n".join(records) + "\n").encode("utf-8", errors="surrogateescape")
    path.parent.mkdir(parents=True, exist_ok=True)
    durable_atomic_write(path, out)
