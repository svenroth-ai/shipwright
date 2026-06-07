"""F0.5 runner-shape validation (surface_verification.run_with_retries).

The F0.5 orchestrator runs the ``--runner`` with ``shell=False``, so a compound
shell command (``cd … && …``) used to die with a cryptic FileNotFoundError /
WinError 2 after burning the whole retry budget. These tests pin the fail-fast,
actionable-error behavior. Kept in their own module so the already-oversized
``test_surface_verification.py`` (bloat-baselined) isn't grown further.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Belt-and-suspenders with conftest: shared/scripts on path for the import.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from surface_verification import run_with_retries  # noqa: E402


def test_compound_shell_runner_fails_fast_with_hint(tmp_path):
    """A `cd … && …` runner can't work (no shell): fail fast (0 attempts) with
    an actionable message instead of a cryptic WinError after 3 retries."""
    exit_code, output, attempts = run_with_retries(
        "cd plugins/shipwright-iterate && uv run pytest tests/ -q",
        cwd=tmp_path,
        retry_cap=3,
    )
    assert exit_code != 0
    assert attempts == 0  # no wasted retries
    assert "no shell" in output.lower()  # actionable hint
    assert "&&" in output  # names the offending operator


def test_cd_builtin_runner_rejected_with_hint(tmp_path):
    """A runner that *starts* with the `cd` shell builtin is rejected the same
    way (the builtin isn't an executable on PATH)."""
    exit_code, output, attempts = run_with_retries(
        "cd subdir", cwd=tmp_path, retry_cap=3,
    )
    assert exit_code != 0
    assert attempts == 0
    assert "no shell" in output.lower()


def test_single_executable_runner_still_runs(tmp_path):
    """Guard against false-positive rejection: a plain single-executable runner
    (the supported form) still executes normally."""
    exit_code, _output, attempts = run_with_retries(
        [sys.executable, "-c", "print('=== 1 passed in 0.0s ===')"],
        cwd=tmp_path,
    )
    assert exit_code == 0
    assert attempts == 1
