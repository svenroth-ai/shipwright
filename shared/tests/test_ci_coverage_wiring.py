"""Guards the Phase-2/4 diff-coverage CI wiring in .github/workflows/ci.yml.

The combine mechanic is fiddly (per-plugin [paths] remap), so the CI steps that
feed it are pinned here: per-plugin ``--cov`` into per-tier data files, a Combine
step, integration coverage, and the diff-coverage gate step running AFTER combine
over the combined ``coverage.xml``. A future edit that drops one of these silently
would otherwise leave the combined report empty / mis-attributed. Phase 4 (hard
flip) routes the ``--fail-under 80`` gate through the tested
``measure_diff_coverage.py`` wrapper and DROPS continue-on-error, so an
under-tested PR blocks merge — pinned by ``test_diff_coverage_step_is_hard_gate``.
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


def test_diff_coverage_step_is_hard_gate():
    # Diff-coverage roadmap Phase 4 — HARD GATE (the hard flip): the gate DECISION
    # runs through the tested `measure_diff_coverage.py --fail-under 80` wrapper
    # (which prints the report + exits non-zero iff diff% < 80), and
    # continue-on-error is now DROPPED, so an under-tested PR BLOCKS merge. The
    # ci_gate_allowlist entry is removed too (asserted in test_check_ci_gate_
    # coverage.py). 80 == control_grade._DIFF_COV_WARN_THRESHOLD.
    step = _step("Diff coverage (gate)")
    run = step.get("run", "")
    # HARD gate: continue-on-error must NOT be set (absent or False) — this is the
    # flip. If it silently comes back, the guard's reverse-drift check also flags
    # it (a loose gate with no allowlist entry), but pin it here at the source.
    assert step.get("continue-on-error") is not True
    # The gate goes through the tested Python entrypoint (not inline diff-cover).
    assert "measure_diff_coverage.py" in run
    assert "--fail-under 80" in run
    assert "coverage.xml" in run
    # diff-cover is pinned (a release can't silently change flags/exit codes).
    assert "diff-cover==10.3.0" in run
    # The wrapper prints the markdown report; the step captures its exit under
    # `bash -eo pipefail` (|| rc=$?) and re-raises it (`exit "$rc"`) so the step
    # (and, with no continue-on-error, the job) fails on an under-covered diff.
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
    assert order["Combine coverage"] < order["Diff coverage (gate)"]
