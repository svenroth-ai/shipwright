"""Stable, tool-minted per-criterion identity for the SHIPPED FR heading +
bullet shape (campaign ``req3-04c-ac-identity-wave2``, sub-iterate P3.1;
``Spec/design/2026-07-22-req3-campaign-SPEC.md`` §8 E1).

**What an AC id is.** ``FR-01.11/AC07`` — an FR's id plus ``AC`` and a
monotonically-minted number, scoped to that FR, never renumbered, never
reused. The rule is the SAME one ``fr-authoring.md`` §4 already states for
FR ids themselves ("the next free number ... a retired number is never
reused"); this module is that rule applied one level down, to the criteria
inside one FR rather than to the FRs themselves.

**Why a tool, not a human, assigns it (E1).** A human typing the next number
can miscount or collide across two parallel edits; a tool computing it from
the existing evidence cannot. "The id is assigned, not typed" (E1) — you
write the criterion's prose, the id is stamped on afterwards.

**Why no content hash (D9).** Acceptance criteria get reworded; a
hash keyed to wording would break every existing tag the moment the sentence
was tightened. Identity here is NOT derived from the criterion's text at
all — once minted, the id is embedded literally in the document (the
``[ACnn]`` marker below) and travels with that line through every future
reword, exactly the way ``FR-01.11`` travels with its heading regardless of
how the requirement's name changes.

**The marker.** ``[ACnn]`` is inserted immediately after any existing
checkbox/assertion decoration and before the criterion's own text, e.g.::

    - (E) [AC07] Given a change ..., when ..., then ...

Square brackets are used (never parens) so the marker cannot be confused with
the `(E)` assertion marker or a trailing `(iterate-slug)` footnote — both of
which already use parens in this document shape. (A bracketed token can in
principle collide with Markdown's own link-reference syntax; not worth
changing the marker over — the canonical-form validation below makes any
such collision loud, not silent.)

**Scope — the SHIPPED shape only, not every shape `fr_criteria` tolerates.**
``lib.fr_criteria`` (R0) is the general reader: it also accepts a legacy
bold-anchor form (``**FR-XX.YY: Name**``) kept for older documents. Both
`mint()` and `read()` discover blocks through `_ac_blocks` (heading-anchored
only, ``### FR-XX.YY`` / any rank — see that module), so the two can never
see a different set of ids. Continuation-line joining and whitespace
normalisation are NOT reimplemented here: once a block is found, its
criteria still come from `fr_criteria.block_criteria(..., strict=True)`.

**Never renumbered, never reused — how.** A ``registry`` (``fr_id -> highest
number ever minted``) travels across runs. Re-running `mint()`:

1. seeds the registry from any ``[ACnn]`` markers already embedded, scanning
   EVERY bullet in each FR block (not just the leading run step 2 mints
   into — a marker outside it is still a real, already-assigned id), so a
   registry snapshot that lagged behind manual edits never causes a clash;
2. mints exactly the leading-run bullets that carry no marker yet, in
   document order, each getting ``registry[fr_id] + 1``.

An already-marked bullet is *never* touched, regardless of where it sits —
so inserting a new bullet in the middle of an already-minted list changes
nothing about the ids around it; the new bullet simply gets the next number,
which is not necessarily adjacent to its neighbours (exactly like an FR id).
Deleting a marked bullet does not free its number: the registry's per-FR
high-water mark only ever increases, so a later mint on the same FR can never
reissue it. This also means the registry may legitimately sit AHEAD of every
marker actually present in a document (a gap from a deleted criterion, or a
document/registry write interrupted between the two) — `mint()`'s seed pass
takes the MAXIMUM of what the registry already says and what the document
carries, in either order, so neither file needs to be the sole source of
truth and a half-applied `--write` self-heals on the next run.

**Fails loudly, never silently, on a marker that cannot be trusted (external
plan review, 2026-09-06).** A minted id is only "never authored" if nothing
downstream can quietly poison it by hand: `mint()` and `read()`/`read_all()`
both validate every marker they see and raise (never coerce or ignore) on:

* a non-canonical digit string — `[AC7]` or `[AC007]` when the canonical
  rendering of that number is `AC07` (``MalformedAcMarkerError``);
* two markers stacked on one criterion, e.g. ``[AC01] [AC02] Given ...``
  (``MalformedAcMarkerError``);
* two different criteria under the SAME FR carrying the SAME number
  (``DuplicateAcIdError``) — the one thing a hand-edit or a bad merge could
  otherwise introduce that neither the marker syntax nor the registry alone
  would catch.

**Two known, deferred effects of minting a REAL document (external plan
review; code review round 3).** `read()` strips `[ACnn]`, but
`lib.fr_criteria.criteria_for` itself does not know the marker exists — so
any OTHER `fr_criteria` caller reading an already-minted document sees
`[ACnn] ` as literal text:

1. a digest gate (e.g. `_layer_coverage_ac`) keyed to criterion text changes;
2. a minted PLACEHOLDER bullet stops collapsing to `fr_criteria`'s bare-
   placeholder token set — `"[AC01] TBD"` normalises to `ac01tbd`, which
   is not in that set — so a placeholder-only FR flips from `has_criteria =
   False` to `True` for every such caller (pinned today at
   `test_mint_and_read_agree_on_a_duplicate_split_across_a_placeholder`,
   which exercises the same collapse loss via the duplicate-detection path).

Both are inert today, since this run never mints the real spec.md; whoever
wires minting into a real, gate-read document (P3.2/P3.3) decides how to
handle them — named here so neither is a surprise there.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

_SHARED_SCRIPTS = Path(__file__).resolve().parents[1]
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

from lib import fr_criteria  # noqa: E402
from lib._ac_blocks import (  # noqa: E402
    embedded_ac_num,
    insert_marker,
    iter_all_bullet_positions,
    iter_bullet_positions,
    iter_heading_anchored_blocks,
)
from lib._ac_markers import (  # noqa: E402
    AcIdentityError,
    DuplicateAcIdError,
    MalformedAcMarkerError,
    canonical_ac_id,
    parse_marker,
)


class InvalidRegistryError(AcIdentityError):
    """A ``registry`` value ``mint()`` was handed is not a usable high-water
    mark: not an int, or negative. Validated in ``mint()`` itself (not just
    the CLI's own ``_load_registry``) because the registry is a public
    parameter any caller can pass directly — a negative value would flow
    straight into ``+ 1`` and could mint ``[AC00]``, which ``parse_marker``
    itself then rejects on the very next run (external code review,
    2026-09-06 round 2)."""


@dataclass(frozen=True)
class MintResult:
    """``mint()``'s output: the (possibly-updated) document text, the
    updated registry, and exactly the ids assigned THIS call — never the
    ones that were already present."""

    content: str
    registry: dict[str, int]
    assigned: tuple[tuple[str, str], ...]  # (fr_id, ac_id), document order


def mint(content: str, registry: dict[str, int] | None = None) -> MintResult:
    """Mint ``[ACnn]`` markers for every not-yet-marked criterion bullet in
    ``content``'s heading-anchored FR blocks.

    Idempotent: a bullet that already carries a marker is never rewritten and
    never contributes to ``assigned``; calling ``mint`` again on its own
    output with the returned ``registry`` is a no-op (``result.content ==
    content`` and ``result.assigned == ()``).

    Raises ``MalformedAcMarkerError`` on a marker that cannot be trusted
    (non-canonical digits, or two markers on one criterion) and
    ``DuplicateAcIdError`` when two different criteria under the same FR
    already carry the same number — either would silently break "never
    reused" if it were let through.
    """
    registry = dict(registry or {})
    for fr_id, value in registry.items():
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise InvalidRegistryError(
                f"{fr_id}: registry value must be a non-negative int, got {value!r}"
            )
    had_trailing_newline = content.endswith("\n")
    lines = content.split("\n")
    if had_trailing_newline and lines and lines[-1] == "":
        lines.pop()

    # Pass 1: seed the registry from ids the document already carries (in
    # EITHER direction relative to what the caller passed in — see module
    # docstring), so a registry snapshot older OR newer than a manual edit
    # can never cause a clash. Scans EVERY bullet in the block, not just the
    # leading run iter_bullet_positions gates minting to (external code
    # review, 2026-09-06 round 3): a marker sitting outside that run is
    # still a real, already-assigned id, and missing it here would let a
    # lost/stale registry re-mint that same number onto a different
    # criterion — the "never reused" violation this pass exists to prevent.
    # This is also the one place that can see two bullets under the same FR
    # sharing a number, since it visits every bullet in the block.
    seen: dict[str, set[int]] = {}
    for fr_id, idx in iter_all_bullet_positions(lines):
        existing = embedded_ac_num(lines[idx], fr_id=fr_id)
        if existing is None:
            continue
        if existing in seen.setdefault(fr_id, set()):
            raise DuplicateAcIdError(
                f"{fr_id}: more than one criterion is marked {canonical_ac_id(existing)}"
            )
        seen[fr_id].add(existing)
        registry[fr_id] = max(registry.get(fr_id, 0), existing)

    # Pass 2: mint exactly the unmarked bullets, in document order.
    assigned: list[tuple[str, str]] = []
    for fr_id, idx in iter_bullet_positions(lines):
        if embedded_ac_num(lines[idx], fr_id=fr_id) is not None:
            continue
        registry[fr_id] = registry.get(fr_id, 0) + 1
        ac_id = canonical_ac_id(registry[fr_id])
        lines[idx] = insert_marker(lines[idx], ac_id)
        assigned.append((fr_id, ac_id))

    new_content = "\n".join(lines) + ("\n" if had_trailing_newline else "")
    return MintResult(content=new_content, registry=registry, assigned=tuple(assigned))


def read(content: str, fr_id: str) -> list[tuple[str | None, str]]:
    """``(ac_id, criterion_text)`` for every criterion anchored to ``fr_id``
    in the shipped shape — ``ac_id`` is ``None`` for a bullet not yet minted.

    Discovery of WHICH blocks belong to ``fr_id`` is
    ``_ac_blocks.iter_heading_anchored_blocks`` — the same heading-only rule
    ``mint()`` uses (external code review, 2026-09-06: using
    ``fr_criteria.iter_anchored_blocks`` directly here also matched the
    legacy bold-anchor form, so ``read()`` could see an id ``mint()`` never
    scanned). Criterion TEXT extraction from each matching block is still
    ``fr_criteria.block_criteria(..., strict=True)`` (R0) — continuation-line
    joining and whitespace normalisation are not reimplemented here, and the
    ``[ACnn]`` marker (if present) is just ordinary leading text to it,
    unaffected by its checkbox/assertion stripping.

    Raises ``MalformedAcMarkerError`` / ``DuplicateAcIdError`` on a marker
    that cannot be trusted — see ``mint()``; a caller that only ever reads
    tool-minted documents will not hit either, but ``read()`` does not
    assume that of its input.
    """
    out: list[tuple[str | None, str]] = []
    seen: set[int] = set()
    for anchored_id, block in iter_heading_anchored_blocks(content):
        if anchored_id != fr_id:
            continue
        for text in fr_criteria.block_criteria(block, strict=True):
            num, remainder = parse_marker(text, fr_id=fr_id)
            if num is None:
                out.append((None, text))
                continue
            if num in seen:
                raise DuplicateAcIdError(
                    f"{fr_id}: more than one criterion is marked {canonical_ac_id(num)}"
                )
            seen.add(num)
            out.append((canonical_ac_id(num), remainder))
    return out


def read_all(content: str) -> dict[str, list[tuple[str | None, str]]]:
    """``read()`` for every HEADING-anchored FR id in ``content``, in the
    order each id is first encountered."""
    seen: dict[str, None] = {}
    for fr_id, _ in iter_heading_anchored_blocks(content):
        seen.setdefault(fr_id, None)
    return {fr_id: read(content, fr_id) for fr_id in seen}


__all__ = [
    "AcIdentityError",
    "DuplicateAcIdError",
    "InvalidRegistryError",
    "MalformedAcMarkerError",
    "MintResult",
    "mint",
    "read",
    "read_all",
]
