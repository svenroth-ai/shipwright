"""Mechanical AC-scoped tag derivation from criterion provenance footnotes (P3.4).

The tagging-backfill unit (campaign ``req3-04c-ac-identity-wave2``, P3.4) prefers
mechanical derivation over hand-mapping wherever a real, non-content-reading
signal exists. ``ac_identity.mint`` gives every criterion a stable ``ACnn``
id; separately, a criterion the AC-identity work post-dates a `fr-authoring.md`
convention already carries a trailing provenance footnote naming the iterate
that introduced or last touched it, e.g.::

    - (E) Given ... (iterate-2026-07-21-review-record)

That footnote's slug is ALSO, independently, the ``Run-ID:`` trailer the same
iterate's own finalization commit carries (F6, ``references/F3.md``/commit
convention) — so the two can be joined without reading any test's content: a
footnote naming exactly one criterion within its FR resolves to exactly one
``(fr_id, ac_id)`` pair, and the commit(s) carrying that Run-ID name exactly
the files that iterate touched.

**Why "exactly one criterion" is required, not advisory.** A footnote shared by
two or more criteria names an iterate that touched more than one criterion in
the same change — real provenance, but not resolvable to a SINGLE AC without
reading which test covers which of the two, which is exactly the hand-mapping
this module exists to avoid doing by guesswork. Such a slug is dropped here,
never guessed; the module intentionally has no fallback tier the way
``backfill_signals`` layers title-similarity under its deterministic signals
(D9: no content hash, no content read, nothing here fuzzy — a pure provenance
JOIN).

**Uniqueness is DOCUMENT-WIDE, not per-FR (P3.4 post-hoc fix).** An earlier
version of this join scoped the "exactly one" check to the slug's own FR, on
the theory that the same iterate touching one criterion in FR-A and a
different, also-singular criterion in FR-B is two independent, individually
resolvable facts. That theory is wrong for the failure mode it actually
missed: an iterate that delivers several criteria in ONE commit, spread across
TWO FRs, can land exactly once (unique) in FR-A while landing 2+ times
(correctly dropped) in FR-B — and the FR-A occurrence is then trusted despite
the underlying commit having touched multiple, materially different criteria.
Measured on this repo's own spec.md: ``iterate-2026-07-27-name-the-blocker``
is unique within FR-01.03 (1 bullet, AC19) but appears 3 times within
FR-01.11 (AC16/AC19/AC20) — a single commit that delivered four distinct
criteria across two FRs, not the "one iterate, one criterion" shape the
per-FR check assumed. The FR-01.03 occurrence was wrongly trusted, and its
derived tag (applied to 7 test files) did not match those files' actual
content on manual re-verification. The rule is therefore: a slug is used only
when it names exactly ONE ``(fr_id, ac_id)`` pair across the ENTIRE minted
document — the same conservatism the per-FR check intended, just applied at
the scope the underlying commit actually operates at (a git commit has no
notion of "per FR").

Pure text/data logic only — no I/O, no git. The git correlation (finding the
commit(s) that carry a given ``Run-ID:`` trailer, and what they touched) is the
CLI's job (``tools/backfill_ac_provenance.py``), kept apart so this module's
join logic is unit-testable without a repository.
"""

from __future__ import annotations

import re

#: A trailing provenance footnote: one or more comma-separated iterate-slugs or
#: ADR ids in parens at the very end of a (whitespace-normalised) criterion
#: text, e.g. ``(iterate-2026-07-21-review-record)`` or
#: ``(iterate-2026-07-27-no-silent-revert, iterate-2026-07-28-silent-revert-false-positives)``.
_FOOTNOTE_RE = re.compile(
    r"\(((?:iterate|adr)-[a-z0-9][a-z0-9-]*(?:,\s*(?:iterate|adr)-[a-z0-9][a-z0-9-]*)*)\)\s*$"
)


def footnote_slugs(criterion_text: str) -> list[str]:
    """The trailing provenance footnote's slugs, in document order, or ``[]``
    when the criterion carries none (most of the pre-convention baseline)."""
    m = _FOOTNOTE_RE.search((criterion_text or "").strip())
    if not m:
        return []
    return [s.strip() for s in m.group(1).split(",")]


def unique_provenance_acs(read_all: dict[str, list[tuple[str | None, str]]]) -> dict[str, dict[str, str]]:
    """``fr_id -> {slug: ac_id}`` for every footnote slug that names EXACTLY ONE
    ``(fr_id, ac_id)`` pair across the WHOLE document (see the module
    docstring's "document-wide, not per-FR" note for why per-FR scoping is
    unsound).

    ``read_all`` is ``lib.ac_identity.read_all``'s own return shape (already-
    minted document): ``fr_id -> [(ac_id_or_None, criterion_text), ...]``. A
    bullet with no minted ``ac_id`` (``None``) contributes no signal — this
    module only ever names a REAL, tool-minted AC, never a bare FR (E1).
    """
    slug_to_pairs: dict[str, set[tuple[str, str]]] = {}
    for fr_id, pairs in read_all.items():
        for ac_id, text in pairs:
            if ac_id is None:
                continue
            for slug in footnote_slugs(text):
                slug_to_pairs.setdefault(slug, set()).add((fr_id, ac_id))
    out: dict[str, dict[str, str]] = {}
    for slug, pairs in slug_to_pairs.items():
        if len(pairs) != 1:
            continue
        (fr_id, ac_id) = next(iter(pairs))
        out.setdefault(fr_id, {})[slug] = ac_id
    return out


__all__ = ["footnote_slugs", "unique_provenance_acs"]
