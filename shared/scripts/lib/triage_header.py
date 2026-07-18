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


def has_header(path: Path) -> bool:
    """True iff line 1 of ``path`` is a triage schema header."""
    if not path.exists():
        return False
    try:
        first_raw = path.read_text(encoding="utf-8").split("\n", 1)[0].strip()
    except OSError:
        return False
    if not first_raw:
        return False
    try:
        first = json.loads(first_raw)
    except json.JSONDecodeError:
        return False
    return first.get("schema") == "triage" and "v" in first


def ensure_header(path: Path, *, schema_version: int, now: str) -> None:
    """Create ``path`` with the schema header if it lacks one.

    Idempotent — never overwrites an existing header. Caller must hold the file lock.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    if has_header(path):
        return
    header = {"v": schema_version, "schema": "triage", "created": now}
    line = json.dumps(header, ensure_ascii=False, separators=(",", ":")) + "\n"
    # File exists but has no header (corrupted bootstrap) → prepend; else create.
    if path.exists() and path.stat().st_size > 0:
        existing = path.read_text(encoding="utf-8")
        path.write_text(line + existing, encoding="utf-8")
    else:
        path.write_text(line, encoding="utf-8")
