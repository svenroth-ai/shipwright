"""``cross_component`` integration-coverage gate.

Extracted verbatim from ``iterate_checks.py``
(iterate-2026-06-13-risk-detector-extract) so that load-bearing verifier
stays under the bloat limit. Behaviour is unchanged — ``iterate_checks``
re-exports ``check_integration_coverage`` (used by ``run_all_checks``) plus
``_is_cross_component`` / ``_CROSS_COMPONENT_PATTERNS`` (pinned by the drift
test ``test_cross_component_patterns_sync``), so every existing import path
keeps resolving.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

_SCRIPTS_ROOT = Path(__file__).resolve().parents[2]
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from lib.iterate_entry import find_entry_by_run_id  # noqa: E402

from ._iterate_latest import (  # noqa: E402
    STATE_MALFORMED,
    STATE_MISSING,
    read_iterate_latest,
)
from .common import CheckResult, Severity  # noqa: E402
from .git_helpers import _iterate_changed_paths, _run_git, git_context  # noqa: E402


# --- cross_component integration-coverage gate ------------------------------
# Self-contained copy of ``classify_complexity.CROSS_COMPONENT_FILE_PATTERNS`` so
# this load-bearing verifier (runs in every shared/tests + CI session) never
# cross-plugin-imports the iterate-plugin lib (ADR-044). The drift test
# ``test_cross_component_patterns_sync`` pins this == the SSoT, forward + reverse.
_CROSS_COMPONENT_PATTERNS = (
    r"(^|/)(integrate_main|ensure_current|resolve_churn_conflicts)\.py$",
    r"(^|/)(churn_merge|gitattributes_union|gitattributes_selfheal)\.py$",
    r"(^|/)(autonomous_loop|events_log)\.py$",
    r"(^|/)campaign_[^/]*\.py$",
    r"(^|/)campaign-mode\.md$",
    r"(^|/)hooks\.json$",
    r"(^|/)hooks/.+\.py$",  # any hook script under a hooks/ dir (incl. scripts/hooks/ + nested)
    r"(^|/)(verify_phase|get_phase_context)\.py$",
)


def _is_cross_component(changed_files: list[str] | None) -> bool:
    for path in changed_files or []:
        norm = path.replace("\\", "/")
        for pat in _CROSS_COMPONENT_PATTERNS:
            if re.search(pat, norm):
                return True
    return False


#: Recorded complexities that are unambiguously BELOW the ``medium`` floor
#: ``risk_taxonomy.cross_component`` enforces. Membership is checked positively —
#: an absent, empty or unrecognised value must produce NO floor claim, because
#: asserting an under-classification the gate cannot substantiate is the same
#: species of overclaim this module was fixed for.
_BELOW_MEDIUM = ("trivial", "small")


def _read_entry(project_root: Path, run_id: str) -> dict | None:
    """This run's F5c entry, or ``None`` when it cannot be read.

    The store itself no longer raises on an undecodable file: ``lib/iterate_entry.py``
    catches ``UnicodeDecodeError`` alongside ``(JSONDecodeError, OSError)`` since
    trg-06216b9f, so a non-UTF-8 entry file (a write torn mid-multibyte-sequence, a
    cp1252 editor save) is skipped at the source instead of taking down the whole F11
    report. This absorption was added while that fix was still deferred and is KEPT
    deliberately: AC-11 requires a malformed entry to be *absent*, never fatal, and
    this gate should not silently depend on a shared reader's error policy staying
    put. It is a belt-and-braces guard, not the primary fix.

    Either way the direction is fail-closed: the caller holds no self-report, and a
    cross-component diff still ERRORs.
    """
    try:
        entry = find_entry_by_run_id(project_root, run_id)
    except (ValueError, OSError):  # incl. UnicodeDecodeError, JSONDecodeError
        return None
    return entry if isinstance(entry, dict) else None


def _floor_note(entry: object | None) -> str:
    """The second thing that went wrong, when it is knowable — plus both actions.

    The gate reads only ``test_completeness.behaviors``; it never reads
    ``status`` and, since the reorder, never reads complexity. So recording the
    behavior in THIS run's F5c entry satisfies it at any tier, including
    ``trivial`` — where ``check_test_completeness_ledger`` SKIPs and the Phase
    Matrix marks the ledger auto-``n/a``, but nothing rejects a ``behaviors`` list
    that is present anyway. An earlier draft of this note claimed escalation was
    the ONLY route; that was false, and it would have sent a trivial run to buy an
    iterate spec, a mini-plan, an approval gate and an external plan review it did
    not need (Stage-3 doubt review). Both routes are named, cheapest first.

    ``str(...).strip().lower()`` is deliberate: a legacy entry written before
    ``normalize_legacy_entry`` can carry ``" Small "``, and a non-string value must
    degrade to "unknown" rather than raise.
    """
    if not isinstance(entry, dict):
        return ""
    complexity = str(entry.get("complexity", "")).strip().lower()
    if complexity not in _BELOW_MEDIUM:
        return ""
    return (
        f"  This run is recorded complexity={complexity}, below the `medium` floor "
        "the `cross_component` risk flag enforces (risk_taxonomy min_complexity) — "
        "it is under-classified as well as under-tested. Either route clears this "
        "gate: record the integration behavior in THIS run's F5c entry "
        "(`test_completeness.behaviors`, which this gate reads at every tier — it "
        "is accepted at `trivial` even though the ledger is otherwise auto-`n/a` "
        "there), or escalate the run to `medium` if the change really warrants the "
        "fuller process."
    )


def check_integration_coverage(project_root: Path, run_id: str, commit_hash: str = "") -> CheckResult:
    """Non-dodgeable ``cross_component`` gate. An iterate that touches FRAMEWORK
    cross-component machinery (merge/churn resolver, Claude-Code hooks + hook
    fan-out, pipeline phase validators, campaign drain) MUST carry a behavior with
    ``category: "integration"`` in the Test Completeness Ledger — a real-scenario
    test proving the pieces compose. The empirical machinery is otherwise
    boundary-centric (``touches_io_boundary`` → round-trip) and app-surface-centric
    (F0.5), so it forces NOTHING for framework composition; this closes that hole
    (motivating class: the auto-merge churn cascade).

    **The DIFF decides, at every complexity**
    (iterate-2026-08-01-coverage-gate-recompute-order, superseding the medium+
    floor). The flag is recomputed from the diff (merge-base..HEAD), never an
    agent-reported value — but until this change the recompute sat BELOW a gate on
    the run's *recorded* complexity, so it was reached only for runs that had
    already self-reported into the enforcing band. Non-dodgeability was a property
    of the flag, never of the gate.

    That band is exactly where the backstop is needed: ``cross_component`` carries
    ``min_complexity: medium``, so a *detected* change is already forced to medium
    and the gate fires anyway. Below medium is reachable only when detection FAILED
    at classification time (Stage 1 sees the message only; the flag is diff-driven)
    and the Stage-2 Quick Scout detector step — prose the agent must remember to
    run — did not catch it. The old order made the mechanical check depend on the
    non-mechanical one it exists to backstop. The recorded complexity is now
    message content (see :func:`_floor_note`), never control flow.

    Infra failures fail CLOSED at every complexity: only a genuine non-git context
    stands the gate down. Same posture as
    :func:`~.ci_supplychain.check_ci_supplychain_ack` on BOTH axes now — complexity
    and git faults: that gate was migrated off the binary ``rev-parse --git-dir``
    probe onto the same tri-state :func:`~.git_helpers.git_context` (trg-20cc9ec8).
    **Scoped to the three ``git_context`` consumers, deliberately** — the binary
    conflation is NOT gone from the repo. ``git_helpers._git_available`` still answers
    it the old way for five callers, one of which (``check_spec_impact_recorded``) is
    an F11 ERROR gate that green-SKIPs on it; migrating those is trg-4183acd3.
    """
    name = "integration coverage (cross-component)"
    # Tri-state, not "did git exit 0": a broken binary / permission failure /
    # wedged index.lock all return non-zero from INSIDE a repo, and reading that
    # as "not a repo" would green-skip a real infra fault. Only a definitive
    # non-git answer stands down — an F11 run outside a repo has nothing to merge,
    # and the CLI sandbox tests depend on that skip.
    ctx = git_context(project_root)
    if ctx == "not_git":
        return CheckResult(name, True, "skipped (not a git work tree)",
                           severity=Severity.SKIPPED.value)
    # Proceed only on an EXPLICIT work_tree. Branching on `== "git_error"` and
    # falling through otherwise would make an unrecognised state fail OPEN, which is
    # the one direction this helper exists to prevent.
    if ctx != "work_tree":
        return CheckResult(
            name, False,
            "git could not answer whether this is a work tree — common causes: a "
            "wedged index.lock, a stalled filesystem, a `safe.directory` / dubious-"
            "ownership refusal, or git missing from PATH. Run `git -C <project> "
            "rev-parse --is-inside-work-tree` to see git's own message. Refusing to "
            "certify cross-component machinery as untouched.",
        )
    # An absent --commit INSIDE a repo is an unobtainable diff, not a licence to
    # stand down: the cheaper input must not be the safer one for a dodger.
    commit = commit_hash
    if not commit:
        # Bounded like every other git probe on this path (git_context 10s,
        # _iterate_changed_paths 30s). Unbounded, a stalled network mount that had
        # already answered the cached metadata probe would hang F11 with no report —
        # exactly the outcome the fail-closed refusal below exists to replace. A
        # timeout yields rc != 0 and lands on that refusal.
        rc, out, _ = _run_git(project_root, "rev-parse", "HEAD", timeout=10.0)
        commit = out.strip() if rc == 0 else ""
    if not commit:
        return CheckResult(
            name, False,
            "no commit supplied and HEAD is unresolvable — refusing to certify "
            "cross-component machinery as untouched",
        )
    changed = _iterate_changed_paths(project_root, commit)
    # `is None`, not `not changed`. `[]` is a FACT (this branch has no net change
    # vs the trunk); `None` is ignorance. Conflating them would hard-fail a
    # commit-then-revert branch with a cause that did not occur.
    if changed is None:
        return CheckResult(
            name, False,
            f"cannot obtain the diff for {commit[:8]} — refusing to certify "
            "cross-component machinery as untouched",
        )
    hit = [p for p in changed if _is_cross_component([p])]
    if not hit:
        return CheckResult(name, True, "no cross-component machinery touched")
    # Applicability is established; only NOW is the self-report read. It may be
    # absent (no entry file), unusable (a corrupt one — the store skips it) or
    # unreadable (`_read_entry` absorbs the raise), and none of those may excuse the
    # finding: omitting the self-report must never be the cheap way out.
    entry = _read_entry(project_root, run_id)
    # Prefer the PER-RUN entry, same reason as check_test_completeness_ledger
    # (iterate-2026-07-27-derived-snapshots-off-branch): the shared results file is
    # restored to HEAD before F11 reads it on a behind branch, so this run's ledger
    # would be gone and a change WITH integration coverage would be failed for
    # lacking it. Caught by this gate on its own iterate.
    block: dict = entry.get("test_completeness") if isinstance(entry, dict) else {}
    if not isinstance(block, dict):
        block = {}
    if not block:
        # The shared file is a LAST resort, and it must be ATTRIBUTED. Reading it raw
        # credited whatever `iterate_latest` happened to be there: on a branch behind
        # main, F11 restores it to HEAD, so an unattributed read sees the PREVIOUS
        # run's block and a cross-component change passes green on someone else's
        # integration test. `check_test_completeness_ledger`, `check_surface_verification`
        # and the silent-revert declarations all guard this same file with
        # `read_iterate_latest(...).is_current`; this gate did not, and the reorder
        # widened that from medium+ to every complexity while the docstring above kept
        # saying "non-dodgeable" (Stage-3 doubt review).
        latest = read_iterate_latest(project_root, run_id)
        if latest.state == STATE_MALFORMED:
            # Surface corruption EXPLICITLY — never misreport an unreadable results
            # file as "missing integration coverage" (external-review fix).
            return CheckResult(
                name, False,
                f"cross-component change touched ({', '.join(hit[:3])}) but "
                f"{latest.detail} — cannot verify integration coverage"
                + _floor_note(entry),
            )
        if latest.is_current:
            candidate = (latest.block or {}).get("test_completeness")
            block = candidate if isinstance(candidate, dict) else {}
        elif latest.state != STATE_MISSING:
            # Present but not ours (foreign / unattributed). Say so instead of
            # silently falling through to "no integration behavior" — the operator
            # needs to know the ledger they wrote is not the one being read.
            return CheckResult(
                name, False,
                f"cross-component change touched ({', '.join(hit[:3])}) but the only "
                f"Test Completeness ledger available is not this run's ({latest.detail}) "
                "— record the integration behavior in this run's F5c entry"
                + _floor_note(entry),
            )
    behaviors = block.get("behaviors", []) if isinstance(block, dict) else []
    has_integration = any(
        isinstance(b, dict) and str(b.get("category", "")).lower() == "integration"
        for b in behaviors
    )
    if has_integration:
        return CheckResult(name, True, f"cross-component change has integration coverage ({hit[0]})")
    return CheckResult(
        name, False,
        f"cross-component machinery touched ({', '.join(hit[:3])}) but NO Test "
        "Completeness behavior has category='integration' — add a real-scenario "
        "integration test proving the components compose (see "
        "shared/tests/test_parallel_merge_cascade_integration.py), mark it "
        "category:integration, or split the cross-component change out."
        + _floor_note(entry),
    )
