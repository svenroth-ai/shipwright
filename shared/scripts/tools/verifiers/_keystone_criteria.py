"""THE KEYSTONE GATE's per-criterion digest reader, split out of
``_keystone_ac_digest`` to buy back headroom at its 300-line limit after the
Stage-3 doubt-review fix (cross-spec-path collision detection). Pure text
parsing, no git.

Re-exported from :mod:`_keystone_ac_digest`, which stays the one import site
callers and tests use.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

# ADR-045: this module's own bootstrap, never relying on `verifiers/__init__.py`'s
# side effect (Stage-2 code review, low; found during build) -- every sibling
# verifiers module that reaches into `lib` carries this same four-line insert,
# and an implicit import-order dependency on the package `__init__` is exactly
# the coupling ADR-045 exists to avoid.
_SHARED_SCRIPTS = Path(__file__).resolve().parents[2]
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

from lib import ac_identity  # noqa: E402

from ._keystone_base_manifest import ReadError  # noqa: E402


def _digest(*parts: str) -> str:
    return hashlib.sha256("\x00".join(parts).encode("utf-8")).hexdigest()


def ac_criteria_digests(text: str) -> tuple[dict[tuple[str, str], str], set[str]]:
    """``({(fr_id, ac_id): digest}, {digest of each UNMINTED criterion})``.

    ``read_all`` returns ``dict[fr_id, list[(ac_id | None, text)]]`` — iterate
    ``.items()``; iterating the mapping itself yields FR-ID STRINGS.

    Unminted criteria are digested over ``(fr_id, text)``, never bare ``text``:
    identical boilerplate under two FRs would otherwise collapse to one digest,
    and an unminted criterion moved verbatim from FR-A to FR-B would cancel out
    in the set difference and go undetected.

    Raises :class:`ReadError` on a marker that cannot be trusted — a
    non-canonical ``[AC7]``, two markers on one criterion, or two criteria under
    one FR sharing a number. Never coerced, never ignored: an untrustworthy
    marker breaks "never reused", which is the whole basis of AC identity.
    """
    minted: dict[tuple[str, str], str] = {}
    unminted: set[str] = set()
    try:
        blocks = ac_identity.read_all(text)
    except ac_identity.AcIdentityError as exc:
        raise ReadError(f"acceptance-criteria markers are not trustworthy: {exc}") from exc
    for fr_id, items in blocks.items():
        for ac_id, criterion in items:
            if ac_id is None:
                unminted.add(_digest(fr_id, criterion))
            else:
                minted[(fr_id, ac_id)] = _digest(fr_id, ac_id, criterion)
    return minted, unminted


def unminted_texts(text: str) -> dict[str, tuple[str, str]]:
    """``digest -> (fr_id, criterion_text)``, so a finding can quote the
    criterion rather than only its hash. Re-parses rather than widening
    :func:`ac_criteria_digests`'s return shape; the only caller reaches here
    AFTER that call returned, so ``read_all`` cannot raise a second time."""
    out: dict[str, tuple[str, str]] = {}
    for fr_id, items in ac_identity.read_all(text).items():
        for ac_id, criterion in items:
            if ac_id is None:
                out[_digest(fr_id, criterion)] = (fr_id, criterion)
    return out


__all__ = ["ac_criteria_digests", "unminted_texts"]
