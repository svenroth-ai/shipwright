"""Source-stability and diff-coverage verdict orchestration for F0."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from scripts.tools.suite_coverage import (
    GATE_FAILED,
    GateResult,
    build_worktree_diff,
    compare_branch,
    run_gate,
)


def _source_snapshot_error(root: Path, expected: str | None, *,
                           fingerprint: Callable) -> str:
    current, error = fingerprint(root)
    if error:
        return error
    if current != expected:
        return ("Python sources or test/coverage configuration changed while "
                "coverage was being measured; re-run F0 on the final working tree")
    return ""


def gate_green_suite(root: Path, result, source_before: str | None, *,
                     fingerprint: Callable) -> GateResult:
    error = _source_snapshot_error(root, source_before, fingerprint=fingerprint)
    if error:
        return GateResult(GATE_FAILED, [f"diff-coverage: FAILED - {error}."])
    branch = compare_branch(root)
    if branch is None:
        return run_gate(root, expected=result.cov_files, branch=None,
                        diff_file=None, suite_green=True)
    error = _source_snapshot_error(root, source_before, fingerprint=fingerprint)
    if error:
        return GateResult(GATE_FAILED, [f"diff-coverage: FAILED - {error}."])
    diff_file, diff_error = build_worktree_diff(root, branch)
    error = diff_error or _source_snapshot_error(
        root, source_before, fingerprint=fingerprint)
    if error:
        return GateResult(GATE_FAILED, [f"diff-coverage: FAILED - {error}."])
    gate = run_gate(root, expected=result.cov_files, branch=branch,
                    diff_file=diff_file, suite_green=True)
    error = _source_snapshot_error(root, source_before, fingerprint=fingerprint)
    return (GateResult(GATE_FAILED, [f"diff-coverage: FAILED - {error}."])
            if error else gate)
