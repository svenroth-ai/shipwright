"""SSOT for FR-classification predicates: is a change *traced* to a requirement?

BP-1 (campaign 2026-06-27-compliance-control-coverage). A ``work_completed``
iterate event is **traced** when it either:

- names the FR(s) it touches (``affected_frs`` / ``new_frs`` non-empty), OR
- is a **satisfied no-FR change**: a *behavior-preserving* change carrying a
  valid ``change_type`` (one of :data:`CHANGE_TYPE_VALUES`) AND a valid one-line
  ``none_reason``.

A **behavior-affecting** change (``spec_impact`` ∈ :data:`BEHAVIOR_AFFECTING`)
can NEVER be a satisfied no-FR change — it must link an FR. The record_event
FR-gate enforces that at write time; this module is the read-side predicate the
Control-Grade adapter and the dashboard traced-% metric share, so the gate's
notion of "classified" and the grade's notion of "traced" can never drift.

Deliberately self-contained (stdlib only) so the compliance plugin can load it
pollution-free via ``audit_adapters.load_shared_lib`` without binding ``lib`` in
``sys.modules`` — the same discipline ``events_amend`` follows.
"""

from __future__ import annotations

import re

# The closed no-FR vocabulary (mirrors record_event's CLI ``choices``).
CHANGE_TYPE_VALUES = ("docs", "tooling", "compliance", "infra")
# ~tweet-length: long enough for a real reason, short enough for a one-line grep.
NONE_REASON_MAX_LEN = 280
# spec_impact values that mean "this change alters an FR's observable behavior".
BEHAVIOR_AFFECTING = ("add", "modify", "remove")
# Disallow newlines, control chars and DEL; tab (0x09) is tolerated.
_NONE_REASON_CONTROL_RE = re.compile(r"[\x00-\x08\x0a-\x1f\x7f]")


def is_non_empty_fr_list(value) -> bool:
    """True iff ``value`` is a list with ≥1 non-empty-string element.

    Type-strict: rejects ``["", " "]``, tuples, and non-lists (a present-but-
    empty tag must fail like a missing one)."""
    if not isinstance(value, list):
        return False
    return any(isinstance(x, str) and x.strip() for x in value)


def is_valid_none_reason(value) -> bool:
    """Validate a ``none_reason``: a trimmed, single-line string ≤ the cap.

    Rejects non-strings, blank/whitespace-only, control chars (except tab), and
    anything longer than :data:`NONE_REASON_MAX_LEN`."""
    if not isinstance(value, str):
        return False
    if not value.strip():
        return False
    if _NONE_REASON_CONTROL_RE.search(value):
        return False
    if len(value) > NONE_REASON_MAX_LEN:
        return False
    return True


def is_behavior_affecting(spec_impact) -> bool:
    """True iff ``spec_impact`` declares the change alters an FR's behavior
    (add/modify/remove). Empty / ``none`` / missing ⇒ behavior-preserving."""
    return str(spec_impact or "").strip().lower() in BEHAVIOR_AFFECTING


def is_fr_tagged(affected_frs, new_frs=None) -> bool:
    """True iff the change names at least one FR (affected or new)."""
    return is_non_empty_fr_list(affected_frs) or is_non_empty_fr_list(new_frs)


def is_satisfied_no_fr(change_type, none_reason, spec_impact=None) -> bool:
    """True iff the change is a *valid, behavior-preserving* no-FR change.

    The discriminating definition the seam (Spec handoff) asked for: keying on
    mere presence of ``none_reason`` would be undiscriminating (near-universal),
    so a satisfied no-FR change requires the FULL discipline — a recognized
    ``change_type`` AND a valid ``none_reason`` AND no behavior impact."""
    return (
        change_type in CHANGE_TYPE_VALUES
        and is_valid_none_reason(none_reason)
        and not is_behavior_affecting(spec_impact)
    )


def is_traced(affected_frs, new_frs=None, change_type=None,
              none_reason=None, spec_impact=None) -> bool:
    """True iff the change is mapped to a requirement decision — either
    FR-linked or a satisfied no-FR change (BP-1's "FR or explicit no-FR")."""
    return is_fr_tagged(affected_frs, new_frs) or is_satisfied_no_fr(
        change_type, none_reason, spec_impact)
