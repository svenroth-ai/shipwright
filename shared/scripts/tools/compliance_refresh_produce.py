#!/usr/bin/env python3
"""Recompute the seven compliance evidence documents, and refuse when it went wrong.

The producing half of the release-time / on-demand refresh (Weg B,
iterate-2026-07-31-derived-docs-at-release). :mod:`tools.refresh_compliance_docs`
is the delivering half — it decides where the result goes; this decides whether
there is a result worth delivering at all.

Three ways a refresh can be worse than leaving the documents frozen, one guard
each:

* **A pass that FAILED is not a pass that found nothing.** ``_update_compliance``
  swallows a non-zero exit, its own 30-second timeout and every exception,
  returning ``[]``; ``regenerate_tracked_snapshots`` then marks paths errored
  WITHOUT writing anything. An all-error pass therefore leaves the digest
  untouched, converges immediately, and reads as a clean fixpoint — green, frozen
  forever, no card. :func:`produce` checks the outcomes BEFORE the convergence
  verdict for exactly that reason.
* **One pass is not enough.** ``update_compliance`` collects once and runs
  generators in list order, so the RTM renders its layer-coverage cells from the
  ``test-traceability.json`` the same pass later overwrites: pass 1 ≠ pass 2,
  pass 2 == pass 3, measured from two different starting states.
* **A well-formed EMPTY document converges perfectly.** ``collect_git_history``
  returns ``[]`` on its 30-second timeout, rendering a change-history document
  with headers and no rows — replacing #480's "wrong by 11 commits" with "zero
  commits". So the content floor is judged against ``HEAD``, never against the
  previous pass: the failure it guards converges happily.

Which paths and how the floor is judged: :mod:`lib.compliance_refresh`. What each
document then SAYS about the state it describes: :mod:`tools.compliance_provenance`.
What this run may UNDO in the producer's own inputs: :mod:`tools.compliance_input_state`.

Trusted use only: runs repo-local generators. Every ``git`` call is an argv list.
"""

from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

# UNCONDITIONAL, matching `tools/resolve_churn_conflicts.py` — the sibling this
# module mirrors. A `if not in sys.path` guard skips the insert whenever the path
# is already present but sitting BEHIND a directory carrying its own `lib`/`tools`
# package, which is the ADR-045 collision that reads green locally and red in CI.
_SCRIPTS_DIR = Path(__file__).resolve().parent.parent  # shared/scripts
sys.path.insert(0, str(_SCRIPTS_DIR))

from lib.churn_merge import CI_SECURITY_SUMMARY  # noqa: E402
from lib.compliance_refresh import (  # noqa: E402
    PRODUCER_TARGETS,
    REFRESH_SET,
    SUCCESS_OUTCOMES,
    content_floor_violation,
    converged,
    failed_paths,
)
from tools.compliance_input_state import (  # noqa: E402
    PRODUCER_STATE,
    rewind,
    snapshot as snapshot_inputs,
)
from tools.compliance_provenance import (  # noqa: E402
    ci_security_report,
    stamp_fixed_point,
)

__all__ = [
    "MAX_PASSES", "capture", "converge", "digest", "floor_violations", "git",
    "head_blob", "produce", "regenerate",
]

MAX_PASSES = 4


def git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    # encoding="utf-8": text=True decodes through the Windows cp1252 locale and
    # mojibakes UTF-8 git output (matches the rest of the churn tooling).
    return subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True, text=True, encoding="utf-8", check=False,
    )


def head_blob(root: Path, rel: str) -> bytes | None:
    """The committed bytes of ``rel`` at ``HEAD``, or ``None`` if HEAD lacks it."""
    proc = subprocess.run(
        ["git", "-C", str(root), "show", f"HEAD:{rel}"],
        capture_output=True, check=False,
    )
    return proc.stdout if proc.returncode == 0 else None


