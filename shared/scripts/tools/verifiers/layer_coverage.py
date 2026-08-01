"""The two enforcing F11 traceability gates (Spec §11 R2/R3, gaps G3/G4/G7/G8).

* ``removal_coverage`` — a removed FR's base-linked tests must be deleted or retargeted to
  a live FR; a bare ``@FR`` tag removal (the stale test escapes into ``untagged_tests``)
  or a still-standing tag → dead FR is a HARD finding.
* ``cross_layer_coverage`` — a behaviour-changed FR (spec/AC/FR delta, NOT source-file
  inference) must have an executed-passing tagged test at every ``required_layer`` (R1); a
  pure refactor triggers nothing; an undeterminable FR mapping WARNs, never silently passes.
  Behaviour change is read from the FR row AND from the requirement's own acceptance
  criteria (``_layer_coverage_ac``) — folding a criterion into an existing requirement is
  the authoring pattern ``shared/fr-authoring.md`` §3 recommends, and the row alone could
  never see it.

Both are RECOMPUTED from git + freshly-regenerated base/head manifests
(``_layer_coverage_regen``), never from a self-reported ledger or the committed artifact —
the same non-dodgeable posture as ``check_integration_coverage``.

FAIL-CLOSED on infra failure, at **every** complexity: a missing ``--commit``, an
unresolvable base ref, a git subprocess failure/timeout, a failed regeneration / collector
load, or a verifier exception is an **ERROR (block)**, never a green SKIP — a gate that
cannot run on an iterate it is meant to enforce must FAIL. Only a genuine **non-git
context** stands the gate down, and that is an inapplicable context rather than a failure.

*This supersedes MUST-FIX 1's original "SKIPs below medium" carve-out
(iterate-2026-08-01-coverage-gate-recompute-order).* ``removal_coverage`` documented itself
as running at all complexities (SHOULD-FIX 6 — a removal is never trivial) while every
infra path below medium returned a green SKIP: it ran, then declined to answer, in the
colour of a pass. Deciding that on the run's own self-reported complexity label was the
defect. ``cross_layer_coverage`` still runs at **medium+** only — that is a deliberate cost
decision about SCOPE (regenerating base/head manifests with execution evidence is
expensive), not an infra carve-out, and its scope gate returns before any infra path is
reachable.

FAIL-CLOSED reasoning (why these cannot false-green):
* removal: the head manifest is regenerated from the HEAD checkout, so a stale test that
  merely dropped its tag lands in ``untagged_tests`` (HARD) and one still tagged to the
  dead FR lands in ``orphans`` (HARD) — there is no state in which a live spec/removed FR
  keeps a passing E2E test and the gate stays green.
* cross-layer: coverage ``ok`` requires ``enabled`` + ``executed=pass`` in THIS run's
  provenance-verified evidence, so a skipped/never-run test reads MISSING, never a pass.
And why they cannot false-RED: a pure refactor leaves base==head specs (no changed FR); a
legacy-provenance or collision (un-namespaced fan-out) gap is ADVISORY, never HARD.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS_ROOT = Path(__file__).resolve().parents[2]
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from lib.iterate_entry import find_entry_by_run_id  # noqa: E402

from ._layer_coverage_ac import changed_criteria_ids  # noqa: E402
from ._layer_coverage_core import CrossLayerVerdict, evaluate_cross_layer  # noqa: E402
from ._layer_coverage_regen import _merge_base, regenerate_base_head  # noqa: E402
from ._layer_coverage_removal import RemovalVerdict, evaluate_removal  # noqa: E402
from .common import CheckResult, Severity  # noqa: E402
from .git_helpers import git_context  # noqa: E402

_REMOVAL_NAME = "removal coverage (removed FR → orphaned tests)"
_CROSS_LAYER_NAME = "cross-layer coverage (behaviour change → executed-passing layers)"


def _complexity(project_root: Path, run_id: str) -> str:
    entry = find_entry_by_run_id(project_root, run_id)
    return str((entry or {}).get("complexity", "")).lower()


def _skip(name: str, detail: str) -> CheckResult:
    return CheckResult(name, True, detail, severity=Severity.SKIPPED.value)


def _is_enforcing(complexity: str) -> bool:
    return complexity in ("medium", "large")


def _git_precheck(name: str, project_root: Path, complexity: str) -> CheckResult | None:
    """SKIP on a clean non-git context; ERROR on a git subprocess failure/timeout;
    ``None`` to proceed when it is a real work-tree.

    The tri-state probe itself is ``git_helpers.git_context`` — it moved there so
    ``integration_coverage`` could share one classification rather than growing a
    second copy (iterate-2026-08-01-coverage-gate-recompute-order). Tests that
    stub the git layer for this path must patch ``git_helpers._run_git``.
    """
    ctx = git_context(project_root)
    if ctx == "not_git":
        return _skip(name, "skipped (not a git work tree — git-diff enforcement N/A)")
    # Proceed only on an explicit work_tree — anything unrecognised must refuse, not
    # fall through to the enforcing path as if the tree were healthy.
    if ctx != "work_tree":
        return _infra_result(
            name, complexity,
            "git could not answer whether this is a work tree (wedged index.lock, stalled FS, "
            "`safe.directory` refusal, or git missing) — run "
            "`git -C <project> rev-parse --is-inside-work-tree` for git's own message",
        )
    return None


def _infra_result(name: str, complexity: str, detail: str) -> CheckResult:
    """A regen infra FAILURE on a git repo (no commit / unresolvable base / collector or
    archive failure / exception). Fail-CLOSED at EVERY complexity — ERROR, block.

    SUPERSEDES MUST-FIX 1's "SKIP below medium"
    (iterate-2026-08-01-coverage-gate-recompute-order). ``check_removal_coverage``
    documents itself as running at all complexities because a removal is never
    trivial, yet every infra path below medium returned a green SKIP: it ran, then
    declined to answer, in the colour of a pass. "Runs" and "can conclude anything"
    had drifted apart. A gate that cannot run on an iterate it is meant to enforce
    must FAIL, and the recorded complexity — a self-reported label — is the wrong
    thing to decide that on.

    ``complexity`` stays in the signature and in the message: it is diagnostic, so
    an operator reading a blocked trivial run can see what the run called itself.
    Distinct from a non-git project, which is an inapplicable context rather than a
    failure — that still SKIPs, via :func:`_git_precheck`, at every complexity.
    """
    return CheckResult(
        name, False,
        f"cannot enforce (complexity={complexity or 'unknown'}): {detail}",
    )


def _removal_suggest(display: str) -> str:
    return (
        f"/shipwright-iterate --type change \"delete or retarget the tests tagged "
        f"@{display} — a removed FR's base-linked tests must not stay green\""
    )


def check_removal_coverage(project_root: Path, run_id: str, commit_hash: str = "") -> CheckResult:
    """Removal → orphan gate. Runs at ALL complexities (a removal is never trivial, SHOULD-FIX
    6) — and now CONCLUDES at all of them: an infra gap is an ERROR at every complexity, not a
    green SKIP below medium (iterate-2026-08-01-coverage-gate-recompute-order, superseding
    MUST-FIX 1). Regenerates base+head (R3); a real un-retired test is a HARD FAIL at any
    complexity; only a non-git context SKIPs."""
    name = _REMOVAL_NAME
    complexity = _complexity(project_root, run_id)
    # Establish the git CONTEXT before asking for a commit. Ordering is
    # load-bearing now that an infra gap ERRORs at every complexity: with the
    # missing-commit branch first, a non-git project would hard-fail on a commit it
    # was never going to have — a false-red introduced by the fail-closed change
    # itself (iterate-2026-08-01-coverage-gate-recompute-order).
    precheck = _git_precheck(name, project_root, complexity)
    if precheck is not None:
        return precheck
    if not commit_hash:
        return _infra_result(name, complexity, "no --commit supplied")
    try:
        regen = regenerate_base_head(project_root, commit_hash, with_evidence=False)
        if regen is None:
            return _infra_result(name, complexity, "git unavailable / no base ref / collector unavailable")
        base, head, renames = regen
        verdict = evaluate_removal(base, head, renames)
    except Exception as exc:  # noqa: BLE001 — surface as ERROR at every complexity, never a silent crash
        return _infra_result(name, complexity, f"regeneration error: {type(exc).__name__}")
    return _removal_result(name, verdict)


def _removal_result(name: str, verdict: RemovalVerdict) -> CheckResult:
    if not verdict.removed_frs:
        return CheckResult(name, True, "no FR moved out of active (## Removed Requirements)")
    if verdict.any_fail:
        evidence = [f"{disp}: {test} — {reason}" for disp, test, reason in verdict.hard[:6]]
        detail = (
            f"{len(verdict.hard)} base-linked test(s) of {len(verdict.removed_frs)} removed "
            f"FR(s) were neither deleted nor retargeted: " + "; ".join(evidence)
            + f"  →  {_removal_suggest(verdict.hard[0][0])}"
        )
        return CheckResult(name, False, detail)
    if verdict.advisory:
        # Not a clean green: a collision-id test tagged to the removed FR is structurally
        # ambiguous (may cover another namespace's same-id FR) → surface as WARN, never a
        # silent pass, but never a HARD block either (that would be a false-red until a
        # namespaced tag form exists — TT2 doubt #3 deferral).
        ev = [f"{disp}: {test} — {reason}" for disp, test, reason in verdict.advisory[:4]]
        return CheckResult(
            name, False,
            f"{len(verdict.removed_frs)} removed FR(s); {len(verdict.advisory)} base-linked "
            f"test(s) are collision-ambiguous (deferred to a namespaced tag): " + "; ".join(ev),
            severity=Severity.WARNING.value, strict_exempt=True,
        )
    return CheckResult(
        name, True,
        f"{len(verdict.removed_frs)} removed FR(s); all base-linked tests deleted/retargeted",
    )


def check_cross_layer_coverage(project_root: Path, run_id: str, commit_hash: str = "") -> CheckResult:
    """Change → cross-layer gate. Regenerates base+head with THIS run's execution evidence
    and requires each behaviour-changed FR to be executed-passing at every required layer."""
    name = _CROSS_LAYER_NAME
    complexity = _complexity(project_root, run_id)
    if not _is_enforcing(complexity):
        return _skip(name, f"skipped (complexity={complexity or 'unknown'})")
    if not commit_hash:
        return _infra_result(name, complexity, "no --commit supplied")
    precheck = _git_precheck(name, project_root, complexity)
    if precheck is not None:
        return precheck
    try:
        regen = regenerate_base_head(
            project_root, commit_hash, with_evidence=True, run_id=run_id,
        )
        if regen is None:
            return _infra_result(name, complexity, "git unavailable / no base ref / collector unavailable")
        base, head, _renames = regen
        # Behaviour change is the union of a changed FR ROW and changed ACCEPTANCE
        # CRITERIA. Folding a criterion into an existing requirement — the pattern
        # fr-authoring.md §3 recommends — leaves the row identical, so the row alone
        # made the encouraged case permanently undeterminable. The criteria are read
        # from the two spec checkouts via `spec_path`; the manifest is not touched.
        ac_changed, ac_error = changed_criteria_ids(
            project_root, _merge_base(project_root, commit_hash), commit_hash, base, head,
        )
        if ac_error:
            # A spec that cannot be read is an infrastructure gap, NOT "no criteria
            # changed" — the latter would be a false green precisely when the gate
            # is least able to see.
            return _infra_result(name, complexity, ac_error)
        verdict = evaluate_cross_layer(base, head, ac_changed)
    except Exception as exc:  # noqa: BLE001 — surface as ERROR at medium+, never a silent crash
        return _infra_result(name, complexity, f"regeneration error: {type(exc).__name__}")
    return _cross_layer_result(name, verdict)


def _cross_layer_result(name: str, verdict: CrossLayerVerdict) -> CheckResult:
    if verdict.could_not_determine:
        return CheckResult(
            name, False,
            "the spec changed, but neither any FR row nor any requirement's acceptance "
            "criteria changed — so the edit landed outside every requirement (an abstract, "
            "a quality requirement, prose between sections), or no active FR parsed. "
            "could-not-determine: a visible WARN for a human to adjudicate, never a silent pass",
            severity=Severity.WARNING.value, strict_exempt=True,
        )
    if not verdict.changed_keys:
        return CheckResult(name, True, "no behaviour-changed FR (no spec/AC/FR delta)")
    if verdict.any_fail:
        gaps = [f"{g.display} [{g.layer}] ({g.priority}) — {g.reason}" for g in verdict.hard[:6]]
        detail = (
            f"{len(verdict.hard)} required layer(s) of {len(verdict.changed_keys)} "
            f"behaviour-changed FR(s) have no executed-passing test: " + "; ".join(gaps)
            + "  →  /shipwright-iterate --type change \"add an executed-passing test at "
            "the missing layer(s) — a green-but-skipped test does not satisfy the gate\""
        )
        return CheckResult(name, False, detail)
    if verdict.advisory:
        # A behaviour-changed FR with a legacy-provenance or collision required layer that
        # has no executed-passing test is NOT a clean pass (external-review MUST-FIX): it
        # surfaces as WARN so the gap is visible, but stays non-blocking — a HARD block on a
        # heuristic (inferred/defaulted) or structurally-ambiguous (collision) layer would be
        # a false-red on the pre-rollout monorepo. Explicit gaps already went HARD above.
        gaps = [f"{g.display} [{g.layer}] ({g.source}) — {g.reason}" for g in verdict.advisory[:6]]
        return CheckResult(
            name, False,
            f"{len(verdict.advisory)} required layer(s) of behaviour-changed FR(s) lack an "
            f"executed-passing test but are legacy/collision (advisory, not blocking): "
            + "; ".join(gaps),
            severity=Severity.WARNING.value, strict_exempt=True,
        )
    return CheckResult(
        name, True,
        f"{len(verdict.changed_keys)} behaviour-changed FR(s) covered+passing at every required layer",
    )


__all__ = ["check_removal_coverage", "check_cross_layer_coverage"]
