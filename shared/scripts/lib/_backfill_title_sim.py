"""Title-similarity scoring for the shared backfill engine (see ``backfill_signals``).

Extracted when fold-map awareness pushed ``backfill_signals`` past the 300-LOC cap. The
seam is cohesive: this is the whole of the *fuzzy* signal — tokenise a test name and an
FR description, score their overlap — kept apart from the deterministic cascade and the
orphan classification that consume it.

The caps encoded here are the reason the fuzzy leg can never auto-write: ``TITLE_CAP``
(0.70) sits below ``AUTO_WRITE_THRESHOLD`` (0.90) by construction, so a title match can
only ever produce an advisory proposal a human reviews. ``tokenize`` / ``jaccard`` are
re-exported from ``backfill_signals`` for callers that already import them there.
"""

from __future__ import annotations

import re

TITLE_MIN = 0.30           # below this, title similarity is noise
TITLE_CAP = 0.70           # title similarity can never reach the auto-write floor

_STOPWORDS = frozenset({
    "test", "tests", "the", "a", "an", "to", "of", "and", "or", "is", "are", "be",
    "can", "should", "when", "then", "with", "for", "in", "on", "at", "it", "its",
    "that", "this", "as", "by", "from", "into", "user", "users", "does", "do",
})
_TOKEN_RE = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> set[str]:
    """Lower-case alphanumeric tokens minus stopwords (title-similarity input)."""
    return {t for t in _TOKEN_RE.findall(text.lower()) if t not in _STOPWORDS and len(t) > 2}


def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def title_scores(name: str, frs_by_id: dict, only_ids) -> list[tuple[str, float]]:
    """``[(fr_id, score), …]`` for FRs whose description overlaps ``name``.

    Sorted strongest-first with the id as tiebreak, so a caller's pick is deterministic
    when two FRs score identically. Takes ``frs_by_id`` rather than the resolution
    context so this stays independent of the cascade's shape.
    """
    name_tokens = tokenize(name)
    scored: list[tuple[str, float]] = []
    for fid in only_ids:
        fr = frs_by_id.get(fid)
        if fr is None:
            continue
        sim = jaccard(name_tokens, tokenize(fr.text))
        if sim >= TITLE_MIN:
            scored.append((fid, min(sim, TITLE_CAP)))
    scored.sort(key=lambda x: (-x[1], x[0]))
    return scored


__all__ = ["TITLE_CAP", "TITLE_MIN", "jaccard", "title_scores", "tokenize"]
