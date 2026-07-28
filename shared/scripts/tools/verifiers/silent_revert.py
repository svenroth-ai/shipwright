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

from .common import CheckResult, Severity  # noqa: E402
from .git_helpers import _run_git  # noqa: E402
from .silent_revert_declarations import (  # noqa: E402
    attributed_declared_removals,
    covered_by_declaration as _covered,
)
# Re-exported: `dropped_lines` is this module's published detector surface and
# several tests + the integration test import it from here.
from .silent_revert_detect import dropped_lines  # noqa: E402
from .silent_revert_reading import resolve_default_ref as _resolve_default_ref  # noqa: E402

_NAME = "no silent revert of merged work"

#: Shown per file before truncating, so the operator sees WHAT is being lost.
_SAMPLE_LINES = 4
_SAMPLE_CHARS = 120


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
