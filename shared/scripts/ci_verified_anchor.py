#!/usr/bin/env python3
"""Walk first-parent ancestors of a commit to find the newest one CI
structurally verified (P3.4c anchor promotion — "B: anchor to the newest
verified ancestor",
``.shipwright/planning/iterate/iterate-2026-09-10-p34c-promotion-anchor-guard.md``).

**Why this exists.** ``ci_provenance.resolve_ci_verification`` answers "was
THIS EXACT commit verified" — and this repo's own merge cadence means HEAD is
verified only in the narrow window between a manifest-refresh push and the
next test-adding merge (any PR that adds/renames/removes a test file changes
``untagged_tests``, the structural comparison's own full collected-ID list).
Outside that window, treating "HEAD isn't verified" as "nothing is available"
throws away a real, still-valid verified commit sitting a few commits back.
This module composes the SAME unforgeability predicate against ancestors
instead of re-deriving trust from scratch — it never re-implements the
push/default-branch/success/step-success filter, it only asks the question
at more than one commit.

**What must never change (restated, because it is the whole point):** the
anchor MOVES; the trust boundary does not. Every candidate is checked through
the unmodified ``resolve_ci_verification`` — an ancestor is never accepted
merely for being "close enough" or "recent"; it must independently pass the
exact same push/default-branch/conclusion=success/step-success gate HEAD
itself would have to pass.

**Ancestors only, first-parent only.** A commit that is not an ancestor of
the commit under evaluation says nothing about that tree — walking anything
else (a branch tip, a recent-but-unrelated commit) would let evidence from a
DIFFERENT line of history stand in for this one. First-parent, not every
parent: on a merge commit this walks the mainline history a `push` to the
default branch actually produces, the same history shape
``git log --first-parent`` is conventionally used to render. This is
sufficient, not merely convenient (external plan review, glm/low): a
``verified`` verdict requires ``event==push && head_branch==default_branch``
(``ci_provenance._qualifying_runs``), and a push-triggered run's commit
lands on the default branch's own first-parent chain by construction — a
verified commit reachable only through a non-first-parent edge is not a
case this trust boundary can produce.

**Bounded, deterministically.** The walk stops after ``max_commits`` commits
or at commits older than ``since_days`` (matching the GitHub Actions run/
artifact retention horizon most callers of this predicate ultimately depend
on) — never searches forever. Exhausting the bound reports ``unavailable``,
the same honest "no usable evidence yet" outcome
``ci_execution_evidence.resolve_execution_evidence`` already uses for the
analogous "verified but no artifact" case — never an error, and never a
promotion.

Three outcomes: ``found`` (some commit at or before ``head_commit``, within
the bound, is ``verified``), ``unavailable`` (every candidate within the
bound resolved to ``no_record``/``not_verified``, or a candidate could not be
queried at all — a query hiccup on ONE candidate degrades to "keep looking
degraded", never a hard failure, because this whole mechanism is already a
best-effort improvement over "unavailable", not the load-bearing evidence
check itself), ``error`` (the ancestor walk itself could not be computed —
``git log`` failed to run at all, so there is no candidate list to search).
A run of ``_CONSECUTIVE_ERROR_LIMIT`` query errors in a row (Stage-3 doubt
review, medium) reports ``unavailable`` early rather than exhausting the
whole bound — a systemic query fault (offline, unauthenticated, rate
limited) otherwise burns the FULL ``max_commits`` worth of ``gh api`` calls
to reach the same conclusion a handful already establishes, worsening the
very rate limit it is failing on; a single candidate erroring on its own way
back to a "verified" one further back is unaffected (the counter resets on
any non-error verdict).
"""

from __future__ import annotations

import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

_SHARED_SCRIPTS = Path(__file__).resolve().parent
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

from ci_provenance import resolve_ci_verification  # noqa: E402

_GIT_TIMEOUT_SECONDS = 15

#: Same shape as `ci_provenance._COMMIT_RE` (external code review, low):
#: `head_commit` reaches `git log ... <head_commit>` as a bare argv element
#: with no `--`/`--end-of-options` terminator, so a value starting with `-`
#: would otherwise be parsed as a git option. Today's only caller passes
#: `git rev-parse HEAD` output, so this is not exploitable now -- validated
#: anyway, matching the sibling predicate's own belt-and-braces convention
#: for exactly this git-argv-injection shape.
_COMMIT_RE = re.compile(r"[0-9a-f]{40}")

#: Expected volume is "a handful of commits" (this repo's own merge cadence
#: closes the verified window in about an hour) — bounded well above that,
#: not tuned to it, so a genuinely quiet period still resolves.
DEFAULT_MAX_COMMITS = 50

#: Matches the GitHub Actions artifact/run retention horizon
#: ``ci_execution_evidence.py`` already documents as this mechanism's other
#: half — an anchor older than this could structurally verify but never
#: carry a usable execution-evidence artifact anyway.
DEFAULT_SINCE_DAYS = 90

