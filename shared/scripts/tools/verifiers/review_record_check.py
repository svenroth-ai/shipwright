"""F11 gate: every review type must have answered for itself.

**The rule is deliberately uniform — no review type may still be ``pending``.**

It would have been possible to re-encode the phase matrix here (self always,
code at medium+, doubt only on a non-trivial surface, …) and check each type
against the complexity it applies at. That was rejected: the matrix lives in the
iterate SKILL, it changes, and a second copy inside a verifier is a copy that
silently goes stale. Instead the gate demands an *active declaration* — a pass
that did not run is recorded as ``not_run`` / ``not_applicable`` with a
disposition naming the rule. Same coverage, nothing to drift.

The residual weakness is honest and known: a run could close every type as
``not_run`` and pass. A prompt-driven lifecycle cannot structurally prove who
decided to skip a pass. What IS enforced is that the skip is written down,
attributed, and names a rule — which turns a silent omission into a reviewable
claim in the diff.

Graduated like the Test Completeness Ledger: enforced at small+, skipped at
trivial. Fails closed on a missing, unreadable, or schema-invalid record — an
integrity fault must never present as a clean review history.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS_ROOT = Path(__file__).resolve().parents[2]
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from lib.iterate_entry import find_entry_by_run_id  # noqa: E402
from lib.review_record import (  # noqa: E402
    REVIEW_TYPES,
    ReviewRecordError,
    is_safe_run_id,
    pending_types,
    read_record,
    record_path,
)

from .common import CheckResult, Severity  # noqa: E402
from .git_helpers import _run_git  # noqa: E402

CHECK_NAME = "review record (all five review types closed)"

#: Complexities the gate applies at. Trivial runs still get a record if one is
#: written; they are simply not blocked for lacking one.
ENFORCED_COMPLEXITIES = ("small", "medium", "large")

_TOOL = "shared/scripts/tools/record_review_pass.py"


def _remediation(run_id: str, outstanding: list[str]) -> str:
    return (
        f"close each outstanding type — for a pass that ran: "
        f"`uv run {_TOOL} record --run-id {run_id} --review-type <type> "
        f"--status completed --from <adapter> --payload-file <reply>`; "
        f"for one that did not: `--status not_run|not_applicable --disposition "
        f"\"<the rule that applies>\"`. To close all "
        f"{len(outstanding)} at once: `uv run {_TOOL} close-missing --run-id "
        f"{run_id} --status not_run --disposition \"<reason>\"`."
    )


def check_review_record(project_root: Path, run_id: str, commit_hash: str = "") -> CheckResult:
    """Verify the run's review record exists and has no unanswered type."""
    entry = find_entry_by_run_id(project_root, run_id)
    complexity = str((entry or {}).get("complexity", "")).lower()
    if complexity not in ENFORCED_COMPLEXITIES:
        return CheckResult(
            CHECK_NAME, True, f"skipped (complexity={complexity or 'unknown'})",
            severity=Severity.SKIPPED.value,
        )

    try:
        record = read_record(project_root, run_id)
    except ReviewRecordError as exc:
        # `record_path` itself rejects an unsafe run_id, so it cannot be used
        # unguarded to build this message — the failure branch would raise the
        # very error it is reporting.
        where = str(record_path(project_root, run_id)) if is_safe_run_id(run_id) else "the record"
        return CheckResult(
            CHECK_NAME, False,
            f"the review record is unreadable or schema-invalid ({exc}) — a "
            "corrupt record must never be read as a clean review history. "
            f"Repair or delete {where} and re-record each pass with {_TOOL}.",
        )

    if record is None:
        return CheckResult(
            CHECK_NAME, False,
            f"no review record for {run_id} — the reviews of this run left no "
            "machine-readable trace, so the Mission view cannot tell 'not run' "
            f"from 'not recorded'. Run `uv run {_TOOL} init --run-id {run_id}`, "
            f"then {_remediation(run_id, list(REVIEW_TYPES))}",
        )

    outstanding = pending_types(record)
    if outstanding:
        return CheckResult(
            CHECK_NAME, False,
            f"{len(outstanding)} review type(s) still unanswered: "
            f"{', '.join(outstanding)} — {_remediation(run_id, outstanding)}",
        )

    committed = _committed_check(project_root, run_id, commit_hash)
    if committed is not None:
        return committed

    return CheckResult(CHECK_NAME, True, "all five review types are recorded")


def _committed_check(project_root: Path, run_id: str, commit_hash: str) -> CheckResult | None:
    """The record must be IN THE COMMIT, not merely in the working tree.

    Without this the gate is satisfiable by a file that never ships: F6 stages an
    explicit per-path list, the run dir is easy to omit, and the worktree is
    removed after the PR merges — so a green F11 would be compatible with the
    artifact vanishing, which is precisely the "nobody wrote it down" outcome the
    record exists to abolish. Mirrors ``check_events_has_commit``'s AC4 layer.

    Skipped when the path is untracked/gitignored in this project (nothing to
    assert) or when no commit is supplied.
    """
    if not commit_hash:
        return None
    rel = f".shipwright/planning/iterate/{run_id}/reviews.json"
    rc, _, _ = _run_git(project_root, "ls-files", "--error-unmatch", rel)
    if rc != 0:
        return None  # untracked here by policy — working-copy presence is all there is
    rc, _, _ = _run_git(project_root, "cat-file", "-e", f"{commit_hash}:{rel}")
    if rc == 0:
        return None
    return CheckResult(
        CHECK_NAME, False,
        f"the review record is tracked but is NOT in commit {commit_hash[:8]} — "
        "F6 did not stage it, so it would never reach the PR and would be lost "
        f"when the worktree is removed. Run `git add {rel}` and amend/commit.",
    )
