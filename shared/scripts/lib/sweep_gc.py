"""GC delivered-membership logic for the D2 outbox sweep (serialization-drift-immune).

Split from :mod:`lib.sweep_outbox` (D2 review cascade — FIX B, doubt-1) so the
sweep orchestrator stays under the 300-LOC guideline and the GC membership rule
is unit-testable in isolation.

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
