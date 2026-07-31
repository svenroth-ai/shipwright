"""F11 gate — an iterate commit carries no derived snapshot
(iterate-2026-07-27-derived-snapshots-off-branch).

F6's add-list is *prose*. Prose does not stop a stray ``git add -A``, a hook, a
repair path, or a future implementation from staging the shared snapshots again —
and one such commit silently reinstates the conflict class this change removed
(external review, openai #5). ``restore_derived_to_head`` covers the producer that
writes them mid-run; this covers the commit itself.

An ERROR, not a warning. It was written as a WARNING first, on the reasoning that
the failure mode is a merge nuisance rather than a safety breach — external review
rejected that, correctly: F11 invokes the verifier WITHOUT ``--strict``, so a
warning here is indistinguishable from no check at all, and the stray commit merges
anyway. A thing called a gate has to gate. The remedy is cheap and local (unstage
the paths, amend), and the regression it prevents is the entire point of the
change.

Own module (not folded into ``iterate_checks.py``) because that file sits at 1054
of a 1062-line bloat baseline (ADR-093); adding a check body there would ratchet it.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from lib.churn_merge import norm  # noqa: E402
from lib.derived_snapshots import (  # noqa: E402
    DERIVED_SNAPSHOTS,
    RESTORABLE_SNAPSHOTS,
)
from .common import CheckResult, Severity  # noqa: E402
from .git_helpers import _iterate_changed_paths  # noqa: E402

__all__ = ["check_no_derived_snapshots_committed"]

_NAME = "no derived snapshots in the iterate commit"


def _restore_flags(offenders: list[str]) -> str:
    """The `git restore` flags this remedy may safely suggest.

    ``--worktree`` on a RUN-WRITTEN path resets the file on disk to its pre-iterate
    state, destroying the ledger F5 just wrote — ``iterate_latest``, the test totals,
    ``test_completeness``, ``surface_verification``, ``ci_supplychain_ack``. That is
    trg-ad29a709 verbatim, and printing it here made it reachable by following this
    gate's own instructions, which is exactly what an operator copies under time
    pressure. Unstaging is enough to clear the gate; the worktree copy is the run's
    own evidence and must survive.
    """
    if set(offenders) - RESTORABLE_SNAPSHOTS:
        return "--staged"
    return "--staged --worktree"


def check_no_derived_snapshots_committed(
    project_root: Path,
    run_id: str,
    commit_hash: str = "",
) -> CheckResult:
    """Fail when the iterate's commit touches any :data:`DERIVED_SNAPSHOTS` path.

    Skipped without a ``--commit`` (nothing to inspect) and when git cannot be
    read — this gate must never invent a finding out of an unreadable repo, the
    same fail-open posture the other commit-scoped iterate checks take. A project
    that does not track these paths simply never trips it.
    """
    if not commit_hash:
        return CheckResult(
            _NAME, None, "skipped (no --commit supplied)",
            severity=Severity.SKIPPED.value,
        )

    paths = _iterate_changed_paths(project_root, commit_hash)
    if paths is None:
        return CheckResult(
            _NAME, None,
            "skipped — the branch diff is unavailable. An EMPTY answer lands here "
            "too: `git show --name-only` prints nothing for a merge commit, so on a "
            "merge HEAD with no resolvable merge-base 'clean' cannot be told from "
            "'blind' — and this gate must never report the second as the first.",
            severity=Severity.SKIPPED.value,
        )

    offenders = sorted({norm(p) for p in paths} & DERIVED_SNAPSHOTS)
    # (see _restore_flags for why the remedy is not a fixed string)
    if not offenders:
        return CheckResult(_NAME, True, f"{len(paths)} path(s), none derived")

    return CheckResult(
        _NAME, False,
        f"{len(offenders)} derived snapshot(s) committed: {', '.join(offenders)} — "
        "these are regenerated from main after merge and must stay out of the PR "
        "(every iterate rewrites them, so N open PRs collide N(N-1)/2 times). "
        f"Fix: `git restore --source=HEAD~1 {_restore_flags(offenders)} -- <paths>` "
        "then amend; see shared/scripts/lib/derived_snapshots.py",
        severity=Severity.ERROR.value,
    )