def digest(root: Path) -> dict[str, str]:
    """Content hash per refresh path that exists. Absent paths are OMITTED rather
    than recorded as empty, so a pass that stops emitting one reads as drift
    rather than as convergence."""
    out: dict[str, str] = {}
    for rel in sorted(REFRESH_SET):
        path = root / rel
        if path.is_file():
            out[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
    return out


def capture(root: Path) -> dict[str, bytes]:
    """Read every refresh path that exists.

    Symlinks are skipped, never followed: reading through one would commit the
    TARGET's bytes to a public branch, and writing back through one would land
    content outside the repository (``finalize_iterate`` already refuses symlinks
    at these exact paths). A skipped path is absent from the payload, which the
    content floor then reads as a violation — fail closed."""
    out: dict[str, bytes] = {}
    for rel in sorted(REFRESH_SET):
        path = root / rel
        if path.is_symlink():
            continue
        if path.is_file():
            out[rel] = path.read_bytes()
    return out


def regenerate(root: Path, run_id: str) -> dict[str, str]:
    """One pass through the canonical producers — reused, never reimplemented.
    Returns ``{relpath: outcome}``, which the caller must not discard."""
    from tools.resolve_churn_conflicts import regenerate_tracked_snapshots

    return regenerate_tracked_snapshots(
        root, run_id, reason="compliance evidence refresh",
        only=set(PRODUCER_TARGETS),
    )


def converge(
    root: Path, run_id: str, *, max_passes: int = MAX_PASSES, regenerate=regenerate,
) -> tuple[bool, int, dict[str, str]]:
    """Regenerate until two consecutive passes agree on the tree-derived set.

    The loop stays even once the generator ordering that makes it necessary is
    fixed: a producer that silently stops converging must fail loudly rather than
    have whichever pass happened to run last committed. ``regenerate`` is injected
    so the LOOP is testable without the compliance plugin — the loop is the
    interesting behaviour here. Returns ``(converged, passes, last_outcomes)``."""
    inputs = snapshot_inputs(root, PRODUCER_STATE)
    left_alone: set[str] = set()
    previous: dict[str, str] | None = None
    outcomes: dict[str, str] = {}
    # A failure in ANY pass, not merely the last one. An errored leg writes
    # nothing, so the pass after it can succeed, change the digest, and the pass
    # after THAT can converge — leaving the caller holding only the final,
    # all-green outcomes while a real producer failure happened inside this loop.
    # AC-4 is about a pass that failed, not about the pass that happened to be
    # last (external code review, openai/high). First verdict per path wins: it is
    # the one nearest the cause.
    failures: dict[str, str] = {}
    try:
        for attempt in range(1, max_passes + 1):
            left_alone |= set(rewind(root, inputs, append_only=True))
            outcomes = regenerate(root, run_id) or {}
            for rel, outcome in outcomes.items():
                if outcome not in SUCCESS_OUTCOMES:
                    failures.setdefault(rel, outcome)
            current = digest(root)
            if previous is not None and converged(previous, current):
                return True, attempt, {**outcomes, **failures}
            previous = current
        return False, max_passes, {**outcomes, **failures}
    finally:
        # In a `finally`, because a producer that raises must not leave its
        # throwaway rewrite of the compliance config behind.
        left_alone |= set(rewind(root, inputs, append_only=True))
        # NOT discarded: an append-only log this run declined to rewind is a fact
        # the operator may need, and dropping it on the floor is how the first
        # version of this guard went unnoticed (Stage-3 doubt D1).
        converge.left_alone = sorted(left_alone)


def floor_violations(
    root: Path, payload: dict[str, bytes], *, allow_shrink: bool = False,
) -> dict[str, str]:
    """Refresh paths whose regenerated content lost material content vs ``HEAD``."""
    bad: dict[str, str] = {}
    for rel in sorted(REFRESH_SET):
        why = content_floor_violation(
            head_blob(root, rel), payload.get(rel), allow_shrink=allow_shrink,
        )
        if why:
            bad[rel] = why
    return bad


def produce(
    root: Path, run_id: str, base_sha: str, release: str | None, *,
    allow_shrink: bool = False,
) -> tuple[dict, dict[str, bytes]]:
    """Regenerate to a fixpoint and verify. Returns ``(result, payload)``.

    ``result["status"] == "ok"`` means every check passed and ``payload`` holds the
    bytes to deliver. Anything else is a refusal, ``payload`` is empty, and the
    caller must not deliver. The stamp is applied AFTER convergence, so the
    fixpoint is a property of the producer's own output rather than of a value
    this tool wrote into it.

    **Every refusal rewinds the seven to the state this call found them in** — not
    to ``HEAD``. The ``--stage`` path has no clean-tree preflight, so an operator
    may legitimately be holding an edit to one of these documents; resetting to
    ``HEAD`` would discard it while cleaning up after a refusal that was not their
    fault (external code review, openai/medium). Same reasoning as the producer-
    input rewind, one level up.
    """
    before = snapshot_inputs(root, REFRESH_SET)
    reached, passes, outcomes = converge(root, run_id)

    result: dict = {
        "base": base_sha, "release": release, "passes": passes,
        "converged": reached, "outcomes": outcomes,
    }
    # Surfaced, not merely recorded: an append-only log this run declined to rewind
    # means somebody else wrote to it while the producer ran, and the operator is
    # the only one who can judge whether that matters. `getattr` because a test may
    # stub `converge` entirely.
    left_alone = getattr(converge, "left_alone", None)
    if left_alone:
        result["inputs_left_alone"] = left_alone
    # AC-6: `ci-security.json` never fails the run. Today it cannot fail alone —
    # one `_update_compliance` call decides all seven together — but stating the
    # carve-out makes the acceptance criterion true by construction rather than by
    # accident of the producer's coupling, which is exactly what would break
    # silently if that producer ever reported per-path outcomes (external code
    # review, openai/high). Its state is reported instead, below.
    failed = [rel for rel in failed_paths(outcomes) if rel != CI_SECURITY_SUMMARY]
    if failed:
        rewind(root, before)
        # BEFORE the convergence verdict: an all-error pass writes nothing, so it
        # converges immediately and would otherwise be reported as a success.
        result["status"] = "producer_failed"
        result["failed"] = failed
        return result, {}
    if not reached:
        rewind(root, before)
        result["status"] = "not_converged"
        return result, {}

    payload, result["stamped"] = stamp_fixed_point(capture(root), base_sha, release)
    violations = floor_violations(root, payload, allow_shrink=allow_shrink)
    if violations:
        rewind(root, before)
        result["status"] = "content_floor"
        result["violations"] = violations
        return result, {}
    if allow_shrink:
        # WHICH documents the override actually covered, not merely that the flag
        # was passed. A boolean cannot tell "a document halved and we let it" from
        # "the flag was passed and never mattered", and only the first is worth
        # anyone's attention (Stage-1 spec review, HIGH-2). The strict re-run names
        # exactly the paths the lenient one forgave: the run reached here, so it
        # carries no unwaivable empty-floor violation.
        result["allow_shrink"] = {"waived": sorted(floor_violations(root, payload))}
    result["status"] = "ok"
    result["ci_security"] = ci_security_report(root, base_sha)
    if CI_SECURITY_SUMMARY in failed_paths(outcomes):
        # Carved out of the refusal above, so it is said out loud here instead.
        result["ci_security"]["producer_outcome"] = outcomes[CI_SECURITY_SUMMARY]
        result["ci_security"]["stale"] = None
        result["ci_security"]["note"] = (
            f"its producer reported {outcomes[CI_SECURITY_SUMMARY]!r}; the committed "
            "copy stands. Not a blocker — a release is never held for a scan."
        )
    return result, payload
