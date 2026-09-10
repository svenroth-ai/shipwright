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

===============  ===============  ====================================
``base_links``   ``head_links``   outcome
===============  ===============  ====================================
>= 1             **0**            ``binding_removed`` (HARD)
0                0                ``unbound`` (report-only)
0                >= 1             the greenness walk
>= 1             >= 1             the greenness walk
===============  ===============  ====================================

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

class EmptyLinkWalk(RuntimeError):
    """The greenness walk was entered with zero links — a programming error,
    never a pass. Every caller is gated on ``head_links >= 1``, so reaching this
    is a bug in the gate, not a finding about the repo."""


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


def _links_for(manifest: dict, fr_id: str, ac_id: str) -> list[dict]:
    """Every link bound to ``(fr_id, ac_id)``, flattened across layers.

    ``[]`` when ANY level is absent (no requirement with that display id, no
    ``acs`` node — e.g. a v3-era manifest — no such AC, or an empty ``tests``
    map). The count, never the node's presence, is what every caller keys on.
    Looks the FR up by its DISPLAY id (``node["id"]``), not the manifest's
    namespaced top-level key: the change set comes from spec.md, which knows only
    display ids.

    **ACTIVE nodes only** — no reviewer asked for this, found during build (NOT
    the same as the separate glm-low finding at §7 about retiring an FR while
    editing its criterion). This used to pool every node carrying the id,
    including RETIRED ones, while ``_keystone_layer_gap`` restricted itself to
    ``_active_nodes`` — an asymmetry that was fail-OPEN, not fail-closed as its
    docstring claimed: a retired duplicate silently ADDS to the head count,
    turning a `base >= 1, head 0` ``binding_removed`` into an ordinary greenness
    walk. Two active nodes sharing a display id still pool (a real collision,
    fail-closed there); ``_keystone_layer_gap`` routes that ADVISORY like its
    siblings.
    """
    out: list[dict] = []
    for node in (manifest.get("requirements") or {}).values():
        if not isinstance(node, dict) or node.get("id") != fr_id:
            continue
        if node.get("status") != "active":
            continue
        ac_node = (node.get("acs") or {}).get(ac_id)
        if not isinstance(ac_node, dict):
            continue
        for links in (ac_node.get("tests") or {}).values():
            if isinstance(links, list):
                out.extend(x for x in links if isinstance(x, dict))
    return out


def _walk_links(links: list[dict], fr_id: str, ac_id: str) -> list[Finding]:
    """One HARD finding per link that is not executed-passing. ``[]`` = all green.

    Raises :class:`EmptyLinkWalk` on empty ``links``. The three non-green
    outcomes stay DISTINCT because a bare "not green" cannot tell an operator
    what to do: a failing test, a skipped one, and one this run never executed
    have three different remedies.
    """
    if not links:
        raise EmptyLinkWalk(
            f"{fr_id}/{ac_id}: the greenness walk was entered with zero links -- "
            "all() over an empty set is vacuously True, which would report a "
            "vanished binding as green. Callers must gate on head_links >= 1."
        )
    findings: list[Finding] = []
    for link in links:
        test_id = str(link.get("id") or "<unknown test>")
        status = link.get("status")
        executed = link.get("executed")
        if status == "enabled" and executed == "pass":
            continue
        # STATUS FIRST -- no reviewer asked for this, found during build (same
        # honesty rule as deviation 3). A link that is `disabled` AND
        # `executed: fail` used to report `failed` ("fix the code"), but a
        # disabled test's `executed` is stale by construction; the actionable
        # fact is that it is disabled. Operator-facing, so pinned by a test.
        if status != "enabled":
            findings.append(Finding(
                SKIPPED, fr_id, ac_id,
                f"{test_id} is {status!r}, not 'enabled' -- a green-but-skipped test does not "
                "satisfy the gate.",
                "hard",
            ))
        elif executed == "fail":
            findings.append(Finding(
                FAILED, fr_id, ac_id,
                f"{test_id} FAILED in this run. Fix the code, or update the test as the "
                "TDD expression of the new acceptance criterion -- never weaken its assertion.",
                "hard",
            ))
        else:
            findings.append(Finding(
                NOT_SELECTED, fr_id, ac_id,
                f"{test_id} was not executed by this run (executed={executed!r}). This AC's "
                "binding names a test CI did not run: retag it to a test CI runs, or fix "
                "evidence staging.",
                "hard",
            ))
    return findings


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
