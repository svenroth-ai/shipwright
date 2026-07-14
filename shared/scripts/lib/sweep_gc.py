"""GC delivered-membership logic for the D2 outbox sweep (serialization-drift-immune).

Split from :mod:`lib.sweep_outbox` (D2 review cascade — FIX B, doubt-1) so the
sweep orchestrator stays under the 300-LOC guideline and the GC membership rule
is unit-testable in isolation. :func:`delivered_membership` reads ``origin``'s blob
(the one git call here); the membership RULE below it stays pure.

The GC drops an outbox line ONLY once it is reachable from ``origin/<default>``.
Historically that was a raw stripped-text comparison. FIX B hardens it: an
``append`` line is delivered by its semantic ``id`` (immune to a future producer
re-serializing the SAME logical append with a different key order / whitespace),
while status / unparseable lines — which carry no stable key — keep the original
text-membership match. A non-delivered id always survives (fail-safe); a missing
``origin`` ref yields empty sets so nothing is GC'd.
"""

from __future__ import annotations

import json
from pathlib import Path

from lib.churn_merge import TRIAGE_LOG
from lib.sweep_text import normalized_set
from lib.worktree_isolation import run_git


def delivered_membership(main_root: Path, default_branch: str) -> tuple[set[str], set[str]]:
    """Read ``origin/<default>:<triage>`` and parse it into the ``(append_ids, text)``
    GC anchors. An outbox line is safe to drop only once reachable from ``origin``.
    ``check=False`` so a missing ref / file yields ``(set(), set())`` — nothing GC'd
    (fail-safe; a non-delivered id always survives)."""
    proc = run_git(["show", f"origin/{default_branch}:{TRIAGE_LOG}"], cwd=main_root, check=False)
    if proc.returncode != 0:
        return set(), set()
    return parse_delivered(normalized_set(proc.stdout))


def parse_delivered(normalized_lines: set[str]) -> tuple[set[str], set[str]]:
    """Split origin's stripped/CRLF-absorbed lines into ``(append_ids, text)``.

    * ``append_ids`` — the ``id`` of every ``event=="append"`` entry (an outbox
      append is delivered iff its id is in here, regardless of re-serialization);
    * ``text`` — the stripped raw line of every NON-append line (status events,
      and any unparseable line) — these have no stable id, so they keep the
      original text-membership match.
    """
    append_ids: set[str] = set()
    text: set[str] = set()
    for stripped in normalized_lines:
        try:
            obj = json.loads(stripped)
        except json.JSONDecodeError:
            text.add(stripped)  # unparseable → text path (keep prior behavior)
            continue
        iid = obj.get("id") if isinstance(obj, dict) else None
        if isinstance(obj, dict) and obj.get("event") == "append" and isinstance(iid, str):
            append_ids.add(iid)
        else:
            text.add(stripped)  # status / non-append → text-membership
    return append_ids, text


def is_delivered(stripped_line: str, delivered_append_ids: set[str], delivered_text: set[str]) -> bool:
    """True iff ``stripped_line`` (an outbox line, already stripped/CRLF-absorbed)
    is present in origin, so the GC may drop it.

    Delivered iff it parses as an ``append`` whose ``id`` is in
    ``delivered_append_ids`` (serialization-drift-immune), OR its stripped text is
    in ``delivered_text`` (status / unparseable lines). Anything else SURVIVES.
    """
    try:
        obj = json.loads(stripped_line)
    except json.JSONDecodeError:
        return stripped_line in delivered_text
    iid = obj.get("id") if isinstance(obj, dict) else None
    if isinstance(obj, dict) and obj.get("event") == "append" and isinstance(iid, str):
        return iid in delivered_append_ids
    return stripped_line in delivered_text
