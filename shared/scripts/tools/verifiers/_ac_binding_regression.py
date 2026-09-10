"""Arm 2 of the orphan-test detector (P3.7, SPEC §8 E2(b)) — a binding dropped
on an AC whose criterion TEXT this PR never touched.

**Naming, precisely (external plan review, openai, low).** This arm detects
an AC-WITHOUT-A-TEST REGRESSION on a criterion that still exists — not
literally "a test whose AC vanished" (that is arm 1's predicate: a binding
tag naming an AC id the spec no longer contains). It is grouped under
feeder (b), HARD and unbaselined, because it is the anti-evasion complement
to feeder (a)'s SAME-PR-baseline loophole (design doc, Known Limitations):
without it, an author could unbind an AC and simultaneously ``--write`` the
ratchet baseline to grandfather it in the very same PR. Both arms share a
MISSION ("a bound AC's
binding must not silently disappear"), not one literal condition — see the
next paragraph for why arm 1 alone cannot cover this.

**Why a second arm, when the shared brief names ONE condition** ("a binding
tag naming an AC id that the current spec's minted criteria no longer
contain" — ``_ac_binding_state.BindingState.orphaned``, arm 1): building
arm 1 and tracing the two-PR unbind sequence (case (i), P3.6 design §7/§10
item 8) through it by hand shows arm 1 does NOT close case (i). Recorded
here rather than silently assumed closed, per this campaign's own rule that
a found gap is disclosed, not hidden (the same honesty p3.6's own "Known
limitations" section models throughout).

Concretely: case (i)'s PR1 "deletes the ``/ACnn`` suffix from a ``@covers``
tag" — the tag becomes a bare, VALID FR-level tag. Nothing about it names a
vanished AC id, so it produces no arm-1 finding; the manifest's regenerated
``acs`` map simply stops carrying a key for that AC at all. That state is
existing backlog, and existing backlog is precisely feeder (a)'s ratcheted
territory (``check_ac_coverage_ratchet.py``), not feeder (b)'s hard one — an
AC an author deliberately generalises away from is not "vanished", and
demanding a criterion-level justification for every such retag would widen
this gate into the coverage-breadth check P3.6's own design explicitly
declines to be (design doc §7, deviation 3's scope note).

**What actually addresses case (i)** is P3.6's own diagnosis of its blind spot
(design doc §7): "Closing it needs a signal that does not depend on the AC's
text changing." That is exactly this arm: an AC whose criterion digest is
IDENTICAL at base and head (so it is invisible to every text-diff-keyed
check, P3.6's ``binding_removed`` included) that had >=1 manifest link at
base and has 0 at head. Blocking THIS blocks PR1 itself — the commit that
actually performs the unbind — rather than waiting to catch PR2's exploit of
the already-unbound state.

**Narrower claim than "closes" (external plan review, openai, HIGH).** This
arm's only evidence of "had a link at base" is the BASE MANIFEST, which is
read from the last commit at base and never regenerated (P3.6 design §7's
own disclosed staleness, inherited here rather than re-solved — see this
module's own docstring further down and the design doc's Known
Limitations). If that committed artifact never recorded the binding in the
first place (a stale or hand-edited base manifest), this arm has nothing to
compare against and stays silent. The accurate claim is: this arm detects
PR1 of the two-PR sequence **whenever the base manifest's own record of the
binding is trustworthy** — not an unconditional closure.

Reuses ``_keystone_criteria.ac_criteria_digests`` (P3.6's per-AC digest —
same reader, not a second one), ``_layer_coverage_ac._spec_paths``/
``spec_text_at`` (the UNION-of-both-sides reader P3.6's own §5.1 union
argument applies here verbatim), and ``_keystone_links.links_for``.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SHARED_SCRIPTS = Path(__file__).resolve().parents[2]
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

from ._keystone_ac_digest import ReadError  # noqa: E402
from ._keystone_criteria import ac_criteria_digests  # noqa: E402
from ._keystone_links import links_for  # noqa: E402
from ._layer_coverage_ac import _spec_paths, spec_text_at  # noqa: E402
from ._layer_coverage_core import collision_display_ids  # noqa: E402


def head_and_base_minted(
    project_root: Path, base_sha: str, head_sha: str, head_manifest: dict, base_manifest: dict,
) -> tuple[dict[tuple[str, str], str], dict[tuple[str, str], str], list[str]]:
    """``({(fr, ac): digest} at head, ditto at base, warnings)`` over the union
    of spec paths either manifest names.

    Raises :class:`ReadError` when a NAMED path could not be read at HEAD —
    a genuine infra fault, matching every sibling reader in this family. The
    BASE side is lenient (warning, treated as empty) for the same reason
    ``_keystone_ac_digest.ac_change_set`` is lenient there: a base commit is
    already merged and cannot be authored by this PR. This applies to BOTH a
    ``None`` (real git/IO fault) and an unparseable base text alike (external
    code review, glm, medium — an earlier version raised on ``None`` here,
    contradicting this very docstring and turning any base-side read fault
    into a hard infra exit that blocks every PR touching that path).

    HEAD is guarded against a cross-spec-path ``(fr_id, ac_id)`` collision,
    same pattern and same reason as ``_keystone_ac_digest.ac_change_set``'s
    own ``head_minted_from`` guard (Stage-2 code review, medium): plain
    ``dict.update`` across spec paths is last-write-wins, so a second path
    re-anchoring an already-unbound AC under its OLD digest would silently
    revert ``head_minted[key]``, making the digest read "unchanged" and
    silencing this hard-from-day-one arm on exactly the input it must not
    miss. Only HEAD is guarded, matching this module's own base/head
    asymmetry above.

    Ported from ``ac_change_set`` (doubt review, medium — found during
    build): a trivially-empty comparison must never look identical to
    "nothing changed". Warns when NEITHER manifest names a spec_path at all
    (the loop below never executes) and when spec_path(s) ARE named but
    NONE resolved to any content at either commit (a stale/mistyped
    ``spec_path``) — both null cases this arm shares with ``ac_change_set``,
    which earned its own two warnings the identical way.
    """
    warnings: list[str] = []
    head_minted: dict[tuple[str, str], str] = {}
    head_minted_from: dict[tuple[str, str], str] = {}
    base_minted: dict[tuple[str, str], str] = {}
    spec_text_was_read = False
    spec_paths = _spec_paths(head_manifest, base_manifest)
    if not spec_paths:
        warnings.append(
            "neither manifest names a spec_path for any requirement; binding_regressions is "
            "trivially empty because there is nothing to compare, not because nothing changed."
        )
    for rel_path in spec_paths:
        head_text = spec_text_at(project_root, head_sha, rel_path)
        if head_text is None:
            raise ReadError(f"could not read {rel_path} at the head commit")
        if head_text:
            spec_text_was_read = True
        h_minted, _ = ac_criteria_digests(head_text)
        for key in h_minted:
            prior = head_minted_from.setdefault(key, rel_path)
            if prior != rel_path:
                raise ReadError(
                    f"{key[0]}/{key[1]} is minted in both {prior!r} and {rel_path!r} at head -- "
                    "an AC id must anchor to exactly one spec path, never reused across documents."
                )
        head_minted.update(h_minted)

        base_text = spec_text_at(project_root, base_sha, rel_path)
        if base_text is None:
            warnings.append(
                f"{rel_path}: base commit's text could not be read; treating base as having "
                "no acceptance criteria there."
            )
            continue
        if base_text:
            spec_text_was_read = True
        try:
            b_minted, _ = ac_criteria_digests(base_text)
        except ReadError as exc:
            warnings.append(
                f"{rel_path}: base commit's AC markers could not be parsed ({exc}); treating "
                "base as having no acceptance criteria there."
            )
            b_minted = {}
        base_minted.update(b_minted)
    if spec_paths and not spec_text_was_read:
        warnings.append(
            f"{len(spec_paths)} spec_path(s) named ({', '.join(spec_paths)}) but none resolved "
            "to any content at either commit; binding_regressions is trivially empty because "
            "there is nothing to compare, not because nothing changed."
        )
    return head_minted, base_minted, warnings


def binding_regressions(
    head_minted: dict[tuple[str, str], str],
    base_minted: dict[tuple[str, str], str],
    head_manifest: dict,
    base_manifest: dict,
) -> set[tuple[str, str]]:
    """Every ``(fr_id, ac_id)`` whose criterion digest is UNCHANGED between
    base and head, that had >=1 link at base and has 0 links at head.

    Deliberately does not touch a ``changed``/``added``/``removed`` AC —
    those are P3.6's own ``binding_removed``/``unbound`` territory (a
    criterion whose TEXT changed already gets that check's greenness/removal
    walk); this arm exists precisely for the complement, the AC P3.6 cannot
    see because nothing about its text moved.

    **Skips a display-id collision, at EITHER commit (Stage-2 code review,
    found during the review cascade).** ``links_for`` deliberately POOLS link
    counts across every active node sharing a display id (its own docstring:
    "a real collision, fail-closed there") — so for a colliding ``fr_id`` the
    "0 links at head" this arm keys on can be an artifact of which node's
    tests happened to be pooled, not a real regression on THIS criterion.
    Arm 1 (``_ac_binding_state.read_binding_state``) already excludes any
    colliding ``fr_id`` from the orphan check entirely, with a warning
    naming it "absent from the orphan check (feeder b)" — that claim was
    FALSE for this arm until this guard existed, since this function never
    consulted ``collision_display_ids`` and could still fire a HARD,
    no-baseline finding for a collision-affected id. Checked against BOTH
    manifests (a collision introduced or resolved between base and head
    still taints the comparison either way), matching arm 1's own
    "any collision at all" caution.
    """
    collisions = collision_display_ids(head_manifest) | collision_display_ids(base_manifest)
    out: set[tuple[str, str]] = set()
    for key, head_digest in head_minted.items():
        if base_minted.get(key) != head_digest:
            continue  # not "unchanged" (absent at base, or a real edit)
        fr_id, ac_id = key
        if fr_id in collisions:
            continue
        if links_for(base_manifest, fr_id, ac_id) and not links_for(head_manifest, fr_id, ac_id):
            out.add(key)
    return out


__all__ = ["ReadError", "binding_regressions", "head_and_base_minted"]
