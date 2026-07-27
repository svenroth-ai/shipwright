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
from lib.derived_snapshots import DERIVED_SNAPSHOTS  # noqa: E402
from tools.verifiers.common import CheckResult, Severity  # noqa: E402
from tools.verifiers.git_helpers import _commit_changed_paths  # noqa: E402

__all__ = ["check_no_derived_snapshots_committed"]

_NAME = "no derived snapshots in the iterate commit"


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

    paths = _commit_changed_paths(project_root, commit_hash)
    if paths is None:
        return CheckResult(
            _NAME, None, "skipped (commit not readable)",
            severity=Severity.SKIPPED.value,
        )

    offenders = sorted({norm(p) for p in paths} & DERIVED_SNAPSHOTS)
    if not offenders:
        return CheckResult(_NAME, True, f"{len(paths)} path(s), none derived")

    return CheckResult(
        _NAME, False,
        f"{len(offenders)} derived snapshot(s) committed: {', '.join(offenders)} — "
        "these are regenerated from main after merge and must stay out of the PR "
        "(every iterate rewrites them, so N open PRs collide N(N-1)/2 times). "
        "Fix: `git restore --source=HEAD~1 --staged --worktree -- <paths>` then "
        "amend; see shared/scripts/lib/derived_snapshots.py",
        severity=Severity.ERROR.value,
    )
