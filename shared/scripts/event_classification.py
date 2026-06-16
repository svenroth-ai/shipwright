"""Canonical normalization of work-event classification tokens.

Shared by the RTM *Verification Timeline* (compliance plugin) and the
Build-Dashboard *Recent Changes* table (shared/scripts/tools) so both render a
clean token in their ``Type`` column.

Why this exists: a handful of historical ``work_completed`` events leaked a
free-text *description* into the ``intent`` field (the real classification lived
in the orthogonal ``change_type`` field). A naive ``event["intent"]`` render
then dumped a 100-char sentence into the Type cell. Adopted repos additionally
seed ``intent`` from git conventional-commit types (``fix`` / ``docs`` /
``merge`` / ``chore`` / ``test``). This module collapses anything that is not a
clean, single-token classification down to a neutral default so the Type column
is always readable.

This is a top-level ``shared/scripts`` module (like ``markdown_table``) rather
than a ``shared/scripts/lib`` one so the compliance plugin can import it without
colliding with its own ``lib/`` regular package (see rtm_generator import note).
"""

from __future__ import annotations

#: The canonical iterate intent vocabulary (see record_event ``--intent``).
INTENT_CANONICAL = ("feature", "change", "bug")

#: Unambiguous aliases that map exactly onto the canonical vocabulary.
_INTENT_ALIASES = {
    "feat": "feature",
    "fix": "bug",
    "bugfix": "bug",
    "fixup": "bug",
}

#: A clean classification token is a single short word. A leaked free-text
#: description (the bug this guards against) carries whitespace or is long.
_MAX_TOKEN_LEN = 16


def normalize_intent(intent: str | None, *, default: str = "change") -> str:
    """Return a clean Type-column token for a work-event ``intent``.

    * ``feature`` / ``change`` / ``bug``      → unchanged
    * ``feat`` / ``fix`` / ``bugfix`` / ``fixup`` → canonical alias
    * any other single short word (``docs`` / ``test`` / ``merge`` …) → kept
    * empty, multi-word, or over-long (a leaked description) → ``default``
    """
    token = (intent or "").strip().lower()
    if not token:
        return default
    if token in _INTENT_ALIASES:
        return _INTENT_ALIASES[token]
    if token in INTENT_CANONICAL:
        return token
    if " " not in token and len(token) <= _MAX_TOKEN_LEN:
        return token
    return default
