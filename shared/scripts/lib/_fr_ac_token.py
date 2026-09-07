"""The ``FR-XX.YY[/ACnn]`` TOKEN grammar — validation only, no source scanning.

Split out of ``fr_tag_grammar.py`` (P3.2, campaign req3-04c-ac-identity-wave2:
adding AC-suffix validation pushed that module past the 300-LOC bloat-baseline
threshold — the same reason ``_ac_markers.py`` was split out of ``ac_identity.py``
in P3.1). This module answers exactly one question, "is this FR[/AC] token one
``fr_tag_grammar`` can trust", and nothing about where in a SOURCE FILE a token
sits — that half stays in ``fr_tag_grammar.py``, which is the one importing this
module, never the other way round.

No content hash (D9): the AC half, when present, is the tool-minted ``[ACnn]``
identity from ``lib.ac_identity`` / ``lib._ac_markers`` — never a fingerprint of
the criterion's wording, which would break on every reword.
"""

from __future__ import annotations

import re

try:  # Package context — `from lib._fr_ac_token import …` (shared/tests).
    from .requirement_model import CANONICAL_FR_RE
except ImportError:  # Loaded by file path: no parent package.
    from requirement_model import CANONICAL_FR_RE  # type: ignore

try:  # Same dual-import pattern as CANONICAL_FR_RE above.
    from ._ac_markers import canonical_ac_id
except ImportError:
    from _ac_markers import canonical_ac_id  # type: ignore

_AC_SUFFIX_RE = re.compile(r"^AC(\d+)$")


def _canonical_ac_suffix(raw: str) -> str | None:
    """Validate an ``ACnn`` suffix (no leading ``/``), reusing — never
    reimplementing — ``_ac_markers``' canonical rule: the digit string must
    round-trip losslessly through ``AC{n:02d}``, so ``AC07`` is canonical but
    ``AC7``/``AC007`` are not. ``AC00`` is also rejected: ``mint()`` never
    assigns it (numbering starts at 1), so it can only be hand-typed — the
    same rule ``_ac_markers.parse_marker`` applies to a document marker."""
    m = _AC_SUFFIX_RE.match(raw)
    if not m:
        return None
    digits = m.group(1)
    num = int(digits)
    if num == 0:
        return None
    canonical = canonical_ac_id(num)
    return canonical if digits == canonical[2:] else None


def canonical_fr_ac(raw: str) -> tuple[str, str | None] | None:
    """Return ``(fr_id, ac_id)`` for a canonical ``FR-XX.YY`` or
    ``FR-XX.YY/ACnn`` token (with or without a leading ``@``), else ``None``.

    ``ac_id`` is ``None`` for the bare FR form — "covers the requirement, AC
    unspecified" (E1) — and the canonical ``ACnn`` rendering for the AC-scoped
    form. A malformed AC suffix invalidates the WHOLE token rather than
    silently falling back to the FR half — the same "never accept a partial
    match" rule ``fr_tag_grammar.TAG_TOKEN_RE`` already applies to the FR half:
    a caller that gets ``None`` must treat the entire raw string as unresolved,
    not retry it as a bare FR id.
    """
    token = raw[1:] if raw.startswith("@") else raw
    fr_part, sep, ac_part = token.partition("/")
    if not CANONICAL_FR_RE.match(fr_part):
        return None
    if not sep:
        return fr_part, None
    ac_id = _canonical_ac_suffix(ac_part)
    if ac_id is None:
        return None
    return fr_part, ac_id


__all__ = ["canonical_fr_ac"]
