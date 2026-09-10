"""Per-AC change detection for THE KEYSTONE GATE (P3.6) — the git-facing half.

Design: ``.shipwright/planning/iterate/2026-09-09-p3-6-keystone-gate.md`` §5.1/§5.3.

This is the capability P3.1's ``[ACnn]`` markers exist to enable and that nothing
consumed until now: ``_layer_coverage_ac.criteria_digests`` hashes an FR's POOLED
criteria text, so it can say "some criterion of FR-01.11 changed" and never
"AC17 changed". Per-AC digests make the second answerable, which is what lets the
gate re-run exactly the tests bound to the criterion that moved.

Two properties fall out of keying on the marker rather than on position, both
strictly better than the pooled digest: **reordering is not a change** (the id
travels with the line) and **reflow is not a change**
(``fr_criteria.block_criteria`` joins continuations and normalises whitespace
before the digest is taken).

**The two criteria readers are NOT interchangeable** — assuming they were
produced a repo-wide false-red in an earlier draft. ``ac_identity.read_all``
(this module's) is heading-anchored and ``strict=True``: only the CONTIGUOUS
LEADING bullet run counts. ``_layer_coverage_ac.criteria_digests`` (the FR-level
gate's) also matches the legacy bold-anchor form and is ``strict=False``
DELIBERATELY, so an introductory note between an FR's heading and its bullets
does not hide them. An FR whose bullets follow a prose sentence therefore yields
ZERO criteria here and NON-ZERO there; :func:`ac_change_set` reports that as
``reader_divergence``, scoped to what THIS PR caused (see the three arms at its
call site). A repo-wide divergence is a drift TEST's job, not a per-PR gate's.

**Silence is the one failure worse than over-firing** (``_layer_coverage_ac
._criteria_region`` states this rule for its own reader; it binds here too), so
every read has a named verdict and none of them is "no ACs changed":

* a malformed/duplicate marker at HEAD -> ``ReadError`` (the CLI exits 2);
* the same at BASE -> base is treated as empty + a warning. Asymmetric on
  purpose: a base commit is already merged and cannot be authored by this PR, so
  the lenient direction is not exploitable, and it lets a branch forked before
  the P3.4 mint pass cleanly;
* ``spec_text_at`` returning ``None`` (git could not read a side) -> ``ReadError``.
"""

from __future__ import annotations

import hashlib
import sys
from dataclasses import dataclass, field
from pathlib import Path

_SHARED_SCRIPTS = Path(__file__).resolve().parents[2]
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

from lib import ac_identity  # noqa: E402

from ._keystone_base_manifest import (  # noqa: E402  (re-exported: one import site for callers)
    MANIFEST_RELPATH,
    ReadError,
    read_base_manifest,
    require_manifest_shape,
)
from ._layer_coverage_ac import _spec_paths, criteria_digests, spec_text_at  # noqa: E402

#: ``criteria_digests`` hashes the JOINED criteria text, so an FR with NO criteria
#: gets the sha256 of the empty string -- a perfectly non-empty *string*. Testing
#: that digest for truthiness would therefore call every criteria-less FR
#: "visible to the FR-level reader" and report a divergence for it.
_EMPTY_CRITERIA_DIGEST = hashlib.sha256(b"").hexdigest()


@dataclass
class AcChangeSet:
    changed: set[tuple[str, str]] = field(default_factory=set)
    added: set[tuple[str, str]] = field(default_factory=set)
    removed: set[tuple[str, str]] = field(default_factory=set)
    #: (fr_id, criterion_text) for each criterion this PR changed OR added that
    #: carries no ``[ACnn]``.
    unminted_changed: list[tuple[str, str]] = field(default_factory=list)
    new_frs_without_criteria: list[str] = field(default_factory=list)
    reader_divergence: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not (self.changed or self.added or self.removed or self.unminted_changed
                    or self.new_frs_without_criteria or self.reader_divergence)


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


