"""F11 check — this branch does not quietly drop work that landed while it was open.

**The failure this exists for.** PR #463 rewrote `docs/hooks-and-pipeline.md`
from a stale base — 10 insertions, 83 deletions — silently reverting
documentation belonging to four already-merged PRs. Every existing guard let it
through, and each for a defensible reason:

* the repo requires branches to be up to date, which is what *forces* the
  integration in which the bad resolution happens — the enforcement is the
  trigger, not the cure;
* `ensure_current` correctly refuses to auto-resolve a non-churn conflict and
  hands over to a human, which is where the wholesale "take my side" happens;
* the `PR Review` LLM gate saw the whole diff and returned SUCCESS;
* `Anti-ratchet` only ever asks whether a file GREW past its baseline;
* and the squash-merge flattened the branch, so the resolution left no trace in
  `main` to audit afterwards.

**The question asked here is narrow and decidable.** Every line `main` gained
since this branch forked must still be present in the branch's tree. A line that
main has, that arrived after the fork point, and that the branch no longer
carries, is work being thrown away.

Two things it deliberately does NOT do:

* It does not accuse a branch that has simply not integrated yet. Before the
  merge, main's newer lines are legitimately absent — that is ``BEHIND``, not a
  revert, and flagging it would fire on every open branch the moment anything
  lands. Only content the branch has *had a chance to keep* counts, i.e. lines
  reachable from the branch's own history.
* It does not forbid removal. Deleting something main just added is sometimes
  exactly right; it just has to be said out loud, with a reason, like every
  other disposition in this pipeline.

**The one undecidable case, on purpose.** If main changed a line and this branch
then changed that same line again, "I built on their change" and "I threw their
change away" are indistinguishable from the text — and that is exactly the #463
shape at line granularity, where a whole file was replaced by an older copy. The
check reports it and asks. Guessing in either direction is worse: guessing
"fine" reproduces the original failure, guessing "revert" would block ordinary
work with no way to proceed. The declaration is the answer.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS_ROOT = Path(__file__).resolve().parents[2]
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from lib.churn_merge import CHURN_ALLOWLIST  # noqa: E402

from .common import CheckResult, Severity  # noqa: E402
from .git_helpers import _run_git  # noqa: E402

_NAME = "no silent revert of merged work"

#: Shown per file before truncating, so the operator sees WHAT is being lost
#: rather than only a count.
_SAMPLE_LINES = 4
_SAMPLE_CHARS = 120


def _significant(line: str) -> bool:
    """Formatting churn is not lost work."""
    return bool(line.strip())


def _file_lines(project_root: Path, ref: str, path: str) -> set[str] | None:
    """The significant lines of ``path`` at ``ref``; ``None`` if absent there."""
    rc, out, _ = _run_git(project_root, "show", f"{ref}:{path}")
    if rc != 0:
        return None
    return {line.strip() for line in out.splitlines() if _significant(line)}


def _integration_merges(root: Path, default_branch: str, head: str) -> list[tuple[str, str]]:
    """``(branch_parent, merged_in_parent)`` for the merges THIS BRANCH performed.

    Scoped to ``default_branch..head`` — commits reachable from the branch but not
    from the default branch. That is exactly the branch's own history, including
    the integration merge it made, and it excludes every merge already part of the
    default branch's past.

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
    restored in a later commit correctly counts as kept.

    A branch that has not integrated yet has no such merge and returns empty —
    that state is ``BEHIND``, not a revert.
    """
    root = Path(project_root)
    dropped: dict[str, set[str]] = {}

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
            if path in CHURN_ALLOWLIST:
                # Derived artifacts are REGENERATED from the merged tree, not
                # merged line-by-line — that is what CHURN_ALLOWLIST marks. Their
                # content legitimately changes wholesale on every integration, so
                # comparing them here flags all eleven of them on every single
                # iterate. Caught by running this check against its own branch.
                continue
            theirs = _file_lines(root, p2, path)
            if theirs is None:
                continue  # they deleted it too — not this branch's doing
            gained = theirs - (_file_lines(root, base, path) or set())
            if not gained:
                continue
            ours = _file_lines(root, head, path)
            missing = gained if ours is None else gained - ours
            if missing:
                dropped.setdefault(path, set()).update(missing)

    return {path: sorted(lines) for path, lines in dropped.items()}


def _covered(path: str, declared_removals) -> bool:
    """True when the operator declared this path's removal WITH a reason."""
    for entry in declared_removals or []:
        if not isinstance(entry, dict):
            continue
        if str(entry.get("path", "")) == path and str(entry.get("reason", "")).strip():
            return True
    return False


