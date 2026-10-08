"""The diff-size arm of the review triggers, defined once.

**The rule.** A change crosses the review threshold when the lines it ADDS plus
the lines it REMOVES, measured against its merge-base with the trunk with
rename detection off (``git diff --numstat --no-renames <merge-base>``), number
**strictly more than 100**. Exactly 100 does not trigger; 101 does. A binary
file counts 0 (numstat prints ``-``). An untracked file counts its line count,
because all of it is added.

**What is not counted:** patch headers, hunk headers and context lines. The docs
used to print ``git diff HEAD~1 | wc -l``, which counted all three and saw only
the last commit. Also not counted: the iterate's own finalization records
(:data:`UNCOUNTED_PREFIXES` / :data:`UNCOUNTED_FILES`). F3-F5c write them after
the trigger is decided and they are generated, not reviewed. Counting them
would push almost every small iterate over 100 lines at F11, so the rule would
in practice say "always" and not "risk flag or diff > 100".

**Who uses it.** Step 3.4's ``diff_risk_recheck.py`` (working tree plus untracked
files against the fork point, before F6 commits) re-exports
:data:`PLAN_REVIEW_DIFF_LOC_THRESHOLD`. The F11 gate
``verifiers/cascade_trigger.py`` measures the committed branch with the same
rule. Both get the number from here.

Standard library only, with no package-relative import. The iterate plugin loads
this file by path under a private module name (ADR-044/045: importing across
the plugin boundary collides on ``lib``), so it must import cleanly under any
name.
"""

from __future__ import annotations

__all__ = [
    "DIFF_LOC_THRESHOLD",
    "PLAN_REVIEW_DIFF_LOC_THRESHOLD",
    "UNCOUNTED_FILES",
    "UNCOUNTED_PREFIXES",
    "exceeds_diff_threshold",
    "is_counted_path",
    "numstat_changed_lines",
]

#: Strictly greater-than: ``> 100`` triggers, ``== 100`` does not.
DIFF_LOC_THRESHOLD = 100

#: The name Step 3.4 has always used; kept as an alias so its callers resolve.
PLAN_REVIEW_DIFF_LOC_THRESHOLD = DIFF_LOC_THRESHOLD

#: Repo-relative prefixes whose lines are not counted: Shipwright's generated
#: artifact tree and the per-run changelog drops.
UNCOUNTED_PREFIXES: tuple[str, ...] = (".shipwright/", "CHANGELOG-unreleased.d/")

#: Root-level ledgers that F5 / F5b rewrite on every run.
UNCOUNTED_FILES: frozenset[str] = frozenset({
    "shipwright_events.jsonl",
    "shipwright_test_results.json",
})


def _norm(path: str) -> str:
    norm = path.strip().strip('"').replace("\\", "/")
    while norm.startswith("./"):
        norm = norm[2:]
    return norm


def is_counted_path(path: str) -> bool:
    """``False`` for a finalization record, ``True`` for everything else."""
    norm = _norm(path)
    if not norm:
        return False
    return norm not in UNCOUNTED_FILES and not norm.startswith(UNCOUNTED_PREFIXES)


def exceeds_diff_threshold(changed_lines: int) -> bool:
    """The trigger: ``changed_lines > 100``. The boundary is stated here only."""
    return changed_lines > DIFF_LOC_THRESHOLD


def numstat_changed_lines(raw: str) -> tuple[list[str], int]:
    """``(paths, counted added+removed)`` from ``git diff --numstat --no-renames``.

    Accepts newline- or NUL-separated records (``-z``). Every path is returned,
    so callers can still run their risk detectors on all of them. Only paths
    :func:`is_counted_path` accepts add to the total. A rename record (an empty
    path field, which appears only when rename detection is on) raises
    ``ValueError``: it would hide the old side of a move.
    """
    paths: list[str] = []
    total = 0
    # `-z` output is split on NUL only: a newline inside a path is data there.
    for record in (raw.split("\0") if "\0" in raw else raw.splitlines()):
        if not record.strip():
            continue
        parts = record.split("\t", 2)
        if len(parts) < 3 or not parts[2]:
            raise ValueError(
                f"numstat record {record[:80]!r} has no path; rename detection "
                "appears to be on (use --no-renames so both sides of a move count)"
            )
        added, removed, path = parts
        paths.append(path)
        if is_counted_path(path):
            total += (int(added) if added.isdigit() else 0) + (int(removed) if removed.isdigit() else 0)
    return paths, total
