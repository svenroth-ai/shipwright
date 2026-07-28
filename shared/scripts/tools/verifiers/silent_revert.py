"""F11 check — this branch does not quietly drop work that landed while it was open.

**The failure this exists for.** PR #463 rewrote `docs/hooks-and-pipeline.md`
from a stale base — 10 insertions, 83 deletions — silently reverting
documentation belonging to four already-merged PRs. Every existing guard let it
through, and each for a defensible reason: requiring branches to be up to date is
what *forces* the integration in which the bad resolution happens; `ensure_current`
correctly refuses a non-churn conflict and hands to a human, which is where the
wholesale "take my side" happens; the `PR Review` LLM gate saw the whole diff and
returned SUCCESS; `Anti-ratchet` only ever asks whether a file GREW; and the
squash-merge flattened the branch, leaving no trace in `main` to audit.

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

**The one undecidable case, narrowed but not eliminated.** If main changed a line
and this branch then changed that same line again, "I built on their change" and
"I threw their change away" are indistinguishable from the text. Where every word
main wrote survives, in order, in the line that replaced it — and that
replacement is one this branch could only have written after seeing theirs —
:mod:`silent_revert_filters` settles it. The rest is still reported and asked
about. Guessing either way is worse: guessing "fine" reproduces the original
failure, guessing "revert" blocks ordinary work with no way through. The
declaration is the answer.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS_ROOT = Path(__file__).resolve().parents[2]
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from lib.churn_merge import is_derived_churn  # noqa: E402

from .common import CheckResult, Severity  # noqa: E402
from .git_helpers import _run_git  # noqa: E402
from .silent_revert_declarations import (  # noqa: E402
    attributed_declared_removals,
    covered_by_declaration as _covered,
)
from .silent_revert_filters import (  # noqa: E402
    matches_default,
    superseded_on_default,
    unexplained_by_edit,
)
from .silent_revert_reading import (  # noqa: E402
    read_side as _read_side,
    resolve_default_ref as _resolve_default_ref,
)

_NAME = "no silent revert of merged work"

#: Shown per file before truncating, so the operator sees WHAT is being lost.
_SAMPLE_LINES = 4
_SAMPLE_CHARS = 120


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
    # Resolve BEFORE the pre-flight so the ref that is validated, the ref that is
    # compared, and the ref the operator is told about are all the same one. This
    # run exists because an operator was handed four findings they could not
    # verify; naming a ref the comparison did not use is that failure in miniature.
    default_branch = _resolve_default_ref(root, default_branch)
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
    undeclared = {p: lines for p, lines in dropped.items() if not _covered(p, declared_removals)}
    # Order matters: findings first. Returning a (non-blocking) SKIP the moment
    # ANY path was unreadable would let one unreadable file convert a real block
    # over every other path into a pass that names none of them (Stage-3 review).
    if problems and not undeclared:
        return CheckResult(
            _NAME, True,
            "skipped (comparison could not be made: " + "; ".join(problems[:3]) + ")",
            severity=Severity.SKIPPED.value,
        )
    incomplete = (
        f"  (comparison also incomplete for {len(problems)} path(s): {problems[0]})"
        if problems else ""
    )

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
          "in shipwright_test_results.json iterate_latest.declared_removals[{path,reason}]"
        + incomplete,
    )


def check_silent_revert_for_run(
    project_root, default_branch: str = "main", *, run_id: str,
) -> CheckResult:
    """F11 entry point: the check plus the run's own declarations.

    ``run_id`` is REQUIRED and keyword-only. Defaulting it to ``""`` would let an
    unconverted caller keep the old two-argument shape while silently changing
    behaviour — every block would read as foreign, discarding even the current
    run's declarations. A TypeError is the only version anyone would notice.
    """
    entries, problem = attributed_declared_removals(project_root, run_id)
    result = check_no_silent_revert(
        project_root, default_branch=default_branch, declared_removals=entries,
    )
    if not problem:
        return result
    # A disregarded declaration is DISCLOSED either way — this module's one
    # prohibition is saying nothing (external code review, openai #2).
    if result.is_failure:
        return CheckResult(result.name, result.ok, f"{result.detail}  ({problem})",
                           severity=result.severity)
    # Nothing dropped ⇒ nothing wrongly excused, so a hard failure would be a
    # false red — but declarations this gate did not use must still be reported.
    # WARNING is the honest severity when the subject is the evidence, not the tree.
    return CheckResult(
        result.name, False,
        f"{result.detail} — but {problem}. Re-run F5 to rewrite "
        "shipwright_test_results.json for this run, or carry "
        "`declared_removals` in the F5c entry, which the F11 integration "
        "cannot rewind",
        severity=Severity.WARNING.value,
    )


__all__ = [
    "attributed_declared_removals",
    "check_no_silent_revert",
    "check_silent_revert_for_run",
    "dropped_lines",
]
