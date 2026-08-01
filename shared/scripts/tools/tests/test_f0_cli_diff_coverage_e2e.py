"""AC-8 through the actual F0 surface: `run_test_suite.py --project-root <repo>`.

The sibling `test_f0_diff_coverage_e2e.py` proves the GATE bites, but it calls
`run_gate` directly and produces coverage with the `coverage` API — so it would
still pass if the runner-level wiring were broken: per-unit `--cov` args, the
per-subprocess `COVERAGE_FILE`, `SuiteResult.cov_files`, or `main`'s invocation of
the gate. Raised by external review (GPT), and correct: a gate proven only below
its own entry point is not proven.

So this drives the real CLI end to end — real unit discovery, a real `uv run pytest`
per unit with real pytest-cov instrumentation, the real combine, the real pinned
diff-cover — over a synthetic repo whose diff is a NEW, uncovered function. The
assertions are the exit codes F0 actually returns: 4 while the changed lines are
uncovered, 0 once a test covers them. Nothing is mocked.

Deliberately ONE covering step rather than a matrix: this spawns real uv
environments and sits on F0's critical path in a test root that is not
xdist-allowlisted. It is also, deliberately, not marked `slow` — the shared units
run `-m "not slow and not cross_plugin"`, so a `slow` mark would quietly remove the
only end-to-end proof of the surface.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_SHARED = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_SHARED))

from scripts.tools.suite_units import UV_RUN

_RUNNER = _SHARED / "scripts" / "tools" / "run_test_suite.py"
_HAS_GIT = shutil.which("git") is not None
_HAS_UV = shutil.which("uv") is not None
_GIT_ENV = {
    **os.environ,
    "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t.invalid",
    "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t.invalid",
}
#: What `run_test_suite.py` needs on disk to run standalone in a synthetic repo.
_RUNNER_FILES = (
    "scripts/lib/atomic_write.py",
    "scripts/lib/diff_coverage_gate.py",
    "scripts/tools/measure_diff_coverage.py",
    "scripts/tools/combine_coverage.py",
    "scripts/tools/run_test_suite.py",
    "scripts/tools/suite_coverage.py",
    "scripts/tools/suite_coverage_rules.py",
    "scripts/tools/suite_report.py",
    "scripts/tools/suite_race_triage.py",
    "scripts/tools/suite_units.py",
)
_PLUGIN = "shipwright-synthetic"
#: `relative_files` is what lets diff-cover match coverage entries against git
#: paths; `omit` keeps the unit's own tests out of the measurement, exactly as the
#: real root pyproject does.
_PYPROJECT = (
    "[tool.coverage.run]\n"
    "relative_files = true\n"
    'omit = ["*/tests/*"]\n'
)
_EXIT_COVERAGE_GATE = 4


def _require_real_tools() -> None:
    if _HAS_GIT and _HAS_UV:
        return
    if os.environ.get("CI", "").lower() in ("true", "1"):
        pytest.fail("git/uv unavailable in CI — the F0 CLI surface cannot be "
                    "proven end to end; fix the runner image, do not skip this.")
    pytest.skip("git or uv unavailable")


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=str(cwd), env=_GIT_ENV,
                   capture_output=True, text=True, check=True)


def _write(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def _synth_repo(root: Path) -> None:
    """A repo `discover_units` recognises: one plugin with pyproject + tests +
    scripts, a root pyproject carrying the coverage config, and a `suite` block so
    the runner is opt-in-satisfied. Plus a real `origin/main` to diff against."""
    for rel in _RUNNER_FILES:
        dst = root / "shared" / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(_SHARED / rel, dst)
    _write(root / "pyproject.toml", _PYPROJECT)
    _write(root / "shipwright_test_config.json", '{"suite": {}}')
    _write(root / ".gitignore", ".cov-data/\ncoverage.xml\n.coverage*\n")
    plug = root / "plugins" / _PLUGIN
    _write(plug / "pyproject.toml", "[project]\nname='synthetic'\nversion='0'\n")
    _write(plug / ".python-version", "3.11\n")
    _write(plug / "scripts" / "m.py", "def a():\n    return 1\n")
    _write(plug / "tests" / "test_m.py",
           "import sys, pathlib\n"
           "sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'scripts'))\n"
           "import m\n\n\n"
           "def test_a():\n    assert m.a() == 1\n")

    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "core.autocrlf", "false")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "base")
    bare = root.parent / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", str(bare)],
                   env=_GIT_ENV, capture_output=True, check=True)
    _git(root, "remote", "add", "origin", str(bare))
    _git(root, "push", "-q", "origin", "main")
    _git(root, "fetch", "-q", "origin", "main")

    # THE CHANGE UNDER TEST: a new, entirely untested function. Left UNCOMMITTED on
    # purpose — that is the state F0 actually runs in (it fires before F6), and it
    # is what `--include-untracked` exists to make visible.
    _write(plug / "scripts" / "m.py",
           "def a():\n    return 1\n\n\ndef b():\n    return 2\n\n\ndef c():\n    return 3\n")


def _run_f0(root: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [*UV_RUN, "--with", "pytest", str(root / "shared/scripts/tools/run_test_suite.py"),
         "--project-root", str(root)],
        cwd=str(root), env=_GIT_ENV, capture_output=True, text=True, timeout=900)


@pytest.fixture(scope="module")
def repo(tmp_path_factory) -> Path:
    _require_real_tools()
    root = tmp_path_factory.mktemp("cli") / "repo"
    root.mkdir()
    _synth_repo(root)
    return root


def test_the_f0_cli_stops_on_an_under_covered_diff_then_passes_once_covered(repo):
    """The whole claim, through the real entry point, in one ordered pair.

    Ordered rather than split into two tests because the second assertion is only
    meaningful against the first: identical repo, identical command, and the ONLY
    thing that changes between them is whether a test covers the new lines. That is
    what makes exit 4 attributable to coverage rather than to setup.
    """
    red = _run_f0(repo)
    combined = red.stdout + red.stderr
    assert red.returncode == _EXIT_COVERAGE_GATE, combined[-3000:]
    assert "diff-coverage: FAILED" in combined, combined[-3000:]

    # Cover b() and c() — nothing else about the repo or the command changes.
    plug = repo / "plugins" / _PLUGIN
    _write(plug / "tests" / "test_m.py",
           (plug / "tests" / "test_m.py").read_text(encoding="utf-8")
           + "\n\ndef test_b_and_c():\n    assert m.b() == 2\n    assert m.c() == 3\n")

    green = _run_f0(repo)
    combined = green.stdout + green.stderr
    assert green.returncode == 0, combined[-3000:]
    assert "diff-coverage: PASS" in combined, combined[-3000:]
