"""Shared event-label + anchor helpers for the compliance markdown tables.

Both the Test Evidence report and the Requirements Traceability Matrix render
``work_completed`` events into markdown tables. These helpers give them ONE
definition of:

* :func:`event_display_name` — the human-facing label for an event: the
  authored plain-language ``summary`` when present, else a lightly-cleaned
  technical ``description``, else the event id. Keeps the Event column readable
  for a non-expert without rewriting the audit-faithful ``description`` field.
* :func:`event_anchor` — the same-document (or cross-file) fragment that links
  an ``iterate`` / ``(iter)`` token to that event's full row in the
  Verification Timeline. Validates the canonical ``evt-<hex>`` id shape before
  interpolating so a malformed wire id can never emit a broken href (mirrors
  :data:`_rtm_reconciliation_render._EVENT_ID_RE`).

Leaf module: stdlib-only at import, imports nothing from the compliance ``lib``
package, so both generators can import it without forming a cycle.
"""

from __future__ import annotations

import re

# Canonical work-event id shape (see ``record_event.generate_event_id``). Kept
# as an independent literal — not imported from ``_rtm_reconciliation_render`` —
# so this leaf module stays import-free; a meta-test pins the two patterns equal
# so they can never drift apart.
EVENT_ID_RE = re.compile(r"^evt-[0-9a-f]{4,16}$")

# A leading workflow prefix carries no information for a reader (every row in
# these tables already came from an iterate). Stripped at render time so
# historical rows read a little cleaner — the stored ``description`` is never
# mutated.
_LEADING_PREFIX_RE = re.compile(r"^\s*iterate(?:\s+fix)?\s*:\s*", re.IGNORECASE)


def event_anchor(event_id: str, rel_prefix: str = "") -> str | None:
    """Return ``{rel_prefix}#evt-…`` for a canonical event id, else ``None``.

    ``rel_prefix`` is empty for a same-document link (the RTM linking into its
    own Verification Timeline) and ``"traceability-matrix.md"`` for the Test
    Evidence report linking across to the sibling artifact in the same
    ``.shipwright/compliance/`` directory.
    """
    if isinstance(event_id, str) and EVENT_ID_RE.match(event_id):
        return f"{rel_prefix}#{event_id}"
    return None


def clean_description(description: str) -> str:
    """Strip a leading ``iterate:`` / ``iterate fix:`` prefix (render-time only)."""
    if not isinstance(description, str):
        return ""
    return _LEADING_PREFIX_RE.sub("", description).strip()


def event_display_name(we) -> str:
    """Human-facing label for an event row.

    Prefers the authored plain-language ``summary`` (forward-only field), then a
    lightly-cleaned ``description``, then the raw event id. ``summary`` is the
    only readability lever that can carry non-expert language; the cleanup is a
    conservative, lossless tidy of the existing technical text.
    """
    summary = (getattr(we, "summary", "") or "").strip()
    if summary:
        return summary
    cleaned = clean_description(we.description or "")
    return cleaned or we.id


__all__ = ["EVENT_ID_RE", "clean_description", "event_anchor", "event_display_name"]
