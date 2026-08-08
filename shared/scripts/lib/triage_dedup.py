"""Dedup for the tracked triage log — the one path on this surface that can DROP
a record rather than supersede it.

Extracted from :mod:`lib.churn_merge` (which sits exactly at the 300-LOC
guideline) so the collision rule below has room to be stated; ``churn_merge``
re-exports :func:`dedup_triage_lines`, so the historical import path is
unchanged.

**Why this module is careful.** Triage ids are ``uuid4().hex[:8]`` — 32 bits, so
two *independently minted* items can share one (~1.2% at 10 000 appends). The
sibling :func:`lib.churn_merge.dedup_event_lines` refuses to drop in exactly that
case and warns, citing those 32-bit ids. This function did the opposite: it
collapsed same-id ``append`` events keep-last **and its docstring promised the
warning list was always empty**, so the one path that deletes a record was also
the one path that could not tell you it had (audit 2026-07-28, finding 25).

The collapse itself is load-bearing and is **kept** — ADR-163. A producer that
re-appends an UPDATED version of a finding writes a second, non-byte-identical
``append`` for that id; ``validate_triage_text`` enforces one append per id, so
without the collapse a legitimate refresh wedges the WHOLE outbox sweep (the
``trg-60ef91fb`` double-append that blocked the 2026-06-08 delivery). What ADR-163
never considered is the *other* shape that produces two appends for one id: a
32-bit collision between two genuinely different items. This module separates the
two and treats them differently.

**The discriminator is** :data:`IDENTITY_ANCHOR` — ``originalTs``, the timestamp of
an item's FIRST append, which a refresh preserves by construction while ``ts``
moves. Measured 2026-08-06 on the tracked log: **684 of 684** append lines carry a
valid non-empty ``originalTs``, so requiring it costs nothing real. (Count the records
by PARSING each line — a raw ``"event":"append"`` substring search returns 638 because
it misses the spaced serializations. Both figures describe the same 1:1 property.)

Two outcomes for a same-id ``append`` group — and a drop needs POSITIVE evidence:

* **supersession** — every record carries the anchor and they all AGREE. One
  logical item, refreshed. Collapse keep-last (ADR-163 unchanged) **and warn**.
* **collision** — anything else: the anchors DISAGREE, some records carry one and
  others do not, or NONE of them does. These may be distinct items sharing a
  32-bit id, and nothing here can tell. **Keep every line** and warn loudly,
  naming ``triage_repair.py``. ``validate_triage_text`` will then report a
  duplicate append and the caller will block — the correct, recoverable outcome.
  Deleting one of two real findings is not.

A missing anchor is therefore never permission to collapse. The tempting third arm
— "no anchor anywhere, so collapse anyway and merely warn" — was written and then
removed: it was defended as protecting an anchorless log from wedging, but the
defence assumed anchorless appends are common enough to matter while collisions
are not. They are equally rare. Both of ``triage.py``'s two append constructors
set ``originalTs`` unconditionally (``:408``, ``:530``), and every append line in the
tracked log carries a valid one, so an anchorless record can only come from a
hand-edit or a foreign writer — the same population as a collision. With no asymmetry
to trade on, the data-retention direction wins. The incident this function is named
for confirms the shape: ``.shipwright/triage.jsonl:285`` (``trg-60ef91fb``) is a
refreshed append whose ``ts`` moved while ``originalTs`` stayed at the first append's
instant — anchor-equality, written by the very writer that does not take our lock.

**What that corpus measurement does NOT establish**, stated so nobody leans on it
further than it goes (doubt review): it is taken from the SETTLED tracked log, where
the input this rule adjudicates — two appends sharing an id — does not occur at all
(0 of 684). It therefore says nothing about the conditional probability that a
same-id pair AGREES on the anchor, which is the only quantity the rule's accuracy
depends on. It establishes one narrower thing, which is all it is used for here: an
append without an anchor is not a shape any current writer produces. The choice to
retain rather than drop when the anchor is missing rests on the constitution's
never-lose-a-record direction, not on that number.

Residual, stated rather than hidden: two items minted in the SAME microsecond that
also collide on a 32-bit id would read as a supersession and one would be dropped
(with a warning). The corpus does contain 2 same-microsecond ``originalTs`` pairs,
so that half is real; the conjunction with an id collision is what makes it
negligible. ``status`` events — which intentionally share an id with their
``append`` — non-append lines, unparseable lines, and appends with a non-``str``
id are never touched by any of this.
"""

from __future__ import annotations

import json
from datetime import datetime

#: The field that identifies a triage item across re-appends. See the module
#: docstring for why this one and not a broader tuple: a refreshed rollup
#: legitimately changes its ``title``, so a title-sensitive anchor would re-create
#: the ADR-163 wedge this function exists to prevent.
IDENTITY_ANCHOR = "originalTs"


