"""F11 gate for the tracked immutable per-run test-results artifact."""

from __future__ import annotations

from pathlib import Path

from lib.iterate_test_results import EvidenceError, evidence_file_for, validate_evidence_bytes
from lib.iterate_entry import RUN_ID_STRICT

from .common import CheckResult, Severity
from .git_blob_read import GitReadError, committed_bytes_reader
from .test_results_backfill_check import check_test_results_backfill
from .git_helpers import _git_available


def check_test_results_evidence(
    project_root: Path, run_id: str, commit_hash: str = ""
) -> CheckResult:
    """Require valid attributed evidence, and require it in HEAD when possible."""
    name = "immutable per-run test results committed"
    root = Path(project_root).resolve()
    if not isinstance(run_id, str) or RUN_ID_STRICT.fullmatch(run_id) is None:
        return CheckResult(
            name,
            True,
            f"legacy run skipped: noncanonical run_id {run_id!r}",
            severity=Severity.SKIPPED.value,
        )
    try:
        target = evidence_file_for(root, run_id)
    except EvidenceError as exc:
        return CheckResult(name, False, f"unsafe evidence path: {exc}")
    if target.is_symlink() or not target.is_file():
        return CheckResult(name, False, f"missing regular evidence file: {target.name}")
    try:
        working = target.read_bytes()
        validate_evidence_bytes(working, run_id)
    except (EvidenceError, OSError) as exc:
        return CheckResult(name, False, f"invalid working evidence: {exc}")
    if not commit_hash or not _git_available(root):
        return CheckResult(
            name, True, f"{target.name} valid; committed check skipped",
            severity=Severity.SKIPPED.value,
        )
    rel = target.relative_to(root).as_posix()
    try:
        committed = committed_bytes_reader(root, commit_hash)(rel)
    except GitReadError as exc:
        return CheckResult(name, False, str(exc))
    if committed is None:
        return CheckResult(
            name, False,
            f"{rel} is valid in the worktree but absent from {commit_hash[:8]} — "
            "F6 must stage the iterates directory",
        )
    try:
        validate_evidence_bytes(committed, run_id)
    except EvidenceError as exc:
        return CheckResult(name, False, f"committed evidence invalid: {exc}")
    if committed != working:
        return CheckResult(name, False, "committed evidence differs from working evidence")
    return CheckResult(name, True, f"{rel} valid and committed in {commit_hash[:8]}")


__all__ = ["check_test_results_backfill", "check_test_results_evidence"]
