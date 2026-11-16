"""Parsing of the Step 2 flag list handed to ``diff_risk_recheck`` (split out to keep
that module under its size limit; it re-exports :func:`_split_flags`)."""

from __future__ import annotations


def _split_flags(raw: str | None) -> list[str]:
    """Accept comma/newline lists AND a JSON array.

    `classify_complexity` emits `risk_flags` as a JSON array, so the obvious
    interpolation of Step 2's output is `["touches_auth", "touches_rls"]`. A
    naive split would yield `['["touches_auth"', '"touches_rls"]']` — tokens that
    still make `plan_review_required` fire (so AC5 looks fine) while Step 3.8's
    named-flag lookup for `touches_io_boundary` silently misses. Strip the JSON
    punctuation rather than trusting the caller to reformat.
    """
    if not raw:
        return []
    cleaned = raw.strip().lstrip("[").rstrip("]")
    parts = cleaned.replace(",", "\n").splitlines()
    return [p.strip().strip('"').strip("'") for p in parts if p.strip(" \"'\t")]
