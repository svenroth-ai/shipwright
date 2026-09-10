"""Pure evaluator for THE KEYSTONE GATE (P3.6, campaign req3-04c-ac-identity-wave2 —
``.shipwright/planning/iterate/2026-09-09-p3-6-keystone-gate.md``).

The campaign SPEC's one sentence (§1.4): *a behaviour-changing PR must not merge
without (a) naming the changed ACs and (b) re-running the tests bound to those
ACs in CI — green.*

No git, no filesystem, no subprocess: this module takes an already-computed
:class:`AcChangeSet` (``_keystone_ac_digest``) plus the two already-parsed
manifests and returns a verdict. Same split the sibling gates use
(``_layer_coverage_core`` is pure; ``layer_coverage`` shapes the result), and the
reason it is unit-testable against fixtures without a repo.

**ONE vocabulary: LINK COUNTS, never node presence** (design §5.3). Every outcome
for a ``changed`` AC derives from exactly two numbers:

===============  =========================  ====================================
``base_links``   ``head_links``             outcome
===============  =========================  ====================================
>= 1             **0**                      ``binding_removed`` (HARD)
>= 1             **< base_links, >= 1**     ``binding_removed`` (HARD -- a reduction, not
                                             just a removal; Stage-3 doubt review, high)
0                0                          ``unbound`` (report-only)
0                >= 1                       the greenness walk
>= 1             ``>= base_links``          the greenness walk
===============  =========================  ====================================

A node-presence phrasing of the same rule disagrees on exactly one input — base
has links, head has an ``acs[ac_id]`` node whose ``tests`` map is empty — where
it falls through to the greenness walk, whose ``all()`` over an empty set is
**vacuously True**: exit 0 for an AC whose binding just vanished, which is the
dodge this gate exists to close. :func:`_walk_links` therefore *raises* on an
empty link set rather than returning "all green".

**Eligibility is not redefined here.** A link counts iff ``status == "enabled"
and executed == "pass"`` — the contract ``_test_links_requirements._cov_status``,
``evaluate_cross_layer`` and ``_highest_ok_layer`` already share. What differs is
the QUANTIFIER: ``_cov_status`` is ``any(...)``, so one green link makes a layer
``"ok"`` even when a sibling failed, while D10 requires **all** bound tests. So
this module never reads ``coverage[layer]`` — it walks the links and requires all
of them. Reusing ``_cov_status`` would ship a gate one green sibling satisfies.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ._keystone_finding import (  # noqa: F401  (re-exported: one import site for callers)
    BINDING_REMOVED,
    FAILED,
    LAYER_GAP,
    NEW_FR_NO_CRITERIA,
    NOT_SELECTED,
    READER_DIVERGENCE,
    SKIPPED,
    UNBOUND,
    UNMINTED_CHANGED,
    Finding,
)
from ._keystone_layer_gap import layer_gap
from ._keystone_links import (  # noqa: F401  (re-exported: one import site for callers)
    EmptyLinkWalk,
    links_for as _links_for,
    walk_links as _walk_links,
)


@dataclass
class KeystoneVerdict:
    hard: list[Finding] = field(default_factory=list)
    advisory: list[Finding] = field(default_factory=list)
    unbound: list[tuple[str, str]] = field(default_factory=list)   # report-only -> p3.7
    #: ACs deleted from the spec that HAD a binding at base — report-only, and the
    #: single-PR sibling of the two-PR unbind sequence. See the paragraph at the
    #: bottom of :func:`evaluate_keystone` for why it does not block here.
    removed_with_bindings: list[tuple[str, str]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def any_hard(self) -> bool:
        return bool(self.hard)


def evaluate_keystone(change_set, head_manifest: dict, base_manifest: dict) -> KeystoneVerdict:
    """The gate's whole decision, from an already-computed change set.

    ``change_set`` is a ``_keystone_ac_digest.AcChangeSet``; it is duck-typed
    here (attribute access only) so this module stays import-light and testable
    with a simple stub.
    """
    verdict = KeystoneVerdict(warnings=list(getattr(change_set, "warnings", []) or []))

    # --- AC-1 arm 1: a criterion this PR changed or added that carries no [ACnn].
    for fr_id, text in change_set.unminted_changed:
        verdict.hard.append(Finding(
            UNMINTED_CHANGED, fr_id, "",
            f"{fr_id}: this PR changes or adds an acceptance criterion carrying no [ACnn] marker, "
            f"so the framework cannot name it: {text[:160]!r}. Mint it -- "
            "uv run shared/scripts/tools/mint_ac_ids.py --spec-file <spec.md> "
            "--registry-file shipwright_ac_registry.json --write -- and commit the rewritten "
            "spec AND the updated registry in this same PR.",
            "hard",
        ))

    # --- The reader-divergence guard, scoped to FRs this PR touched. Evaluated
    # BEFORE arm 2 and suppressing it for the same FR (design 5.1/5.2): both fire
    # on a brand-new FR whose bullets follow an intro sentence, and arm 2's
    # remedy ("state a criterion") is the WRONG one there -- the criteria exist,
    # this reader just cannot see them.
    diverged = set()
    for fr_id in change_set.reader_divergence:
        diverged.add(fr_id)
        verdict.hard.append(Finding(
            READER_DIVERGENCE, fr_id, "",
            f"{fr_id}: its acceptance criteria changed in this PR, but they are not a contiguous "
            "leading bullet run under its heading, so ac_identity cannot see them at all. Move the "
            "introductory note below the bullets, or mint the criteria.",
            "hard",
        ))

    # --- AC-1 arm 2: a NEW active FR at head that states no minted criterion.
    for fr_id in change_set.new_frs_without_criteria:
        if fr_id in diverged:
            continue
        verdict.hard.append(Finding(
            NEW_FR_NO_CRITERIA, fr_id, "",
            f"{fr_id} is new in this PR and states no acceptance criterion. A new requirement must "
            "state at least one, then have it minted (mint_ac_ids.py --write).",
            "hard",
        ))

    # --- AC-2: every changed AC's bound tests, judged on LINK COUNTS only.
    for fr_id, ac_id in sorted(change_set.changed):
        base_links = _links_for(base_manifest, fr_id, ac_id)
        head_links = _links_for(head_manifest, fr_id, ac_id)
        if not head_links:
            if base_links:
                verdict.hard.append(Finding(
                    BINDING_REMOVED, fr_id, ac_id,
                    f"{fr_id}/{ac_id}: this PR changes the criterion AND removes its test binding "
                    f"({len(base_links)} link(s) at base, none at head). Restore the "
                    f'@pytest.mark.covers("{fr_id}/{ac_id}") tag, or justify its removal in review.',
                    "hard",
                ))
            else:
                # Never existed on either side -> p3.7's anti-ratcheted feeder.
                verdict.unbound.append((fr_id, ac_id))
            continue
        # COUNTS, not just emptiness (found during build, Stage-3 doubt review,
        # high): dropping the @covers suffix from ONE of several links on a
        # fat AC used to be indistinguishable from an ordinary edit, because
        # only `head_links == []` was ever checked -- the exact remediable-in-
        # this-PR shape `binding_removed` exists to catch, just short of zero.
        if len(head_links) < len(base_links):
            # Named, not just counted (Stage-2 code review, low; found during
            # build): a set-difference over link ids tells the operator WHICH
            # `@covers` tag(s) vanished, rather than leaving them to diff two
            # manifests by hand to find out.
            base_ids = {str(link.get("id") or "<unknown test>") for link in base_links}
            head_ids = {str(link.get("id") or "<unknown test>") for link in head_links}
            missing = sorted(base_ids - head_ids)
            missing_desc = ", ".join(missing) if missing else "none identifiable by id"
            verdict.hard.append(Finding(
                BINDING_REMOVED, fr_id, ac_id,
                f"{fr_id}/{ac_id}: this PR changes the criterion AND reduces its test binding "
                f"({len(base_links)} link(s) at base, {len(head_links)} at head; missing: "
                f"{missing_desc}). Restore the removed "
                f'@pytest.mark.covers("{fr_id}/{ac_id}") tag(s), or justify the reduction '
                "in review.",
                "hard",
            ))
            continue
        for finding in _walk_links(head_links, fr_id, ac_id):
            verdict.hard.append(finding)
        gap = layer_gap(head_manifest, fr_id, ac_id, head_links)
        if gap is not None:
            # Explicit, not `getattr(verdict, gap.severity)`: routing a finding by
            # using its severity STRING as an attribute name silently turns any
            # future third severity into an AttributeError at gate time.
            (verdict.hard if gap.severity == "hard" else verdict.advisory).append(gap)

    # --- ADDED ACs: report-only WHEN UNBOUND, greenness-walked when they are not.
    #
    # DEVIATION 3 from the ratified design, whose four-step justification lives in
    # design §7's third-deviation bullet and §8's ruling row -- NOT repeated here.
    # In short: AC-2 says "a NAMED AC whose bound test did not run green blocks",
    # an added AC is named, and the design's only stated ground for exempting it
    # ("a new criterion has no binding") is an assumption that fails exactly when
    # the criterion arrives carrying a `@covers` tag.
    #
    # ATTRIBUTION, because an earlier version of this comment got it wrong and a
    # spec review caught it: NO REVIEWER ASKED FOR THIS -- it was found during
    # build. The code review's openai-high finding is the Track R / Q2 scope
    # objection that §12.1 REJECTS; the plan review's AC-id-rotation finding stays
    # "reported, not blocked" (the `removed_with_bindings` arm below).
    #
    # SCOPE -- greenness ONLY, deliberately narrower than the `changed` arm:
    # `layer_gap` is NOT called here. Layer BREADTH for a brand-new criterion is
    # coverage (p3.7's), and it is the arm that would false-red the moment p3.5
    # promotes an FR to `explicit`. `binding_removed` is likewise not evaluated --
    # an added AC has no base side to have been removed from, by construction.
    for fr_id, ac_id in sorted(change_set.added):
        head_links = _links_for(head_manifest, fr_id, ac_id)
        if not head_links:
            verdict.unbound.append((fr_id, ac_id))
            continue
        verdict.hard.extend(_walk_links(head_links, fr_id, ac_id))

    # --- REMOVED ACs that HAD a binding. Report-only, and deliberately so; the
    # reasoning is worth the paragraph because both external plan reviewers found
    # this from opposite directions and the disposition is a scope call, not a
    # dismissal.
    #
    # THE HOLE: `binding_removed` walks `changed` only, so deleting a criterion
    # outright -- or rotating its id, `[AC01] foo` -> `[AC55] foo TWICE`, which
    # reads as removed+added -- discards an AC-to-test obligation in ONE PR
    # without ever entering the `changed` set. That is strictly worse than the
    # two-PR unbind sequence 7 already discloses.
    #
    # WHY NOT BLOCK: there is no remediable predicate available here. Blocking on
    # "base had links" is UNFIXABLE INSIDE THE PR -- base is immutable, so an
    # author legitimately retiring a criterion AND its test still fails forever.
    # The predicate that IS remediable ("the criterion is gone but its @covers tag
    # survives, now pointing at nothing" -> remove or retarget the tag) is exactly
    # p3.7(b)'s orphan detector, hard from day one per SPEC 8 E2. Building a second
    # copy of it here is how two gates drift apart, which this campaign has already
    # paid for once. So: p3.6 makes the shape VISIBLE in every PR's JSON rather
    # than leaving it disclosed only in a design document, and p3.7(b) blocks it.
    for fr_id, ac_id in sorted(change_set.removed):
        if _links_for(base_manifest, fr_id, ac_id):
            verdict.removed_with_bindings.append((fr_id, ac_id))
    return verdict


__all__ = [
    "BINDING_REMOVED", "FAILED", "SKIPPED", "NOT_SELECTED", "UNBOUND", "LAYER_GAP",
    "UNMINTED_CHANGED", "NEW_FR_NO_CRITERIA", "READER_DIVERGENCE",
    "EmptyLinkWalk", "Finding", "KeystoneVerdict", "evaluate_keystone",
]
