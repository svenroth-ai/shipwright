"""S0: verify that a declared FR id names a requirement that actually exists.

The FR-gate (``record_event._fr_or_change_type_gate_error``) asks *"is this
change classified?"* and is satisfied by a non-empty list. It never asks whether
the ids in that list denote anything, so ``--affected-frs FR-99.99`` passed;
existence was checked only by detective D2 — MEDIUM, non-blocking, post-merge,
behind a ``spec_updated`` watermark. That is why dangling references exist in the
repo today.

Extracted into its own module rather than grown onto ``record_event`` /
``finalize_iterate``: both are already over the 300-LOC limit
(``shipwright_bloat_baseline.json``), so adding here would ratchet them further.
This cluster is cohesive on its own — collect, judge, report — and both write
paths import it, which also guarantees they can never drift apart.

The rule itself (:func:`lib.fr_classification.unknown_fr_ids`) stays in
``fr_classification``: that module is deliberately stdlib-only so the compliance
plugin can load it pollution-free, and the predicate is pure. Everything here
touches the filesystem, so it lives on this side of that line.
"""

from __future__ import annotations

import sys
from pathlib import Path

from lib.fr_classification import (
    CHANGE_TYPE_VALUES as _CHANGE_TYPE_VALUES,
    NONE_REASON_MAX_LEN as _NONE_REASON_MAX_LEN,
    is_behavior_affecting as _is_behavior_affecting,
    is_non_empty_fr_list as _is_non_empty_fr_list,
    is_valid_none_reason as _is_valid_none_reason,
    unknown_fr_ids,
)

#: Canonical planning root, kept as one full literal rather than split into path
#: segments: the artifact-path-canon lint matches the canonical string, and a
#: tuple of parts reads to it as a bare legacy reference.
_PLANNING = ".shipwright/planning"


def collect_known_fr_ids(project_root) -> tuple[frozenset[str], bool]:
    """Return ``(known FR ids, specs_found)``.

    ``specs_found`` distinguishes the two cases the collector alone cannot:
    ``collect_requirements_from_planning`` returns ``[]`` both when there is no
    planning directory AND when the specs there parse to zero requirements. The
    gate must treat those differently — the first is unverifiable, the second is
    the blind-scanner case — so presence is probed separately.

    Never raises. A collector failure degrades to "unverifiable" rather than
    blocking a write: this is a correctness check, not an availability dependency.
    """
    try:
        from lib.drift_parsers import collect_requirements_from_planning
        from lib.planning_discovery import iter_spec_files
    except Exception:
        return frozenset(), False

    try:
        planning = Path(project_root) / _PLANNING
        # require="is_file" (not the majority's "exists") is this call site's own
        # divergence: a *directory* named spec.md does not count as a spec here.
        # sort=False keeps raw iterdir order, and the generator still
        # short-circuits on the first hit exactly as the old ``any()`` did.
        specs_found = next(
            iter_spec_files(planning, sort=False, require="is_file"), None
        ) is not None
        if not specs_found:
            return frozenset(), False
        ids = {
            fr.id.strip()
            for fr in collect_requirements_from_planning(project_root)
            if getattr(fr, "id", None)
        }
        return frozenset(ids), True
    except Exception:
        return frozenset(), False


def existence_gate_error(event, known_fr_ids, *, specs_found: bool) -> dict | None:
    """Error dict when the event declares an FR id absent from ``known_fr_ids``.

    Kept separate from the classification gate: the two ask different questions,
    fail with different remedies, and BP-1's behaviour-affecting rule must stay
    verifiably untouched.

    ``new_frs`` is validated as strictly as ``affected_frs``. By F5b the spec edit
    has already happened during build, so a minted row must be on disk; if it is
    not, the iterate minted a requirement that exists only in the event log —
    precisely the drift this closes.

    **Graduated, so a gate can never brick a repo that cannot satisfy it:**
    ``specs_found=False`` (nothing to check against) and an empty
    ``known_fr_ids`` (specs parse to nothing) both ALLOW — the caller warns for
    the second. Only an id outside a non-empty known set is a hard failure.
    Fail-open on *unavailable* is deliberately not fail-open on *unknown*.
    """
    if not isinstance(event, dict):
        return None
    if event.get("type") != "work_completed" or event.get("source") != "iterate":
        return None
    if not specs_found or not known_fr_ids:
        return None

    declared: list = []
    for key in ("affected_frs", "new_frs"):
        value = event.get(key)
        if isinstance(value, list):
            declared.extend(value)

    unknown = unknown_fr_ids(declared, known_fr_ids)
    if not unknown:
        return None

    return {
        "error": "fr_gate_unknown_fr",
        "detail": (
            f"declared FR id(s) exist in no spec: {', '.join(unknown)}. "
            "Every --affected-frs/--new-frs entry must name a requirement row "
            "under .shipwright/planning/<split>/spec.md. Add the row first (or "
            "fix the typo) — an id that names nothing cannot be traced. "
            "See SKILL.md step F4 (FR capture)."
        ),
    }


def check_fr_existence(event, project_root, caller: str) -> dict | None:
    """Collect, warn on the blind-scanner case, and judge. The whole flow.

    Both write paths call exactly this, so the CLI and the F5b worktree path
    cannot drift — the same failure that ADR-059 had to close for the
    classification gate.
    """
    known_fr_ids, specs_found = collect_known_fr_ids(project_root)
    if specs_found and not known_fr_ids:
        # Allowed (a legitimately empty project must not be blocked) but never
        # silent — silence here reads as "nothing to audit".
        print(
            f"[{caller}] WARNING: specs found under .shipwright/planning/ but "
            "zero requirements parsed — FR existence is NOT being verified.",
            file=sys.stderr,
        )
    return existence_gate_error(event, known_fr_ids, specs_found=specs_found)


