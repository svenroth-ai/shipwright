"""What this branch took delivery of and then dropped — the merge walk.

The last split of :mod:`silent_revert`, made for the same 300-line cap that
produced :mod:`silent_revert_reading` (primitives), :mod:`silent_revert_filters`
(policy) and :mod:`silent_revert_declarations` (the operator's exceptions). The
seam is the honest one left: everything here WALKS THE REPOSITORY to compute a
set of dropped lines; the module next door turns that set into a
:class:`CheckResult` and decides what the operator is told.

Nothing here knows about declarations, severities, or how a finding is worded.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS_ROOT = Path(__file__).resolve().parents[2]
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from lib.churn_merge import is_derived_churn  # noqa: E402

from .git_helpers import _run_git  # noqa: E402
from .silent_revert_filters import (  # noqa: E402
    matches_default,
    superseded_on_default,
    unexplained_by_edit,
)
from .silent_revert_reading import (  # noqa: E402
    read_side as _read_side,
    resolve_default_ref as _resolve_default_ref,
)

__all__ = ["dropped_lines"]


def _integration_merges(root: Path, default_branch: str, head: str) -> list[tuple[str, str]]:
    """``(branch_parent, merged_in_parent)`` for the merges THIS BRANCH performed.

    Scoped to ``default_branch..head`` — the branch's own history, including the
    integration merges it made, and nothing already in the default branch's past.
    Walking the full history instead is both wrong and slow: for a merge that
    landed months ago, everything legitimately edited or deleted since reads as
    "dropped". A probe on this repo's real history reported 889 files for a
    perfectly clean merge, and took over ten minutes to do it.
    """
    rc, out, _ = _run_git(root, "rev-list", "--merges", f"{default_branch}..{head}")
    if rc != 0:
        return []
    merges: list[tuple[str, str]] = []
    for sha in (s.strip() for s in out.splitlines() if s.strip()):
        rc, parents, _ = _run_git(root, "rev-list", "--parents", "-n", "1", sha)
        if rc != 0:
            continue
        bits = parents.split()
        if len(bits) < 3:
            continue
        p1, others = bits[1], bits[2:]
        # EVERY non-first parent is inspected, not just the second: in an octopus
        # merge (`git merge topic main`) the default branch can be third or later,
        # and looking only at parent two would skip the integration entirely.
        for other in others:
            rc, _, _ = _run_git(root, "merge-base", "--is-ancestor", other, default_branch)
            if rc == 0:
                merges.append((p1, other))
    return merges


def dropped_lines(project_root, default_branch: str, head: str = "HEAD",
                  problems: list[str] | None = None) -> dict[str, list[str]]:
    """path → lines the branch took delivery of and then dropped.

    Asked **per integration merge**, which is the only framing that is both
    precise and free of false alarms:

    * ``B`` = the common ancestor of that merge's two sides,
    * ``gained`` = what the merged-in side had that ``B`` did not — i.e. exactly
      the work that landed on the default branch while this branch was open,
    * anything in ``gained`` that ``head`` no longer carries was dropped.

    Comparing ``head`` against the default branch WHOLESALE would flag every
    ordinary edit (the old line is on main and absent here, by definition);
    subtracting ``B`` is what separates "I changed my line" from "I discarded
    theirs". Checking against ``head`` rather than the merge commit means content
    restored in a later commit correctly counts as kept. A branch that has not
    integrated yet has no such merge and returns empty — ``BEHIND``, not a revert.

    Several things that satisfy ``gained - ours`` are not losses; each is settled
    by a proof in :mod:`silent_revert_filters`, never by a threshold, and each
    runs only once something was going to be reported. Per-path reads are memoised.
    """
    root = Path(project_root)
    dropped: dict[str, set[str]] = {}
    # The ref the branch actually integrates — a stale local one silently skips
    # whole merges AND answers "does main still carry this?" against the wrong
    # tree, so every use takes the same resolved value.
    default_branch = _resolve_default_ref(root, default_branch)
    tip_cache: dict = {}
    superseded_cache: dict = {}   # keyed (delivered, path)
    edit_cache: dict = {}         # keyed path — its ref pair is always (default, head)

    for p1, p2 in _integration_merges(root, default_branch, head):
        rc, base, _ = _run_git(root, "merge-base", p1, p2)
        if rc != 0 or not base.strip():
            # A shallow / incomplete clone can hold the merge but not its base.
            # Reporting "nothing dropped" here would be the very silence this
            # check exists to remove (external review).
            if problems is not None:
                problems.append(f"merge-base of {p1[:8]}..{p2[:8]} does not resolve")
            continue
        base = base.strip()
        rc, out, _ = _run_git(root, "diff", "--name-only", f"{base}..{p2}")
        if rc != 0:
            if problems is not None:
                problems.append(f"cannot diff {base[:8]}..{p2[:8]}")
            continue
        for path in (p.strip() for p in out.splitlines() if p.strip()):
            if is_derived_churn(path):
                # Derived artifacts are REGENERATED from the merged tree, not
                # merged line-by-line. Their content legitimately changes wholesale
                # on every integration, so comparing them flags all eleven on every
                # iterate. Caught by running this check against its own branch.
                # The predicate is the churn resolver's own, so "derived" cannot
                # come to mean two things (a campaign status.json used to be
                # regenerated churn to `classify` and authored content here).
                continue
            # Strongest of the three proofs and the cheapest, so it is asked first:
            # if the two trees agree about the file, nothing in it can be a loss.
            if matches_default(root, default_branch, head, path, tip_cache, problems):
                continue
            # Every side goes through read_side: an unreadable one is DISCLOSED,
            # never inferred as an absence (external code review).
            theirs, ok = _read_side(root, p2, path, problems)
            if not ok or theirs is None:
                continue  # unreadable (disclosed) or they deleted it too
            base_lines = _read_side(root, base, path, problems)[0] or set()
            gained = theirs - base_lines
            if not gained:
                continue
            ours = _read_side(root, head, path, problems)[0]
            missing = gained if ours is None else gained - ours
            if missing:
                missing = superseded_on_default(
                    root, default_branch, p2, head, path, missing, superseded_cache)
            # Skipped when our side is absent: the branch deleted the file, so the
            # diff holds only deletions and there is nothing to pair with. Saves
            # the git call; the outcome is the same either way.
            if missing and ours is not None:
                # A replacement only counts if this branch could have written it
                # AFTER seeing theirs — so neither the merge base nor the branch's
                # own pre-merge side may vouch for a line they predate.
                excluded = base_lines | (_read_side(root, p1, path, problems)[0] or set())
                missing = unexplained_by_edit(
                    root, default_branch, head, path, missing, excluded, edit_cache)
            if missing:
                dropped.setdefault(path, set()).update(missing)

    return {path: sorted(lines) for path, lines in dropped.items()}
