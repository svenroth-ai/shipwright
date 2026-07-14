"""AC2 parity guard — the F0 runner and ci.yml must select the SAME test units.

CI deliberately stays SERIAL (it is the independent cross-check that would catch a
parallel-only false green — see references/F0.md). That only works while both sides
run the same units. This guard fails if ci.yml stops using the selection rule the
runner re-implements, forcing a conscious re-sync instead of silent drift.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from scripts.tools.suite_units import INTEGRATION_DIR, SHARED_TEST_DIRS, discover_units

_REPO_ROOT = Path(__file__).resolve().parents[4]
_CI = _REPO_ROOT / ".github" / "workflows" / "ci.yml"

pytestmark = pytest.mark.skipif(not _CI.is_file(), reason="ci.yml not present (not the monorepo)")


@pytest.fixture(scope="module")
def ci_text() -> str:
    return _CI.read_text(encoding="utf-8")


def test_ci_still_loops_plugins_on_pyproject_plus_tests(ci_text):
    """The runner's plugin rule: plugins/*/ having pyproject.toml AND tests/."""
    assert "for plugin in plugins/*/" in ci_text
    assert '[ -f "$plugin/pyproject.toml" ]' in ci_text
    assert '[ -d "$plugin/tests" ]' in ci_text


def test_ci_still_runs_the_same_shared_dirs(ci_text):
    """Pin the EXECUTABLE line, not the file text: ci.yml also names these dirs in long
    comments, so a substring-anywhere check would still pass if the loop were deleted."""
    assert f"for dir in {' '.join(SHARED_TEST_DIRS)}" in ci_text, \
        "ci.yml no longer loops over exactly the shared test dirs — F0/CI selection drifted"


def test_ci_still_runs_integration_tests(ci_text):
    assert f"pytest {INTEGRATION_DIR}/" in ci_text, \
        "ci.yml no longer runs the integration-tests step — F0/CI selection drifted"


def test_ci_keeps_the_shared_marker_expression(ci_text):
    """Same selection on both sides (AC3) — CI restates `not slow` because a CLI
    -m replaces the pyproject default."""
    assert 'not slow and not cross_plugin' in ci_text


def test_ci_stays_SERIAL(ci_text):
    """The load-bearing guard, not a style rule.

    F0's honest claim is that it only removes false STOPs — it does NOT prove serial
    equivalence for units that PASSED. The one thing that would catch a parallel-only
    false green is CI running the same units SERIALLY. Parallelising ci.yml would delete
    that cross-check while every other test in this repo stayed green. So: no xdist in
    CI's test steps, enforced.
    """
    for forbidden in ("--numprocesses", "pytest-xdist", "-n auto", "-p xdist"):
        assert forbidden not in ci_text, (
            f"ci.yml uses {forbidden!r}: CI must stay SERIAL — it is the independent "
            "cross-check for a parallel-only false green (see references/F0.md)."
        )


def test_runner_discovers_every_plugin_ci_would_run():
    """Forward direction: no plugin with tests is missing from the runner's units."""
    discovered = {u.id for u in discover_units(_REPO_ROOT)}
    expected = {
        p.name for p in (_REPO_ROOT / "plugins").iterdir()
        if (p / "pyproject.toml").is_file() and (p / "tests").is_dir()
    }
    assert expected <= discovered
    assert expected, "no plugin units discovered — the glob is broken"