def run_fr_gates(event, project_root, caller: str) -> dict | None:
    """Both FR gates, in order: is the change classified, then do its ids exist.

    One entry point so a write path cannot wire up one gate and forget the other
    — the exact bypass ADR-059 had to close for the classification gate, which is
    why the existence gate is never offered separately to callers.
    """
    return (
        fr_or_change_type_gate_error(event)
        or check_fr_existence(event, project_root, caller)
    )


def fr_or_change_type_gate_error(event) -> dict | None:
    """Iterate C.1 (ADR-059) FR-gate. Hard-enforce forward-only.

    Every ``work_completed`` event with ``source == "iterate"`` MUST
    record either:

    - ``affected_frs`` non-empty list (or ``new_frs`` non-empty list
      — both forms tie the iterate to one or more FRs), OR
    - ``change_type`` ∈ ``{docs, tooling, compliance, infra}`` AND
      ``none_reason`` is a valid one-line justification (see
      ``_is_valid_none_reason``).

    BP-1 (campaign 2026-06-27) adds one rule: a **behavior-affecting**
    change (``spec_impact`` ∈ ``{add, modify, remove}``) MUST link an FR
    — the no-FR ``change_type`` branch is reserved for behavior-preserving
    changes. Unlike the CLI-only, intent-gated ``_spec_impact_gate_error``,
    this rule runs at finalize too (F5b parity) and is intent-independent.

    Additional consistency check: if ``change_type`` is present at all
    (even alongside valid FRs) it must be a recognized value — a malformed
    value is invalid input regardless of FR presence.

    Hard-rejects otherwise (error dict; ``main`` exits 1, writes nothing).
    Defensive ``.get()`` lookups mean a directly-constructed event dict
    missing ``type``/``source`` cleanly bypasses rather than crashing, and
    pre-gate events still parse (``change_type``/``none_reason`` = None).

    Build events (``source != "iterate"``) and non-work_completed events
    bypass entirely; Phase 0 pre-classified every existing iterate event so
    this hard-enforcement is risk-free.

    Scope: the gate runs at the CLI boundary (``record_event.main``)
    AND, since iterate-2026-06-05-fr-linkage-lifecycle, inside
    ``finalize_iterate._record_event`` (the worktree F5b / Stop-hook
    write-path), which calls this same function before its
    ``append_event`` — that bypass is now closed (ADR-059 parity). The
    spec-impact gate (``_spec_impact_gate_error``) stays CLI-only.

    Origin: iterate-2026-05-21-c1-fr-gate-finalize.
    """
    if not isinstance(event, dict):
        return None
    if event.get("type") != "work_completed":
        return None
    if event.get("source") != "iterate":
        return None

    change_type = event.get("change_type")
    none_reason = event.get("none_reason")
    has_frs = (
        _is_non_empty_fr_list(event.get("affected_frs"))
        or _is_non_empty_fr_list(event.get("new_frs"))
    )

    # BP-1 (campaign 2026-06-27): a behavior-affecting change (spec_impact ∈
    # add/modify/remove) MUST link an FR — the no-FR change_type branch is not
    # available to it. Closes two holes the CLI-only, intent-gated
    # _spec_impact_gate_error left open: this runs at finalize too (F5b parity)
    # AND is intent-independent (catches BUG + intent-less events). Without it a
    # behavior change could dodge FR-linkage by self-labeling "tooling", which
    # would also starve BP-2's per-FR reconciliation.
    if _is_behavior_affecting(event.get("spec_impact")) and not has_frs:
        return {
            "error": "fr_gate_behavior_affecting_requires_fr",
            "detail": (
                f"spec_impact={event.get('spec_impact')!r} is behavior-"
                "affecting but no --affected-frs/--new-frs was recorded. A "
                "behavior-affecting change must link the FR(s) it touches; the "
                "no-FR change_type branch is only for behavior-preserving "
                "(spec_impact none) changes. See SKILL.md step F4."
            ),
        }

    # Defense in depth: if change_type is present at all, the FULL
    # pair must be valid — both a recognized value AND a non-empty
    # one-line none_reason. Reviewer-flagged Gemini-M12 (iterate review)
    # + Gemini-M1 (code review): if the operator bothered to classify
    # via change_type, the metadata must be internally consistent. FRs
    # being present too is not a "free pass" to skip the reason.
    if change_type is not None:
        if change_type not in _CHANGE_TYPE_VALUES:
            return {
                "error": "fr_gate_unclassified",
                "detail": (
                    f"change_type={change_type!r} is not one of "
                    f"{list(_CHANGE_TYPE_VALUES)}. See SKILL.md step F4."
                ),
            }
        if not _is_valid_none_reason(none_reason):
            return {
                "error": "fr_gate_unclassified",
                "detail": (
                    "change_type is set but none_reason is missing or "
                    "malformed (require a non-empty single-line string, "
                    f"max {_NONE_REASON_MAX_LEN} chars, no control chars "
                    "except tab). See SKILL.md step F4."
                ),
            }
        # Pair is valid — the change_type path provides classification.
        return None

    # No change_type → must classify via FRs.
    if has_frs:
        return None

    return {
        "error": "fr_gate_unclassified",
        "detail": (
            "An iterate work_completed event must record either "
            "--affected-frs (or --new-frs) with at least one FR, OR "
            "--change-type ∈ {docs, tooling, compliance, infra} together "
            "with --none-reason '<one-line justification, max "
            f"{_NONE_REASON_MAX_LEN} chars, no newlines>'. "
            "See SKILL.md step F4 (FR capture)."
        ),
    }
