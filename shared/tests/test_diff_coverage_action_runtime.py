"""Runtime behavior of the ``diff-coverage-gate`` action's shell body.

``test_diff_coverage_action.py`` locks the action's *static* contract (inputs,
defaults, SHA-pin, injection-safety). That does not prove the shell WIRING is
right: the ``origin/<branch>`` fetch-target derivation, the space-separated
``coverage-files`` split into distinct argv, and the pinned ``diff-cover@``
invocation are new logic (an external-review finding flagged the compare-branch
handling specifically). This test executes the action's *actual* ``run:`` body —
extracted from ``action.yml`` so a copy can't drift — with ``git`` and ``uvx``
shadowed by bash functions that record their argv. We assert the exact fetch
target and diff-cover argv for single-file, two-file, and non-default-origin
inputs.

The gate DECISION (diff-cover exit semantics) is proven separately against real
diff-cover in ``shared/scripts/tools/tests/test_measure_diff_coverage_gate.py``;
here we only prove the wiring hands diff-cover the right arguments.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

REPO_ROOT = Path(__file__).resolve().parents[2]
ACTION_PATH = REPO_ROOT / ".github/actions/diff-coverage-gate/action.yml"

_BASH = shutil.which("bash")


def _require_bash() -> str:
    # Single explicit return at the tail (guard-clause style) — the not-bash
    # branch always raises, so there is no implicit fall-through returning None.
    if not _BASH:
        # Silent-skip CI-discipline: the action's shell body is bash; every CI
        # runner (ubuntu + windows git-bash) has it, so an absent bash in CI is
        # a provisioning bug, not a reason to quietly skip the wiring proof.
        if os.environ.get("CI", "").lower() in ("true", "1"):
            pytest.fail(
                "bash unavailable in CI — the diff-coverage action's shell body "
                "cannot be exercised. ubuntu-latest / windows-latest both ship bash."
            )
        pytest.skip("bash unavailable; install Git Bash to run this test.")
    return _BASH


def _gate_run_body() -> str:
    action = yaml.safe_load(ACTION_PATH.read_text(encoding="utf-8"))
    steps = (action.get("runs") or {}).get("steps") or []
    for s in steps:
        run = s.get("run") if isinstance(s, dict) else None
        if isinstance(run, str) and "diff-cover@" in run:
            return run
    raise AssertionError("no composite step running diff-cover found in action.yml")


# Shadow git + uvx with bash functions that append their argv (one token per
# line) to log files, then run the real extracted body. Function definitions
# win over external commands, so no PATH shim / no real fetch happens.
_HARNESS = (
    'git() {{ printf "%s\\n" "$@" >> "$GIT_LOG"; }}\n'
    'uvx() {{ printf "%s\\n" "$@" >> "$UVX_LOG"; }}\n'
    "{body}\n"
)


def _exec(tmp_path: Path, compare_branch: str, coverage_files: str) -> tuple[list[str], list[str]]:
    bash = _require_bash()
    git_log = tmp_path / "git.log"
    uvx_log = tmp_path / "uvx.log"
    prog = _HARNESS.format(body=_gate_run_body())
    env = {
        **os.environ,
        "INPUT_COMPARE_BRANCH": compare_branch,
        "INPUT_COVERAGE_FILES": coverage_files,
        "INPUT_FAIL_UNDER": "80",
        "INPUT_DIFF_COVER_VERSION": "10.3.0",
        "GIT_LOG": str(git_log),
        "UVX_LOG": str(uvx_log),
    }
    subprocess.run([bash, "-c", prog], env=env, check=True, capture_output=True, text=True)
    git_argv = git_log.read_text(encoding="utf-8").splitlines() if git_log.exists() else []
    uvx_argv = uvx_log.read_text(encoding="utf-8").splitlines() if uvx_log.exists() else []
    return git_argv, uvx_argv


class TestDiffCoverageActionRuntime:
    @pytest.mark.parametrize(
        "compare_branch,coverage_files,base,files",
        [
            ("origin/main", "coverage/cobertura-coverage.xml", "main",
             ["coverage/cobertura-coverage.xml"]),
            ("origin/main",
             "client/coverage/cobertura-coverage.xml server/coverage/cobertura-coverage.xml",
             "main",
             ["client/coverage/cobertura-coverage.xml", "server/coverage/cobertura-coverage.xml"]),
            ("origin/develop", "coverage/cobertura-coverage.xml", "develop",
             ["coverage/cobertura-coverage.xml"]),
        ],
    )
    def test_wiring(
        self,
        tmp_path: Path,
        compare_branch: str,
        coverage_files: str,
        base: str,
        files: list[str],
    ) -> None:
        git_argv, uvx_argv = _exec(tmp_path, compare_branch, coverage_files)

        assert git_argv == ["fetch", "--no-tags", "origin", base], (
            f"fetch target wrong for {compare_branch!r}: got {git_argv!r}. The "
            f"action must fetch `<branch>` (origin/ stripped) so diff-cover's "
            f"--compare-branch ref exists."
        )
        # diff-cover@<pinned-version>, then each cobertura path as its own arg,
        # then the gate flags — proving both the pin threading and the split.
        expected = (
            ["diff-cover@10.3.0"]
            + files
            + [f"--compare-branch={compare_branch}", "--fail-under=80"]
        )
        assert uvx_argv == expected, (
            f"diff-cover argv wrong for files={coverage_files!r}: got {uvx_argv!r}, "
            f"expected {expected!r}."
        )
