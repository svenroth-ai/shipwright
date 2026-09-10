"""Reader-divergence and new-FR-without-criteria arms, split out of
``_keystone_ac_digest`` to buy back headroom at its 300-line limit after the
Stage-2 code-review fixes (Stage-2 code review, low; found during build).

Both arms are scoped to what THIS PR caused, never a repo-wide sweep -- see
each function's own docstring for why. Pure set/dict logic over values
``_keystone_ac_digest.ac_change_set`` has already computed; no git, no I/O.
"""

from __future__ import annotations

import hashlib

#: ``criteria_digests`` hashes the JOINED criteria text, so an FR with NO criteria
#: gets the sha256 of the empty string -- a perfectly non-empty *string*. Testing
#: that digest for truthiness would therefore call every criteria-less FR
#: "visible to the FR-level reader" and report a divergence for it.
_EMPTY_CRITERIA_DIGEST = hashlib.sha256(b"").hexdigest()


def resolve_reader_divergence(
    result, *, head_fr_digests: dict[str, str], head_active_frs: set[str],
    head_seen_frs: set[str], base_seen_frs: set[str], base_fr_digests: dict[str, str],
) -> None:
    """Populate ``result.reader_divergence`` (arm 1 — appends in place).

    Reader divergence, SCOPED to what THIS PR caused. An unscoped guard would
    red every later PR in the repo -- including docs-only ones -- from the day
    one FR acquires an introductory sentence. Arm (a) exists because ADDING an
    intro sentence changes NO criterion text, so the FR-level digest alone
    (single test, found insufficient at build time) is byte-identical across
    the very PR that creates the divergence -- without it the AC silently
    vanishes from this reader and the NEXT PR to edit it reads `added` rather
    than `changed`, i.e. never blocks on greenness (the two-step dodge).

    ACTIVE FRs only, like every sibling predicate in this gate (`_links_for`,
    `_keystone_layer_gap._fr_node`, `_active_display_ids`) -- dropped here by
    omission (found by a Stage-1 spec review). Unreachable today, but "latent
    today" is the reasoning round 3 rejected once already: a spec.md heading
    survives retirement, so a retired FR gaining an intro sentence would HARD-
    block a PR over a requirement the rest of the gate does not enforce.
    """
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


def resolve_new_frs_without_criteria(
    result, *, head_active_ids: set[str], base_active_ids: set[str],
    base_fr_digests: dict[str, str], head_minted: dict[tuple[str, str], str],
    spec_text_was_read: bool,
) -> None:
    """Populate ``result.new_frs_without_criteria`` (arm 2 — appends in place).

    Arm 2's input, stated as the set operation it is (external plan review, glm,
    low: round 3's `.get(fr)` finding was the same family -- an unstated set
    operation over two manifests is where the null case hides). "NEW active FR"
    == a DISPLAY id carried by an `active` requirement in the HEAD manifest and
    by no active requirement in the BASE one.

    ...which is why the empty base manifest SUPPRESSES the arm entirely. Under
    `base_manifest_absent` every head FR trivially satisfies "absent at base",
    so arm 2 would fire for every criteria-less FR in the repo at once -- a
    repo-wide false red in the one mode that already degrades, and the same
    blast-radius mistake round 3 fixed for the divergence guard. "New" is not
    answerable without a base to be new relative to, so it is not answered.

    ``spec_text_was_read`` -- True iff at least one named ``spec_path``
    yielded non-empty content at either commit -- gates the SAME suppression
    for a second, independent null case (Stage-2 code review, medium; found
    during build): neither
    manifest naming a `spec_path` -- or every named path resolving to no
    content at either commit (Stage-2 code review, low; found during build,
    round 6) -- means `base_fr_digests` and `head_minted` are empty NOT
    because the base genuinely has no criteria, but because no spec text was
    ever scanned. Without this guard, a base manifest that DOES carry active
    requirements makes every head-only active FR read as
    `new_frs_without_criteria` -- "states no acceptance criterion" asserted
    from a document nobody read, the exact blast-radius mistake this
    suppression already exists for one call up. Required, no default: the
    caller has already computed whether text was actually read, and a
    silently-safe default here would hide the day a second caller forgets to
    pass it.

    Same precedence as ``result.reader_divergence``: an FR already reported by
    arm 1 (`unminted_changed`) is NOT "states no acceptance criterion" -- it
    states one or more, unminted. Without this exclusion a brand-new FR
    authored with bullets but no `[ACnn]` markers fires BOTH arms, and arm 2's
    message then tells the operator to do something they already did (found by
    Stage-2 code review: the single most likely first real-world encounter with
    this gate is exactly this shape -- an FR hand-authored before running the
    minter).
    """
    if not spec_text_was_read:
        # `ac_change_set` has already emitted a warning explaining why the
        # change set is trivially empty -- the "no spec_path named" warning
        # for the first disjunct, or its sibling "named but resolved to no
        # content" warning for the second (Stage-1 spec review, round 19,
        # medium: this comment used to name only the first warning, which does
        # NOT fire in the second disjunct -- see the docstring above).
        return
    diverged = set(result.reader_divergence)
    unminted_frs = {fr for fr, _ in result.unminted_changed}
    if base_active_ids:
        for fr_id in sorted(head_active_ids - base_active_ids):
            if fr_id in diverged or fr_id in unminted_frs:
                continue
            # SPEC-derived (ruling Q1b): the manifest is regenerated at head
            # but read from the last COMMIT at base, and the two are known to
            # drift (the drift step is advisory, not a hard gate) -- found
            # during build, Stage-2 code review. An FR whose heading already
            # existed at base is not "new in this PR" even if a stale base
            # manifest never carried it.
            if fr_id in base_fr_digests:
                continue
            if not any(k[0] == fr_id for k in head_minted):
                result.new_frs_without_criteria.append(fr_id)
    elif head_active_ids:
        result.warnings.append(
            "the base manifest names no active requirement, so 'is this FR new?' is "
            "unanswerable; the new-FR-without-criteria arm is suppressed for this run."
        )


__all__ = ["resolve_reader_divergence", "resolve_new_frs_without_criteria"]
