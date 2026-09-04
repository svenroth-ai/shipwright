"""Integration tests for the `trap 'ec=$?; ... cleanup ...; exit "$ec"' EXIT`
shell idiom used by `code-review.md` Step 6c, `iteration-reviews.md` Branch A,
and `sub-iterate-runner.md` Step 2 to guarantee review_scratch.py cleanup
across every exit path. Split out of test_review_scratch.py (PR #676
round-4 external-review finding) — see that file for the unit-level
resolve()/cleanup() coverage this complements."""

from __future__ import annotations

import os
import shutil
import subprocess  # nosec B404 - fixed argv, shell=False
from pathlib import Path
from uuid import uuid4

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[4]
_CLI = _REPO_ROOT / "shared" / "scripts" / "tools" / "review_scratch.py"


def _bash() -> str:
    """Find the Bash paired with Git when Windows exposes only git.exe."""
    if os.name == "nt":
        git = shutil.which("git")
        if git:
            candidate = Path(git).resolve().parent.parent / "bin" / "bash.exe"
            if candidate.is_file():
                return str(candidate)
        for variable in ("ProgramFiles", "ProgramW6432", "ProgramFiles(x86)"):
            candidate = Path(os.environ.get(variable, "")) / "Git" / "bin" / "bash.exe"
            if candidate.is_file():
                return str(candidate)
    resolved = shutil.which("bash")
    if resolved:
        return resolved
    pytest.skip("bash is required to exercise the shell trap pattern")
    raise AssertionError("pytest.skip() must not return")


def _run_trap_pattern(run_id: str, *, review_exit: int) -> subprocess.CompletedProcess:
    """A fake "review command" with a controlled exit code stands in for
    `external_review.py`."""
    script = (
        f'DIFF_FILE="$(uv run "{_CLI}" resolve --run-id "{run_id}" --name diff.txt)"\n'
        f'trap \'ec=$?; uv run "{_CLI}" cleanup --run-id "{run_id}"; exit "$ec"\' EXIT\n'
        f"echo payload > \"$DIFF_FILE\"\n"
        f"exit {review_exit}\n"
    )
    return subprocess.run(  # nosec B603 - fixed argv, shell=False
        [_bash(), "-c", script],
        cwd=_REPO_ROOT, capture_output=True, text=True, check=False, timeout=60,
    )


def test_trap_preserves_a_failed_review_commands_exit_status():
    # PR #676 round-4 external-review finding: a trap whose own cleanup
    # command succeeds becomes bash's new "last command run", so without
    # `ec=$?` ... `exit "$ec"` the trap silently turns a failed review into
    # an apparent success.
    run_id = f"iterate-trap-fail-{uuid4().hex[:12]}"
    try:
        result = _run_trap_pattern(run_id, review_exit=17)
        assert result.returncode == 17, result.stderr
    finally:
        subprocess.run(  # nosec B603 - fixed argv, shell=False
            ["uv", "run", str(_CLI), "cleanup", "--run-id", run_id],
            cwd=_REPO_ROOT, capture_output=True, text=True, check=False, timeout=60,
        )


def test_trap_cleans_up_the_scratch_diff_on_a_failed_review():
    run_id = f"iterate-trap-cleanup-{uuid4().hex[:12]}"
    result = _run_trap_pattern(run_id, review_exit=1)
    assert result.returncode == 1, result.stderr
    check = subprocess.run(  # nosec B603 - fixed argv, shell=False
        ["uv", "run", str(_CLI), "resolve", "--run-id", run_id, "--name", "diff.txt"],
        cwd=_REPO_ROOT, capture_output=True, text=True, check=False, timeout=60,
    )
    try:
        assert check.returncode == 0, check.stderr
        assert not Path(check.stdout.strip()).exists(), (
            "trap must remove the scratch diff even when the review command failed"
        )
    finally:
        subprocess.run(  # nosec B603 - fixed argv, shell=False
            ["uv", "run", str(_CLI), "cleanup", "--run-id", run_id],
            cwd=_REPO_ROOT, capture_output=True, text=True, check=False, timeout=60,
        )


def test_trap_preserves_a_successful_review_commands_exit_status():
    run_id = f"iterate-trap-ok-{uuid4().hex[:12]}"
    try:
        result = _run_trap_pattern(run_id, review_exit=0)
        assert result.returncode == 0, result.stderr
    finally:
        subprocess.run(  # nosec B603 - fixed argv, shell=False
            ["uv", "run", str(_CLI), "cleanup", "--run-id", run_id],
            cwd=_REPO_ROOT, capture_output=True, text=True, check=False, timeout=60,
        )