def _parsed_append(line: str) -> dict | None:
    """The decoded object iff ``line`` is an ``append`` event with a ``str`` id.

    Total: never raises. A deeply-nested value makes ``json.loads`` raise
    ``RecursionError`` (not a ``ValueError``) from its scanner — the same
    failure mode ``lib/jsonl_records.py`` already documents and catches at its
    own two call sites. Treated identically to a ``JSONDecodeError``: the line
    is unparseable as an append, so it is invisible to the same-id grouping
    below and falls through unmodified (card trg-57d0d6d3 / P2.19g, TEIL 2).
    ``TypeError`` is guarded too, for the reason ``sweep_canon.canonical_form``
    gives for the identical symmetry: the signature above only ever receives
    ``str`` today, but the "Total" claim is absolute, so it does not lean on
    caller discipline (doubt-reviewer finding 4, Stage 3, this run).
    """
    try:
        obj = json.loads(line)
    except (json.JSONDecodeError, TypeError, ValueError, RecursionError):
        return None
    if not isinstance(obj, dict) or obj.get("event") != "append":
        return None
    return obj if isinstance(obj.get("id"), str) else None


def _anchor_of(obj: dict) -> str | None:
    """The record's identity anchor as a COMPARABLE instant, or ``None`` when it does
    not carry a usable one. Empty and non-``str`` values are ``None``: an absent anchor
    and a blank one are the same amount of evidence.

    Normalised, not compared raw — and this is load-bearing. The only writer that
    produces same-id appends is the one that does not take our lock, and it
    demonstrably emits BOTH spellings of a UTC instant: ``.shipwright/triage.jsonl:285``
    (``trg-60ef91fb``, the very incident ADR-163's collapse exists for) carries
    ``"ts":"...+00:00"`` beside ``"originalTs":"...Z"`` in one record. On raw byte
    equality, a refresh that re-serialised ``Z`` as ``+00:00`` would read as a
    collision, both lines would be kept, the one-append-per-id validator would report a
    duplicate, and the sweep would return ``invalid`` — delivery off on every
    subsequent iterate. That is the exact terminal state this whole card exists to
    forbid, reached through the rule meant to prevent it (doubt review).

    Unparseable values fall back to the trimmed string: an anchor we cannot read is
    still an anchor two records can agree on, and disagreement only ever costs a
    refusal to collapse, which is the safe direction.
    """
    value = obj.get(IDENTITY_ANCHOR)
    # STRIP before the emptiness test, not after. Testing `not value` first let a
    # whitespace-only anchor through as "present", and the unparseable fallback then
    # normalised it to "" — so two distinct records carrying `" "` compared EQUAL and
    # one was dropped. Blank is blank (external code review).
    if not isinstance(value, str) or not value.strip():
        return None
    value = value.strip()
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).isoformat()
    except ValueError:
        return value


def _is_supersession(anchors: list[str | None]) -> bool:
    """True iff EVERY record in one same-id group carries the anchor and they all
    agree — the only state that licenses dropping a record.

    Grouped by exact anchor value rather than compared pairwise against the last
    kept line: a pairwise walk over three-plus records can chain A~B, B~C into an
    accidental A~C match and drop a record whose anchor nothing ever agreed with.
    """
    return all(a is not None for a in anchors) and len(set(anchors)) == 1


def dedup_triage_lines(lines: list[str]) -> tuple[list[str], list[str]]:
    """Dedup for the triage log, preserving order. Two collapses, in order:

    1. **Byte-identical** lines (the same event recorded on both merge sides) are
       dropped, first-seen order preserved. This deletes no information, so it
       never warns.
    2. **Same-id ``append`` events** are adjudicated by :func:`_is_supersession`
       and collapsed keep-last only when that is justified — see the module
       docstring. The reader overlays status in a SEPARATE ts-sorted pass, so
       dropping an earlier append never un-flips a status regardless of where the
       kept append lands relative to a status line.

    Returns ``(deduped, warnings)``. ``warnings`` is **no longer always empty**:
    every same-id append collapse reports itself, and a probable id collision
    reports itself loudly and drops nothing. Callers must surface them — but a
    warning is *not* an error and must never, by itself, stop delivery.
    """
    # (1) byte-identical dedup, first-seen order.
    seen: set[str] = set()
    interim: list[str] = []
    for line in lines:
        if not line.strip() or line in seen:
            continue
        seen.add(line)
        interim.append(line)

    # (2) group the same-id appends, then decide per group.
    groups: dict[str, list[int]] = {}
    parsed: dict[int, dict] = {}
    for i, line in enumerate(interim):
        obj = _parsed_append(line)
        if obj is None:
            continue
        parsed[i] = obj
        groups.setdefault(obj["id"], []).append(i)

    drop: set[int] = set()
    warnings: list[str] = []
    for item_id, idxs in groups.items():
        if len(idxs) < 2:
            continue
        if not _is_supersession([_anchor_of(parsed[i]) for i in idxs]):
            warnings.append(
                f"triage id {item_id!r} is shared by {len(idxs)} DISTINCT append lines that do "
                f"not agree on {IDENTITY_ANCHOR} (or do not all carry one) — possibly a 32-bit "
                "id collision between two real items, so ALL are kept and none is dropped. The "
                "one-append-per-id validator will report this; resolve it with "
                "tools/triage_repair.py rather than by deleting a line."
            )
            continue
        drop.update(idxs[:-1])
        warnings.append(
            f"triage id {item_id!r}: {len(idxs) - 1} earlier append(s) superseded by a later "
            f"one with the same {IDENTITY_ANCHOR} (kept last, reader parity)."
        )

    return [ln for i, ln in enumerate(interim) if i not in drop], warnings
