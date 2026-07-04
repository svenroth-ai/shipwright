"""Guards the Phase-2 diff-coverage CI wiring in .github/workflows/ci.yml.

The combine mechanic is fiddly (per-plugin [paths] remap), so the CI steps that
feed it are pinned here: per-plugin ``--cov`` into per-tier data files, a Combine
step, integration coverage, and the diff-cover step running AFTER combine over the
combined ``coverage.xml``. A future edit that drops one of these silently would
otherwise leave the combined report empty / mis-attributed.
"""

from __future__ import annotations

from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CI = _REPO_ROOT / ".github" / "workflows" / "ci.yml"


def _steps() -> list[dict]:
    data = yaml.safe_load(_CI.read_text(encoding="utf-8"))
    return data["jobs"]["python-checks"]["steps"]


def _step(name: str) -> dict:
    for s in _steps():
        if s.get("name") == name:
            return s
    raise AssertionError(f"ci.yml step {name!r} not found")


def _run(name: str) -> str:
    return _step(name).get("run", "")


def test_plugin_step_measures_per_plugin_coverage():
    run = _run("Run plugin tests")
    assert "--cov=scripts" in run
    assert "COVERAGE_FILE=" in run and ".cov-data/.coverage.$name" in run
    # relative_files is honoured from the plugin dir only via the root config.
    assert "--cov-config=" in run
    # The single stale-state clear lives here (first coverage-producing tier).
    assert "rm -rf .cov-data" in run


def test_shared_step_writes_shared_tier_datafile():
    run = _run("Run shared tests")
    assert ".cov-data/.coverage.shared" in run
    assert "--cov=shared" in run and "--cov-append" in run


def test_integration_step_measures_coverage():
    run = _run("Run integration tests")
    assert "--cov=shared" in run
    assert ".cov-data/.coverage.integration" in run


def test_combine_step_invokes_the_tool():
    step = _step("Combine coverage")
    run = step.get("run", "")
    assert "combine_coverage.py" in run
    assert "--data-dir .cov-data" in run
    assert "--output coverage.xml" in run
    # always(): produce the coverage artifact even when an earlier test tier
    # failed the job (combine is absent-safe), so a red run still leaves the
    # diagnostic — without masking the failing step.
    assert step.get("if") == "always()"


def test_diff_coverage_step_stays_nongating():
    step = _step("Diff coverage (informational)")
    assert step.get("continue-on-error") is True
    assert "--fail-under" not in step.get("run", "")  # Phase 4 adds the gate
    assert "coverage.xml" in step.get("run", "")


def test_combine_runs_before_diff_after_all_tiers():
    names = [s.get("name") for s in _steps()]
    order = {n: i for i, n in enumerate(names) if n}
    # Every tier is measured, THEN combined, THEN diff-covered.
    assert order["Run plugin tests"] < order["Combine coverage"]
    assert order["Run shared tests"] < order["Combine coverage"]
    assert order["Run integration tests"] < order["Combine coverage"]
    assert order["Combine coverage"] < order["Diff coverage (informational)"]