def check_no_silent_revert(
    project_root,
    default_branch: str = "main",
    declared_removals=None,
) -> CheckResult:
    """Block when the branch's tree is missing content the default branch gained."""
    root = Path(project_root)
    rc, out, _ = _run_git(root, "rev-parse", "--is-inside-work-tree")
    if rc != 0 or out.strip() != "true":
        return CheckResult(_NAME, True, "skipped (not a git work tree)",
                           severity=Severity.SKIPPED.value)
    rc, _, _ = _run_git(root, "rev-parse", "--verify", f"{default_branch}^{{commit}}")
    if rc != 0:
        # Honest degradation: unresolvable base means the comparison did not run.
        # Reporting "nothing lost" here would be the very silence this check exists
        # to remove.
        return CheckResult(
            _NAME, True,
            f"skipped ({default_branch!r} does not resolve — comparison not made)",
            severity=Severity.SKIPPED.value,
        )

    problems: list[str] = []
    dropped = dropped_lines(root, default_branch, problems=problems)
    if problems:
        return CheckResult(
            _NAME, True,
            "skipped (comparison could not be made: " + "; ".join(problems[:3]) + ")",
            severity=Severity.SKIPPED.value,
        )
    undeclared = {p: lines for p, lines in dropped.items() if not _covered(p, declared_removals)}

    if not undeclared:
        if dropped:
            return CheckResult(
                _NAME, True,
                f"{len(dropped)} file(s) drop content from {default_branch}, all declared "
                f"with a reason: {', '.join(sorted(dropped))}",
            )
        return CheckResult(_NAME, True, f"nothing {default_branch} gained since the fork is missing")

    parts = []
    for path in sorted(undeclared)[:4]:
        sample = "; ".join(line.strip()[:_SAMPLE_CHARS] for line in undeclared[path][:_SAMPLE_LINES])
        parts.append(f"{path} ({len(undeclared[path])} line(s)): {sample}")
    return CheckResult(
        _NAME, False,
        f"this branch is missing content that {default_branch} gained since it forked — "
        "work merged by someone else would be reverted by this change: "
        + " | ".join(parts)
        + "  →  re-integrate and resolve as a UNION, or declare the removal with a reason "
          "in shipwright_test_results.json iterate_latest.declared_removals[{path,reason}]",
    )


def declared_removals(project_root) -> list[dict]:
    """``iterate_latest.declared_removals`` — the run's stated intentional removals.

    Kept here rather than at the call site so the F11 orchestrator stays a list of
    check invocations. A missing or malformed file yields ``[]``: an unreadable
    declaration must not silently excuse a removal.
    """
    import json

    path = Path(project_root) / "shipwright_test_results.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    entries = (data.get("iterate_latest") or {}).get("declared_removals")
    return [e for e in entries if isinstance(e, dict)] if isinstance(entries, list) else []


def check_silent_revert_for_run(project_root, default_branch: str = "main") -> CheckResult:
    """F11 entry point: the check plus the run's own declarations."""
    return check_no_silent_revert(
        project_root, default_branch=default_branch,
        declared_removals=declared_removals(project_root),
    )


__all__ = [
    "check_no_silent_revert",
    "check_silent_revert_for_run",
    "declared_removals",
    "dropped_lines",
]