def _unminted_texts(text: str) -> dict[str, tuple[str, str]]:
    """``digest -> (fr_id, criterion_text)`` for the unminted criteria, so a
    finding can quote the criterion rather than only its hash. Re-parses rather
    than widening :func:`ac_criteria_digests`'s designed return shape; the only
    caller reaches here AFTER that call returned, so ``read_all`` cannot raise a
    second time on the same text."""
    out: dict[str, tuple[str, str]] = {}
    for fr_id, items in ac_identity.read_all(text).items():
        for ac_id, criterion in items:
            if ac_id is None:
                out[_digest(fr_id, criterion)] = (fr_id, criterion)
    return out


def _active_display_ids(manifest: dict) -> set[str]:
    return {
        node["id"]
        for node in (manifest.get("requirements") or {}).values()
        if isinstance(node, dict) and node.get("status") == "active"
        and isinstance(node.get("id"), str)
    }


def ac_change_set(
    project_root: Path, base_sha: str, head_sha: str,
    head_manifest: dict, base_manifest: dict,
) -> AcChangeSet:
    """The per-AC change set between ``base_sha`` and ``head_sha``.

    Spec paths are the UNION of both manifests (``_spec_paths`` is variadic
    exactly for this — "so a spec that was renamed or added between base and head
    is still compared"). Head-only would make a spec file this PR REMOVES or
    RENAMES invisible, including to the ``binding_removed`` check — the same
    subtractability the gate exists to prevent.
    """
    result = AcChangeSet()
    base_minted: dict[tuple[str, str], str] = {}
    base_unminted: set[str] = set()
    head_minted: dict[tuple[str, str], str] = {}
    head_unminted: set[str] = set()
    head_texts: dict[str, str] = {}
    base_fr_digests: dict[str, str] = {}
    head_fr_digests: dict[str, str] = {}
    head_seen_frs: set[str] = set()
    base_seen_frs: set[str] = set()

    for rel_path in _spec_paths(head_manifest, base_manifest):
        base_text = spec_text_at(project_root, base_sha, rel_path)
        head_text = spec_text_at(project_root, head_sha, rel_path)
        if base_text is None or head_text is None:
            side = "base" if base_text is None else "head"
            raise ReadError(f"could not read {rel_path} at the {side} commit")

        h_minted, h_unminted = ac_criteria_digests(head_text)
        head_minted.update(h_minted)
        head_unminted |= h_unminted
        head_texts.update(_unminted_texts(head_text))
        head_fr_digests.update(criteria_digests(head_text))
        # NON-EMPTY criteria lists only. `read_all` returns a key for EVERY
        # heading-anchored FR id, including one whose leading bullet run is empty
        # -- so keying on the id would report "this reader can see it" for exactly
        # the FRs it cannot see, and the divergence guard would never fire.
        head_seen_frs |= {
            fr for fr, items in ac_identity.read_all(head_text).items() if items
        }

        try:
            b_minted, b_unminted = ac_criteria_digests(base_text)
        except ReadError as exc:
            # Lenient at BASE only -- see the module docstring. A pre-mint or
            # hand-broken base must not block a PR that cannot have caused it.
            result.warnings.append(
                f"{rel_path}: base commit's AC markers could not be parsed ({exc}); treating base "
                "as having no acceptance criteria, so every head AC reads as newly added."
            )
            b_minted, b_unminted = {}, set()
        else:
            base_seen_frs |= {
                fr for fr, items in ac_identity.read_all(base_text).items() if items
            }
        base_minted.update(b_minted)
        base_unminted |= b_unminted
        base_fr_digests.update(criteria_digests(base_text))

    for key, head_digest in head_minted.items():
        base_digest = base_minted.get(key)
        if base_digest is None:
            result.added.add(key)
        elif base_digest != head_digest:
            result.changed.add(key)
    result.removed = set(base_minted) - set(head_minted)

    for digest in sorted(head_unminted - base_unminted):
        result.unminted_changed.append(head_texts.get(digest, ("<unknown FR>", "")))

    # Reader divergence, SCOPED to what THIS PR caused. An unscoped guard would
    # red every later PR in the repo -- including docs-only ones -- from the day
    # one FR acquires an introductory sentence. Three scoping signals, and the
    # first is why the design's single `criteria_digests(base) != (head)` test is
    # not enough on its own (found by the AC-K9(d)(i) test at build time):
    # ADDING the intro sentence changes NO criterion text, so the FR-level digest
    # is byte-identical across the very PR that creates the divergence. Without
    # arm (a), that PR passes silently, the AC vanishes from this reader, and the
    # NEXT PR to edit it reads `added` rather than `changed` -- i.e. never blocks
    # on greenness. That is the two-step version of the dodge the gate exists for.
    #
    # ACTIVE FRs only. The design states the predicate twice as "read_all yields
    # zero criteria for an ACTIVE FR" (§5.1, AC-K9(d)), and every sibling predicate
    # in this gate filters the same way (`_links_for`, `_keystone_layer_gap._fr_node`,
    # `_active_display_ids`). It was dropped here by omission, not by decision --
    # found by a Stage-1 spec review. Unreachable today (no retired FR has an
    # intro-sentence-before-bullets shape), and "latent today" is exactly the
    # reasoning round 3 rejected once already: a spec.md heading survives
    # retirement, so the day one retired FR gains an intro sentence this guard
    # HARD-blocks a PR over a requirement the rest of the gate does not enforce.
    head_active_frs = _active_display_ids(head_manifest)
    for fr_id, head_fr_digest in sorted(head_fr_digests.items()):
        if fr_id not in head_active_frs:
            continue  # retired/absent at head -- out of scope, like every sibling
        if fr_id in head_seen_frs:
            continue  # this reader CAN see it -- no divergence
        if head_fr_digest == _EMPTY_CRITERIA_DIGEST:
            # Both readers agree there is nothing here. That is arm 2's input
            # ("a new FR stating no criterion"), whose remedy -- state one -- is
            # the opposite of divergence's ("move the note below the bullets").
            continue
        caused_here = (
            fr_id in base_seen_frs                          # (a) it was visible at base
            or fr_id not in base_fr_digests                 # (b) the FR is new at head
            # (c) `.get`, never a bare subscript: an FR absent at base would
            # otherwise raise KeyError INSIDE the guard.
            or base_fr_digests.get(fr_id) != head_fr_digest  # (c) its criteria changed
        )
        if caused_here:
            result.reader_divergence.append(fr_id)

    # Arm 2's input, stated as the set operation it is (external plan review, glm,
    # low: round 3's `.get(fr)` finding was the same family -- an unstated set
    # operation over two manifests is where the null case hides). "NEW active FR"
    # == a DISPLAY id carried by an `active` requirement in the HEAD manifest and
    # by no active requirement in the BASE one.
    #
    # ...which is why the empty base manifest SUPPRESSES the arm entirely. Under
    # `base_manifest_absent` every head FR trivially satisfies "absent at base",
    # so arm 2 would fire for every criteria-less FR in the repo at once -- a
    # repo-wide false red in the one mode that already degrades, and the same
    # blast-radius mistake round 3 fixed for the divergence guard. "New" is not
    # answerable without a base to be new relative to, so it is not answered.
    diverged = set(result.reader_divergence)
    # Same precedence as `diverged`: an FR already reported by arm 1
    # (`unminted_changed`) is NOT "states no acceptance criterion" -- it states
    # one or more, unminted. Without this exclusion a brand-new FR authored with
    # bullets but no `[ACnn]` markers fires BOTH arms, and arm 2's message then
    # tells the operator to do something they already did (found by Stage-2
    # code review: the single most likely first real-world encounter with this
    # gate is exactly this shape -- an FR hand-authored before running the
    # minter).
    unminted_frs = {fr for fr, _ in result.unminted_changed}
    base_ids = _active_display_ids(base_manifest)
    if base_ids:
        for fr_id in sorted(_active_display_ids(head_manifest) - base_ids):
            if fr_id in diverged or fr_id in unminted_frs:
                continue
            if not any(k[0] == fr_id for k in head_minted):
                result.new_frs_without_criteria.append(fr_id)
    elif _active_display_ids(head_manifest):
        result.warnings.append(
            "the base manifest names no active requirement, so 'is this FR new?' is "
            "unanswerable; the new-FR-without-criteria arm is suppressed for this run."
        )
    return result


__all__ = [
    "MANIFEST_RELPATH", "AcChangeSet", "ReadError",
    "ac_criteria_digests", "ac_change_set", "read_base_manifest",
    "require_manifest_shape",
]
