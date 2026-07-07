"""The diff-coverage composite action's gate actually BITES with real diff-cover.

``test_diff_coverage_action_runtime.py`` proves the action's shell WIRING (argv,
fetch target) by shadowing ``git``/``uvx``. That leaves one load-bearing claim
unproven in-repo: that the action's ``uvx diff-cover@10.3.0 … --fail-under=80``
call exits **non-zero on an under-covered diff and zero on a covered one** — the
exact decision the monorepo's HARD merge gate now rests on (Stage 3 self-consume,
iterate-2026-07-07-diff-coverage-self-consume), and that all three consumers
(adopt templates, WebUI, monorepo) inherit.

This test executes the action's *actual* ``run:`` body — extracted from
``action.yml`` so a copy can't drift — with the **real** ``uvx diff-cover`` against
a synthetic git repo (bare origin + a feature change) whose changed lines are
either covered or not. It asserts the gate exit code, closing the "testable ⇒
tested" gap the runtime test structurally cannot.
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
_GIT = shutil.which("git")
_UVX = shutil.which("uvx") or shutil.which("uv")

# A cobertura report over mod.py: changed lines {4,5}; line 5's hit count is
# parametrised so the changed-line coverage is 100% (covered) or 50% (< 80%).
_COVERAGE_XML = (
    '<?xml version="1.0" ?>\n'
    '<coverage line-rate="0.8" version="7.0" timestamp="0"><packages>\n'
    '<package name="." line-rate="0.8"><classes>\n'
    '<class name="mod.py" filename="mod.py" line-rate="0.8"><lines>\n'
    '<line number="1" hits="1"/><line number="2" hits="1"/>\n'
    '<line number="4" hits="1"/><line number="5" hits="{hit5}"/>\n'
    "</lines></class></classes></package></packages></coverage>\n"
)


def _require_tools() -> None:
    if _BASH and _GIT and _UVX:
        return
    # Silent-skip CI-discipline: the shared-tests CI step provisions uv + git +
    # bash + diff-cover, so a missing tool in CI is a provisioning bug, not a
    # reason to quietly skip the gate-bites proof.
    if os.environ.get("CI", "").lower() in ("true", "1"):
        pytest.fail(
            "bash/git/uvx unavailable in CI — cannot exercise the diff-coverage "
            "action's real gate. The shared-tests step must provision them."
        )
    pytest.skip("bash/git/uvx unavailable; install them + diff-cover to run.")


def _gate_run_body() -> str:
    action = yaml.safe_load(ACTION_PATH.read_text(encoding="utf-8"))
    for s in (action.get("runs") or {}).get("steps") or []:
        run = s.get("run") if isinstance(s, dict) else None
        if isinstance(run, str) and "diff-cover@" in run:
            return run
    raise AssertionError("no diff-cover step found in action.yml")


def _git(cwd: Path, *args: str) -> None:
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    subprocess.run([_GIT, *args], cwd=str(cwd), env=env, check=True,
                   capture_output=True, text=True)


class TestDiffCoverageActionGateBites:
    @pytest.mark.parametrize("covered,expect_zero", [(True, True), (False, False)])
    def test_gate_exit_code(self, tmp_path: Path, covered: bool, expect_zero: bool) -> None:
        _require_tools()
        origin = tmp_path / "origin.git"
        repo = tmp_path / "repo"
        subprocess.run([_GIT, "init", "-q", "--bare", str(origin)], check=True,
                       capture_output=True, text=True)
        repo.mkdir()
        _git(repo, "init", "-q", "-b", "main")
        _git(repo, "config", "core.autocrlf", "false")
        (repo / "mod.py").write_text("def a():\n    return 1\n", encoding="utf-8")
        _git(repo, "add", "-A")
        _git(repo, "commit", "-q", "-m", "base")
        _git(repo, "remote", "add", "origin", str(origin))
        _git(repo, "push", "-q", "origin", "main")
        # Feature change: add def b() → changed lines 4,5.
        (repo / "mod.py").write_text(
            "def a():\n    return 1\n\ndef b():\n    return 2\n", encoding="utf-8")
        (repo / "coverage.xml").write_text(
            _COVERAGE_XML.format(hit5="1" if covered else "0"), encoding="utf-8")
        _git(repo, "add", "-A")
        _git(repo, "commit", "-q", "-m", "feature")

        env = {
            **os.environ,
            "INPUT_COMPARE_BRANCH": "origin/main",
            "INPUT_COVERAGE_FILES": "coverage.xml",
            "INPUT_FAIL_UNDER": "80",
            "INPUT_DIFF_COVER_VERSION": "10.3.0",
        }
        proc = subprocess.run(
            [_BASH, "-c", _gate_run_body()], cwd=str(repo), env=env,
            capture_output=True, text=True,
        )
        if expect_zero:
            assert proc.returncode == 0, (
                f"covered diff (100%) must PASS the gate; got exit "
                f"{proc.returncode}\n{proc.stdout}\n{proc.stderr}"
            )
        else:
            assert proc.returncode != 0, (
                f"under-covered diff (50% < 80%) must FAIL the gate; got exit 0\n"
                f"{proc.stdout}\n{proc.stderr}"
            )
