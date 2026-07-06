"""Guards the Phase-2/4 diff-coverage CI wiring in .github/workflows/ci.yml.

The combine mechanic is fiddly (per-plugin [paths] remap), so the CI steps that
feed it are pinned here: per-plugin ``--cov`` into per-tier data files, a Combine
step, integration coverage, and the diff-coverage gate step running AFTER combine
over the combined ``coverage.xml``. A future edit that drops one of these silently
would otherwise leave the combined report empty / mis-attributed. Phase 4 (hardened)
routes the warn-only ``--fail-under 80`` gate through the tested
``measure_diff_coverage.py`` wrapper (still continue-on-error during the settling
window) — pinned by ``test_diff_coverage_step_is_warn_only_gate``.
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


def test_diff_coverage_step_is_warn_only_gate():
    # Diff-coverage roadmap Phase 4 (warn-only), hardened: the gate DECISION now
    # runs through the tested `measure_diff_coverage.py --fail-under 80` wrapper
    # (which prints the report + exits non-zero iff diff% < 80) instead of inline
    # `diff-cover` shell, so the fail-path is provable. continue-on-error stays
    # True for the settling window, so an under-tested PR shows a visible FAILURE
    # but does NOT block merge yet. The hard flip (drop continue-on-error + drop
    # the ci_gate_allowlist entry) is the deferred last step. 80 ==
    # control_grade._DIFF_COV_WARN_THRESHOLD.
    step = _step("Diff coverage (warn-only gate)")
    run = step.get("run", "")
    assert step.get("continue-on-error") is True
    # The gate goes through the tested Python entrypoint (not inline diff-cover).
    assert "measure_diff_coverage.py" in run
    assert "--fail-under 80" in run
    assert "coverage.xml" in run
    # diff-cover is pinned (a release can't silently change flags/exit codes).
    assert "diff-cover==10.3.0" in run
    # The wrapper prints the markdown report; the step captures its exit under
    # `bash -eo pipefail` (|| rc=$?) and re-raises it (`exit "$rc"`) so the step
    # goes red on an under-covered diff (continue-on-error downgrades to warning).
    assert "--markdown-out diff-cover.md" in run
    assert "rc=$?" in run
    assert 'exit "$rc"' in run


def test_combine_runs_before_diff_after_all_tiers():
    names = [s.get("name") for s in _steps()]
    order = {n: i for i, n in enumerate(names) if n}
    # Every tier is measured, THEN combined, THEN diff-covered.
    assert order["Run plugin tests"] < order["Combine coverage"]
    assert order["Run shared tests"] < order["Combine coverage"]
    assert order["Run integration tests"] < order["Combine coverage"]
    assert order["Combine coverage"] < order["Diff coverage (warn-only gate)"]
