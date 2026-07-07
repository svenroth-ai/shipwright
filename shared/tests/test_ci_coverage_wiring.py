"""Guards the Phase-2/4 diff-coverage CI wiring in .github/workflows/ci.yml.

The combine mechanic is fiddly (per-plugin [paths] remap), so the CI steps that
feed it are pinned here: per-plugin ``--cov`` into per-tier data files, a Combine
step, integration coverage, and the diff-coverage gate step running AFTER combine
over the combined ``coverage.xml``. A future edit that drops one of these silently
would otherwise leave the combined report empty / mis-attributed. The
``--fail-under 80`` HARD gate (continue-on-error dropped, so an under-tested PR
blocks merge) now runs through the SHARED composite action
``.github/actions/diff-coverage-gate`` via a local ``./`` path (Stage 3,
iterate-2026-07-07-diff-coverage-self-consume) — pinned by
``test_diff_coverage_step_is_hard_gate``.
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
    # Diff-coverage roadmap — HARD GATE, now via the SHARED composite action
    # (Stage 3, iterate-2026-07-07-diff-coverage-self-consume). The gate DECISION
    # (pinned diff-cover, --fail-under 80, the base fetch) lives in ONE place —
    # `.github/actions/diff-coverage-gate` — consumed by adopt templates + WebUI +
    # (here) the monorepo itself. continue-on-error stays DROPPED, so an
    # under-tested PR BLOCKS merge. The gate mechanics are pinned by the action's
    # own contract test (test_diff_coverage_action.py); the guard's reverse-drift
    # check (test_check_ci_gate_coverage.py) enforces it stays gating.
    step = _step("Diff coverage (gate)")
    # HARD gate: continue-on-error must NOT be set (absent or False).
    assert step.get("continue-on-error") is not True
    # The gate runs through the shared composite action via a LOCAL `./` path —
    # NOT `@main`: a PR that edits the action is gated by its own checkout (no
    # bootstrapping wrinkle) and there is no mutable-action-tag finding.
    uses = step.get("uses", "")
    assert uses.startswith("./.github/actions/diff-coverage-gate"), (
        f"gate step must use the local composite action, got uses={uses!r}"
    )
    assert "@" not in uses, "self-consume must use the local ./ path, not a @ref"
    # The combined coverage.xml is what gets gated.
    with_block = step.get("with") or {}
    assert with_block.get("coverage-files") == "coverage.xml", (
        f"gate must pass coverage-files: coverage.xml, got {with_block!r}"
    )
    # The inline wrapper is gone from this step (it lives in the action now).
    assert "measure_diff_coverage.py" not in step.get("run", "")
    # Skip cleanly when Combine produced no coverage.xml.
    assert step.get("if") == "hashFiles('coverage.xml') != ''"


def test_combine_runs_before_diff_after_all_tiers():
    names = [s.get("name") for s in _steps()]
    order = {n: i for i, n in enumerate(names) if n}
    # Every tier is measured, THEN combined, THEN diff-covered.
    assert order["Run plugin tests"] < order["Combine coverage"]
    assert order["Run shared tests"] < order["Combine coverage"]
    assert order["Run integration tests"] < order["Combine coverage"]
    assert order["Combine coverage"] < order["Diff coverage (gate)"]