#: Consecutive ``error`` verdicts (a query hiccup on ONE candidate, degrading
#: toward "keep looking" per the loop's own docstring below) before the walk
#: gives up rather than exhausting the full ``max_commits`` bound (Stage-3
#: doubt review, medium): a systemic condition — unauthenticated ``gh``,
#: offline, secondary rate-limited — otherwise burns up to ``max_commits``
#: worth of ``gh api`` subprocess spawns (2-3 each) to reach the exact same
#: ``unavailable`` outcome this many fewer would already establish, and
#: worsens the very rate-limit backoff it's failing on. A single-digit streak
#: is enough to distinguish "systemic" from "this one candidate" without
#: giving up on a genuinely spotty but partially-working query path.
_CONSECUTIVE_ERROR_LIMIT = 5


@dataclass(frozen=True)
class VerifiedAnchor:
    status: str  # "found" | "unavailable" | "error"
    detail: str
    commit: str | None = None
    depth: int | None = None  # 0 == head_commit itself


def _first_parent_history(
    head_commit: str, *, project_root: Path, max_commits: int, since_days: int,
) -> list[str] | None:
    """``head_commit`` and its first-parent ancestors, newest first, bounded
    by BOTH ``max_commits`` and ``since_days`` — ``None`` only when the ``git
    log`` process itself could not be run or exited non-zero (an unknown
    ``head_commit``, a corrupt repository, ...)."""
    try:
        result = subprocess.run(  # nosec B603,B607 - fixed argv, shell=False
            [
                "git", "-C", str(project_root), "log", "--first-parent",
                f"--max-count={max_commits}", f"--since={since_days} days ago",
                "--format=%H", head_commit,
            ],
            capture_output=True, text=True, timeout=_GIT_TIMEOUT_SECONDS,
            encoding="utf-8", errors="replace", check=False, shell=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def resolve_verified_anchor(
    head_commit: str, *, project_root: Path | str, workflow_file: str = "ci.yml",
    max_commits: int = DEFAULT_MAX_COMMITS, since_days: int = DEFAULT_SINCE_DAYS,
) -> VerifiedAnchor:
    """The newest commit at-or-before ``head_commit`` (first-parent only,
    bounded) that ``resolve_ci_verification`` reports ``verified`` for.

    Includes ``head_commit`` itself as the depth-0 candidate — a caller that
    already knows ``head_commit`` is unverified (the common case: this
    function exists to be tried only as a fallback) pays one redundant query
    for that certainty rather than special-casing it away, keeping this
    function's own contract simple and independently correct.
    """
    if not (isinstance(head_commit, str) and _COMMIT_RE.fullmatch(head_commit.lower())):
        return VerifiedAnchor("error", f"head_commit {head_commit!r} is not a 40 char hex SHA")
    # Normalised once, then used for BOTH the `git log` argv and every
    # returned `commit`/`detail` (Stage-3 doubt review, low): `git log
    # --format=%H` always emits lowercase, so an uppercase/mixed-case
    # `head_commit` would otherwise make the depth-0 candidate's `sha`
    # differ from the caller's own `head_commit` string by case alone —
    # defeating an `anchor.commit != sha` guard at the call site for no
    # real reason. Today's only caller already passes `resolve_head_sha`'s
    # lowercase output, so this is latent, not live -- fixed anyway, the
    # same "independently correct library surface" bar this module's own
    # docstring already holds itself to.
    head_commit = head_commit.lower()
    root = Path(project_root)
    history = _first_parent_history(
        head_commit, project_root=root, max_commits=max_commits, since_days=since_days,
    )
    if history is None:
        return VerifiedAnchor("error", f"could not walk first-parent history from {head_commit}")
    if not history:
        return VerifiedAnchor(
            "unavailable",
            f"first-parent history from {head_commit} within the last {since_days} days is empty",
        )

    # A query failure on ONE candidate must not abort the search — an older,
    # genuinely verified commit further back is still worth finding. Unlike
    # `resolve_ci_verification`'s own "one candidate errors -> the whole
    # commit is `error`" rule (that predicate is load-bearing for ONE
    # commit), this walk is itself a best-effort improvement layered on top
    # of an already-safe "unavailable" default — degrading toward
    # "unavailable" on a query hiccup is the conservative direction, never a
    # false `found`.
    consecutive_errors = 0
    for depth, sha in enumerate(history):
        verification = resolve_ci_verification(sha, project_root=root, workflow_file=workflow_file)
        if verification.status == "verified":
            return VerifiedAnchor("found", f"commit {sha} verified at depth {depth}", sha, depth)
        if verification.status == "error":
            consecutive_errors += 1
            if consecutive_errors >= _CONSECUTIVE_ERROR_LIMIT:
                return VerifiedAnchor(
                    "unavailable",
                    f"gave up after {consecutive_errors} consecutive query errors at depth "
                    f"{depth} of {head_commit}'s first-parent history (of {len(history)} "
                    "candidates within the bound) -- a systemic query fault, not a "
                    "per-candidate hiccup",
                )
        else:
            consecutive_errors = 0

    return VerifiedAnchor(
        "unavailable",
        f"no verified commit found within the first {len(history)} first-parent "
        f"ancestor(s) of {head_commit} (bounded at {max_commits} commits / {since_days} days)",
    )


__all__ = [
    "DEFAULT_MAX_COMMITS",
    "DEFAULT_SINCE_DAYS",
    "VerifiedAnchor",
    "resolve_verified_anchor",
]
