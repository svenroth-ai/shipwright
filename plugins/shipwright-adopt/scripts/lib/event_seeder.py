"""Seed shipwright_events.jsonl with the adopted event + optional backfill.

One `adopted` event is mandatory. Optional backfill: N `work_completed`
events derived from major_refactor_commits, tagged with
`source="adopted-backfill"` and `confidence="low"` so they don't
contaminate serious RTM metrics.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ends_without_newline(path: Path) -> bool:
    """True iff ``path`` exists, is non-empty, and its final byte is not ``\\n``.

    DELIBERATE DUPLICATION of ``shared/scripts/lib/jsonl_records.ends_without_newline``,
    which is the SSOT for this contract. This plugin CANNOT import it: it ships its
    own ``scripts/lib/`` package, so ``from lib import jsonl_records`` resolves to
    THIS package and raises ImportError — the ``sys.modules['lib']`` collision that
    ADR-045 describes. Verified empirically, not assumed.

    Keep in lock step with the shared leaf; the contract is small and stable
    (missing / zero-byte -> False, since seeking -1 from an empty file raises).
    """
    try:
        if path.stat().st_size == 0:
            return False
        with path.open("rb") as fh:
            fh.seek(-1, 2)  # 2 == os.SEEK_END
            return fh.read(1) != b"\n"
    except (OSError, ValueError):
        return False


def _append_jsonl(path: Path, event: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Termination guard (iterate-2026-07-18-events-jsonl-record-boundary): this
    # writer takes NO lock and appends repeatedly (the adopted event, then N
    # backfill events), so it must not assume the previous line was terminated —
    # otherwise two records land on one physical line and a reader without
    # record-boundary recovery discards BOTH.
    needs_separator = _ends_without_newline(path)
    with path.open("a", encoding="utf-8") as f:
        if needs_separator:
            f.write("\n")
        f.write(json.dumps(event, ensure_ascii=False) + "\n")


def seed_adopted_event(
    events_path: Path,
    *,
    profile: str,
    scope: str,
    features_inferred: int,
    nested_excluded: list[str],
    plugin_version: str,
    commit_sha: str | None,
) -> dict[str, Any]:
    event = {
        "type": "adopted",
        "timestamp": _utc_now_iso(),
        "profile": profile,
        "scope": scope,
        "features_inferred": features_inferred,
        "nested_excluded": nested_excluded,
        "plugin_version": plugin_version,
        "commit_at_adoption": commit_sha or "HEAD",
    }
    _append_jsonl(events_path, event)
    return event


def seed_backfill_events(
    events_path: Path,
    refactor_commits: list[dict[str, Any]],
    *,
    max_count: int = 10,
) -> int:
    """Write backfill `work_completed` events from major refactor commits.

    Returns the number of events written.
    """
    written = 0
    for commit in refactor_commits[:max_count]:
        event = {
            "type": "work_completed",
            "timestamp": commit.get("date") or _utc_now_iso(),
            "source": "adopted-backfill",
            "confidence": "low",
            "commit_sha": commit.get("sha", ""),
            "subject": commit.get("subject", ""),
            "author": commit.get("author", ""),
            "files_changed": commit.get("files_changed", 0),
        }
        _append_jsonl(events_path, event)
        written += 1
    return written
