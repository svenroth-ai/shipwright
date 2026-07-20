"""Canonical FR-id assignment for adopt's sequential feature/route numbering.

Adopt numbers detected features/routes ``1..N`` and stamps each with a
canonical requirement id. The canonical machine token is ``FR-GG.MM`` — exactly
two digits per side (``shared/scripts/lib/requirement_model.CANONICAL_FR_RE``).

A naive ``f"FR-01.{n:02d}"`` silently emits ``FR-01.100`` once ``n`` passes 99,
which is non-canonical: it fails ``is_canonical_fr`` and raises out of
``namespace_for_id`` downstream (trg-c9669d6a). This helper rolls the *group*
over at 99 instead — ``FR-01.99`` is followed by ``FR-02.01`` — so every id
stays canonical regardless of how many features a repo exposes.
"""

from __future__ import annotations

# Each side of a canonical id is two digits, so both group and minor span 1..99.
_PER_GROUP = 99
_MAX_GROUP = 99
# The last representable sequence position (FR-99.99).
MAX_SEQUENCE = _MAX_GROUP * _PER_GROUP


def canonical_fr_id(sequence: int) -> str:
    """Return the canonical ``FR-GG.MM`` id for a 1-based ``sequence`` position.

    ``1`` -> ``FR-01.01`` … ``99`` -> ``FR-01.99`` -> ``100`` -> ``FR-02.01``.
    The minor rolls at 99 and the group increments, keeping both sides two-digit
    so the result always satisfies the canonical ``FR-\\d{2}\\.\\d{2}`` grammar.

    Raises ``ValueError`` for a non-positive ``sequence`` or one so large the
    group would exceed 99 (> ``MAX_SEQUENCE`` features). A non-canonical id is
    never returned as a silent fallback — an overflow is a real (if absurd for
    adopt) condition the caller must see.
    """
    if sequence < 1:
        raise ValueError(f"FR sequence must be >= 1, got {sequence!r}")
    if sequence > MAX_SEQUENCE:
        raise ValueError(
            f"FR sequence {sequence} overflows the canonical FR-GG.MM space "
            f"(max {MAX_SEQUENCE} features)"
        )
    zero_based = sequence - 1
    group = zero_based // _PER_GROUP + 1
    minor = zero_based % _PER_GROUP + 1
    return f"FR-{group:02d}.{minor:02d}"
