"""The review-record check's ``unavailable`` half: evidence, and saying so out loud.

Two jobs, both for a pass closed with ``reason_code: unavailable``:

1. :func:`unavailable_evidence` — an adapter-backed pass (``plan``,
   ``external_code``) must carry the adapter's captured error
   (``lib.review_unavailable``). When the record itself is committed, the
   evidence is read from THAT commit, byte for byte — a working-tree file that
   never ships, or one that differs from what ships, proves nothing; a symlink
   is refused on both sides. There is no gitignore exemption of its own: the
   artifact is required exactly where the record is.
2. :func:`unavailable_note` — a passing check still names every ``unavailable``
   pass in its detail line, so F11's output says "the external review did not
   run" instead of a bare "every review pass is recorded".
"""

from __future__ import annotations

from pathlib import Path

from lib.review_unavailable import artifact_problem, unavailable_adapter_rows, unavailable_rows, worktree_reader

from .common import CheckResult
from .git_blob_read import GitReadError, committed_bytes_reader
from .git_helpers import _run_git
from .review_record_floor import CHECK_NAME

__all__ = ["unavailable_evidence", "unavailable_note"]


def _record_is_committed(project_root: Path, run_id: str, commit_hash: str) -> bool:
    rel = f".shipwright/planning/iterate/{run_id}/reviews.json"
    rc, _, _ = _run_git(project_root, "cat-file", "-e", f"{commit_hash}:{rel}")
    return rc == 0


def unavailable_evidence(
    project_root: Path, record: dict, run_id: str, commit_hash: str = "",
) -> CheckResult | None:
    """``None`` when every adapter-backed ``unavailable`` row is backed by its capture."""
    rows = unavailable_adapter_rows(record)
    if not rows:
        return None
    committed = bool(commit_hash) and _record_is_committed(project_root, run_id, commit_hash)
    read = (committed_bytes_reader(project_root, commit_hash) if committed  # a symlink blob raises
            else worktree_reader(project_root))
    where = f" in commit {commit_hash[:8]}" if committed else " in the working tree"
    problems: list[str] = []
    for review_type in rows:
        try:
            problem, _ = artifact_problem(run_id, review_type, read)
        except GitReadError as exc:
            problem = f"the capture could not be read ({exc})"
        if problem:
            problems.append(f"`{review_type}`: {problem}")
    if not problems:
        return None
    return CheckResult(
        CHECK_NAME, False,
        f"{len(problems)} adapter-backed pass(es) closed `unavailable` without the "
        f"adapter's captured error{where} — {'; '.join(problems)}. `unavailable` claims "
        "the reviewer could not run; the claim needs the adapter's own failure output "
        "(stage it with the record), or re-run the review and record it completed.",
    )


def unavailable_note(record: dict) -> str:
    """``""``, or a suffix naming every pass closed ``unavailable`` (loud even on a pass)."""
    rows = unavailable_rows(record)
    if not rows:
        return ""
    return (f" — NOTE: {len(rows)} pass(es) did NOT run (unavailable): {', '.join(rows)}; "
            "the PR body and the F12 summary must carry review_unavailable_note.py's line")
