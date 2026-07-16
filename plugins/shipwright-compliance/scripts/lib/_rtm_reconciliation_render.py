"""cc3 (AR-05) RTM reconciliation-rendering helpers.

Extracted from :mod:`rtm_generator` to keep that grandfathered module under its
anti-ratchet ceiling. These render the BP-2 reconciliation signal into the
Requirements Traceability Matrix: the per-FR **Reconciled?** column, the **FRs
needing re-verification** summary subsection, the column legend, and clickable
``evt-`` evidence anchors.

The reconciliation status itself comes from the single SSOT
:func:`_reconciliation.compute_reconciliation` — the very helper the
Control-Grade reconciliation dimension (:func:`_control_block.build_grade_inputs`)
reads — so the matrix and the grade can never disagree, and both are
**age-neutral**: an old change that was re-verified stays reconciled forever;
only an unverified behavior change is surfaced.

Leaf module: top-level imports are stdlib only (the BP-2 helper is imported
lazily), so it never imports :mod:`rtm_generator` and cannot form a cycle.
"""

from __future__ import annotations

import re
from datetime import datetime

# Public surface re-exported by ``rtm_generator``. Declaring it also tells
# CodeQL's py/unused-global-variable that ``_RECONCILED_MARK`` (read across the
# module boundary, invisible to intra-file analysis) is intentionally exported.
__all__ = [
    "_EVENT_ID_RE",
    "_RECONCILED_MARK",
    "_NullReconciliation",
    "_compute_reconciliation_safe",
    "_coverage_table_legend",
    "_evt_anchor_ref",
    "_latest_event_for",
    "_render_needs_reverification_section",
]

# Work-event ids follow the `evt-<hex>` shape (see
# `shared/scripts/tools/record_event.py:_generate_id`). cc3 (AR-05) makes the
# "Verified By" iterate refs clickable: each `evt-` id links to a matching
# `<a id="evt-…">` anchor in the Verification Timeline (same document). Validate
# the shape before interpolating so a malformed wire id can't emit a broken
# href or a dangling anchor (mirrors `rtm_generator._TRIAGE_ID_RE`).
_EVENT_ID_RE = re.compile(r"^evt-[0-9a-f]{4,16}$")


def _evt_anchor_ref(event_id: str) -> str | None:
    """`#evt-…` same-document fragment for a canonical event id, else ``None``."""
    if isinstance(event_id, str) and _EVENT_ID_RE.match(event_id):
        return f"#{event_id}"
    return None


# Reconciled? cell glyphs, keyed by the reconciliation-status strings from
# `_reconciliation` (RECONCILED / NEEDS_REVERIFICATION / UNTOUCHED). Literal
# keys (not an import) keep the lazy-import contract — importing the helper pulls
# in `audit_adapters`' sys.path setup, which must stay off the import surface
# (see `_compute_reconciliation_safe`). A meta-test pins these keys against the
# helper's constants so they can't drift.
_RECONCILED_MARK = {
    "reconciled": "✅",
    "needs_reverification": "⚠️ needs re-verification",
    "untouched": "—",
}


class _NullReconciliation:
    """Fallback when the BP-2 helper can't be imported (minimal env): every FR
    reads as untouched, so the column degrades to ``—`` instead of crashing."""

    def status(self, fr_id: str) -> str:  # noqa: ARG002 - uniform interface
        return "untouched"

    @property
    def unreconciled(self) -> set[str]:
        return set()


def _compute_reconciliation_safe(work_events):
    """Lazy-import wrapper around ``_reconciliation.compute_reconciliation``.

    Mirrors ``rtm_generator``'s lazy ``triage`` import: keeps RTM generation
    crash-free in a minimal env and keeps the helper's ``audit_adapters``
    sys.path setup off the import surface. The grade dimension
    (``_control_block.build_grade_inputs``) reads the very same helper, so the
    RTM "Reconciled?" column and the Control-Grade reconciliation dimension can
    never disagree."""
    try:
        from scripts.lib._reconciliation import compute_reconciliation  # noqa: PLC0415
    except ImportError:
        return _NullReconciliation()
    try:
        return compute_reconciliation(work_events)
    except Exception:  # noqa: BLE001 - tolerant; an RTM render must never crash
        return _NullReconciliation()


def _coverage_table_legend() -> list[str]:
    """Decode the coverage table's terse columns (cc3 AR-05)."""
    # Built as a parenthesized expression (not adjacent literals inside the list)
    # so CodeQL's py/implicit-string-concatenation-in-list doesn't read it as a
    # missing comma.
    legend = (
        "> **Legend** — *Tests*: `passed/total` of the latest event that ran "
        "tests; `first → latest` shows progression across tested runs. "
        "*Last tested*: date of that event (`iter` / `build` source); age is "
        "informational, **not a penalty**. *Reconciled?*: ✅ behavior-affected "
        "FR re-verified since its last change · ⚠️ needs re-verification "
        "(behavior changed, not yet re-tested) · — not behavior-touched. "
        "*Unit / Integration / E2E* (traceability manifest): `ok` an executed-passing "
        "tagged test covers the FR at that layer · `MISSING` the layer is required but "
        "has no executed-passing test · `n/a` layer not required · — no manifest entry."
    )
    return [legend, ""]


def _parse_ts(ts):
    """Parse an ISO-8601 timestamp; ``None`` on malformed input (cite-only)."""
    try:
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except (ValueError, AttributeError, TypeError):
        return None


def _latest_event_for(events):
    """The event with the max *parsed* timestamp, or ``None`` (cite-only)."""
    parsed = [(e, _parse_ts(e.timestamp)) for e in events]
    parseable = [(e, dt) for e, dt in parsed if dt is not None]
    if parseable:
        return max(parseable, key=lambda p: p[1])[0]
    return events[-1] if events else None


def _render_needs_reverification_section(needs_reverify, fr_events_map) -> list[str]:
    """FRs whose behavior changed without a later test run (cc3/AR-05).

    Reconciliation-driven, **age-neutral**: an old but re-verified change never
    appears here. ``needs_reverify`` is the requirement list already filtered to
    ``Reconciliation.unreconciled`` by the caller, so this and the per-row
    ``Reconciled?`` column (and the Control-Grade dimension) agree by reading the
    one helper. Best-effort cites the latest event that touched the FR."""
    if not needs_reverify:
        return []
    lines = ["### FRs needing re-verification", ""]
    for req in needs_reverify:
        events = fr_events_map.get(req.id) or []
        latest = _latest_event_for(events)
        if latest is not None:
            ref = (
                latest.section if latest.source == "build" and latest.section
                else latest.id
            )
            suffix = f" — behavior last touched by `{ref}` ({latest.timestamp[:10]})"
        else:
            suffix = ""
        lines.append(
            f"- [{req.id}](../../{req.spec_path}) ({req.priority}): "
            f"behavior changed without a later test run{suffix}"
        )
    lines.append("")
    return lines
