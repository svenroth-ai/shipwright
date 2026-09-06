"""The ``[ACnn]`` marker GRAMMAR — validation only, no document scanning.

Split out of ``ac_identity.py`` (external plan review, 2026-09-06: adding
canonical-format + duplicate-marker validation pushed that module past the
300-LOC bloat-baseline threshold). This module answers exactly one question,
"is this marker one `ac_identity` can trust", and nothing about where in a
document a marker sits — that half stays in ``ac_identity.py``, which is the
one importing this module, never the other way round.

Square brackets, never parens, so a marker can never be confused with the
`(E)` assertion marker or a trailing `(iterate-slug)` footnote already used
in this document shape.
"""

from __future__ import annotations

import re

#: The AC-id marker itself: ``[AC07]``.
AC_MARKER_RE = re.compile(r"^\[AC(?P<num>\d+)\]\s*")

#: A NEAR-MISS at the start of the text -- case, whitespace, or a missing
#: closing bracket away from a real marker (``[AC 1]``, ``[ac01]``,
#: ``[AC01 :]``). Anchored at the start exactly like ``AC_MARKER_RE`` so a
#: literal ``[AC03]``-shaped substring mid-sentence is never flagged (external
#: code review, 2026-09-06 round 2: without this, a hand-typo like this was
#: silently read as ordinary prose on both `mint()` (stacks ANOTHER marker in
#: front of it on every rerun -- not idempotent) and `read()` (reports the
#: criterion as unminted forever), breaking the "fails loudly, never
#: silently" promise for exactly the input a human is likeliest to produce.
_NEAR_MISS_MARKER_RE = re.compile(r"^\[\s*AC\s*\d", re.IGNORECASE)


class AcIdentityError(ValueError):
    """Base class for a marker this module refuses to trust."""


class MalformedAcMarkerError(AcIdentityError):
    """A ``[AC...]`` marker that is not in canonical form, or a criterion
    carrying more than one of them."""


class DuplicateAcIdError(AcIdentityError):
    """Two different criteria under the same FR carry the same AC number."""


def canonical_ac_id(num: int) -> str:
    return f"AC{num:02d}"


def parse_marker(text: str, *, fr_id: str) -> tuple[int | None, str]:
    """``(number, remainder)`` for a ``[ACnn]`` marker at the START of
    ``text``, or ``(None, text)`` when there is none.

    Raises ``MalformedAcMarkerError`` rather than guessing when the marker
    cannot be trusted: a digit string that does not round-trip through the
    canonical ``AC{n:02d}`` rendering (``[AC7]``, ``[AC007]``), a second
    marker stacked right after the first (``[AC01] [AC02] Given ...``),
    ``[AC00]`` — ``mint()`` starts counting at 1, so a 0 can only be
    hand-typed (external code review, 2026-09-06) — or a NEAR-MISS that is
    not valid at all, e.g. ``[AC 1]`` or ``[ac01]`` (external code review,
    2026-09-06 round 2).
    """
    marker = AC_MARKER_RE.match(text)
    if not marker:
        if _NEAR_MISS_MARKER_RE.match(text):
            raise MalformedAcMarkerError(
                f"{fr_id}: text starts with something AC-marker-shaped that "
                f"is not a valid '[ACnn]' marker: {text!r}"
            )
        return None, text
    digits, num = marker.group("num"), int(marker.group("num"))
    canonical = canonical_ac_id(num)
    if num == 0:
        raise MalformedAcMarkerError(
            f"{fr_id}: marker '[AC{digits}]' is 0 -- mint() never assigns "
            f"that number, so it can only be hand-typed: {text!r}"
        )
    if digits != f"{num:02d}":
        raise MalformedAcMarkerError(
            f"{fr_id}: marker '[AC{digits}]' is not canonical (expected "
            f"'[{canonical}]') in: {text!r}"
        )
    remainder = text[marker.end():]
    if AC_MARKER_RE.match(remainder):
        raise MalformedAcMarkerError(
            f"{fr_id}: more than one AC marker on one criterion: {text!r}"
        )
    return num, remainder


__all__ = [
    "AC_MARKER_RE",
    "AcIdentityError",
    "DuplicateAcIdError",
    "MalformedAcMarkerError",
    "canonical_ac_id",
    "parse_marker",
]
