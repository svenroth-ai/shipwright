"""The two enforcing F11 traceability gates (Spec §11 R2/R3, gaps G3/G4/G7/G8).

* ``removal_coverage`` — a removed FR's base-linked tests must be deleted or retargeted to
  a live FR; a bare ``@FR`` tag removal (the stale test escapes into ``untagged_tests``)
  or a still-standing tag → dead FR is a HARD finding.
* ``cross_layer_coverage`` — a behaviour-changed FR (spec/AC/FR delta, NOT source-file
  inference) must have an executed-passing tagged test at every ``required_layer`` (R1); a
  pure refactor triggers nothing; an undeterminable FR mapping WARNs, never silently passes.

Both are RECOMPUTED from git + freshly-regenerated base/head manifests
(``_layer_coverage_regen``), never from a self-reported ledger or the committed artifact —
the same non-dodgeable posture as ``check_integration_coverage``.

FAIL-CLOSED on infra failure (MUST-FIX 1): for a **medium/large** iterate, a missing
``--commit``, an unresolvable base ref, a failed regeneration / collector load, or a
verifier exception is an **ERROR (block)**, never a green SKIP — a gate that cannot run on
an iterate it is meant to enforce must FAIL. Only **below medium** does an infra gap SKIP.
``removal_coverage`` runs at **all** complexities (SHOULD-FIX 6 — a removal is never
trivial); ``cross_layer_coverage`` runs at **medium+** only.

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

from ._layer_coverage_core import CrossLayerVerdict, evaluate_cross_layer  # noqa: E402
from ._layer_coverage_regen import regenerate_base_head  # noqa: E402
from ._layer_coverage_removal import RemovalVerdict, evaluate_removal  # noqa: E402
from .common import CheckResult, Severity  # noqa: E402
from .git_helpers import _run_git  # noqa: E402

_REMOVAL_NAME = "removal coverage (removed FR → orphaned tests)"
_CROSS_LAYER_NAME = "cross-layer coverage (behaviour change → executed-passing layers)"


def _complexity(project_root: Path, run_id: str) -> str:
    entry = find_entry_by_run_id(project_root, run_id)
    return str((entry or {}).get("complexity", "")).lower()


def _skip(name: str, detail: str) -> CheckResult:
    return CheckResult(name, True, detail, severity=Severity.SKIPPED.value)


def _is_enforcing(complexity: str) -> bool:
    return complexity in ("medium", "large")


def _git_context(project_root: Path) -> str:
    """Tri-state git probe (coordinator FIX 1): ``work_tree`` | ``not_git`` | ``git_error``.

    A binary ``_git_available`` conflates "not a git repo" (an inapplicable context → SKIP)
    with a git SUBPROCESS failure/timeout on a real work-tree (a wedged index.lock / stalled
    FS / >10s stall → an infra failure that must fail-CLOSED at medium+). Only a DEFINITIVE
    non-git answer (rc 0 → not "true", or git ran and said "not a git repository") is
    ``not_git``; a synthesized failure (OSError/timeout → rc 1, empty stderr) or any other
    non-zero rc without that message is ``git_error``."""
    rc, out, err = _run_git(project_root, "rev-parse", "--is-inside-work-tree", timeout=10.0)
    if rc == 0:
        return "work_tree" if out.strip() == "true" else "not_git"
    if "not a git repository" in (err or "").lower() or "not a work tree" in (err or "").lower():
        return "not_git"
    return "git_error"


def _git_precheck(name: str, project_root: Path, complexity: str) -> CheckResult | None:
    """SKIP on a clean non-git context; ERROR (medium+) on a git subprocess failure/timeout;
    ``None`` to proceed when it is a real work-tree."""
    ctx = _git_context(project_root)
    if ctx == "not_git":
        return _skip(name, "skipped (not a git work tree — git-diff enforcement N/A)")
    if ctx == "git_error":
        return _infra_result(name, complexity, "git probe failed/timed out (wedged index.lock / stalled FS)")
    return None


def _infra_result(name: str, complexity: str, detail: str) -> CheckResult:
    """A regen infra FAILURE on a git repo (no commit / unresolvable base / collector or
    archive failure / exception). Fail-CLOSED at medium+ (ERROR — block), a legitimate SKIP
    below medium. Distinct from a non-git project, which is an inapplicable context, not a
    failure — that always SKIPs (git-diff enforcement does not apply)."""
    if _is_enforcing(complexity):
        return CheckResult(name, False, f"cannot enforce this medium+ iterate: {detail}")
    return _skip(name, f"skipped (complexity={complexity or 'unknown'}; {detail})")


def _removal_suggest(display: str) -> str:
    return (
        f"/shipwright-iterate --type change \"delete or retarget the tests tagged "
        f"@{display} — a removed FR's base-linked tests must not stay green\""
    )


def check_removal_coverage(project_root: Path, run_id: str, commit_hash: str = "") -> CheckResult:
    """Removal → orphan gate. Runs at ALL complexities (a removal is never trivial, SHOULD-FIX
    6). Regenerates base+head (R3); an infra gap is ERROR at medium+, SKIP below (MUST-FIX 1);
    a real un-retired test is a HARD FAIL at any complexity."""
    name = _REMOVAL_NAME
    complexity = _complexity(project_root, run_id)
    if not commit_hash:
        return _infra_result(name, complexity, "no --commit supplied")
    precheck = _git_precheck(name, project_root, complexity)
    if precheck is not None:
        return precheck
    try:
        regen = regenerate_base_head(project_root, commit_hash, with_evidence=False)
        if regen is None:
            return _infra_result(name, complexity, "git unavailable / no base ref / collector unavailable")
        base, head, renames = regen
        verdict = evaluate_removal(base, head, renames)
    except Exception as exc:  # noqa: BLE001 — surface as ERROR at medium+, never a silent crash
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
        verdict = evaluate_cross_layer(base, head)
    except Exception as exc:  # noqa: BLE001 — surface as ERROR at medium+, never a silent crash
        return _infra_result(name, complexity, f"regeneration error: {type(exc).__name__}")
    return _cross_layer_result(name, verdict)


def _cross_layer_result(name: str, verdict: CrossLayerVerdict) -> CheckResult:
    if verdict.could_not_determine:
        return CheckResult(
            name, False,
            "spec changed but no FR-row-level behaviour change was determinable (an AC-prose "
            "edit under an unchanged FR row, or no parseable active FR) — could-not-determine, "
            "a visible WARN for a human to adjudicate, never a silent pass",
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
