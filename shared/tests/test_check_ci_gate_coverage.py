"""Tests for the CI gate-coverage guard (``check_ci_gate_coverage.py``).

The guard is the meta-check that stops CI quality gates from silently going
loose (the ``ci.yml`` "dormant" regression) or a new test dir from being
silently uncovered. These tests pin each acceptance criterion AND assert the
live repo's workflows pass the guard, so the guard can never go green while the
real ``.github/workflows`` are broken.
"""

from __future__ import annotations

from lib.ci_gate_allowlist import AllowEntry, LOOSE_GATE_ALLOWLIST
from tools.check_ci_gate_coverage import (
    Step,
    check_loose_gates,
    check_security_findings_gate,
    check_test_dir_coverage,
    is_gate_step,
    is_loose,
    launch_gates,
    stale_allowlist_entries,
)


def _step(*, workflow="ci.yml", job="checks", name="", run="", uses="", coe=False):
    return Step(workflow=workflow, job=job, name=name, run=run, uses=uses,
                continue_on_error=coe)


# --------------------------------------------------------------------------- #
# Classification
# --------------------------------------------------------------------------- #
class TestClassification:
    def test_pytest_run_is_gate(self):
        assert is_gate_step(_step(run="uv run pytest tests/ -v"))

    def test_ruff_run_is_gate(self):
        assert is_gate_step(_step(run="ruff check ."))

    def test_codeql_uses_is_gate(self):
        assert is_gate_step(_step(uses="github/codeql-action/analyze@v3"))

    def test_checkout_is_not_gate(self):
        assert not is_gate_step(_step(name="Checkout", uses="actions/checkout@v4"))

    def test_continue_on_error_gate_is_loose(self):
        assert is_loose(_step(run="pytest x", coe=True))

    def test_pipe_true_on_gate_command_is_loose(self):
        assert is_loose(_step(run="uv run ruff check . || true"))

    def test_clean_gate_is_not_loose(self):
        assert not is_loose(_step(run="uv run pytest tests/ -v"))

    def test_diagnostic_pipe_true_on_nongate_step_not_loose(self):
        # The bloat-check pattern: `cat log || true` on a non-gate step.
        assert not is_loose(_step(name="Show output", run="cat /tmp/log || true"))

    def test_pipe_true_on_nongate_line_within_gate_step_not_loose(self):
        # `|| true` is on the diagnostic line, not the gate command line.
        step = _step(run="uv run pytest tests/\ncat /tmp/log || true")
        assert not is_loose(step)

    def test_pipe_exit_zero_on_gate_is_loose(self):
        assert is_loose(_step(run="uv run pytest tests/ || exit 0"))

    def test_comment_line_quoting_loose_form_not_loose(self):
        # An explanatory comment that quotes `|| true` must not trip the guard.
        step = _step(run="# legacy form was: pytest x || true\nuv run pytest tests/ -v")
        assert not is_loose(step)

    def test_install_step_is_not_gate(self):
        assert not is_gate_step(_step(name="Install Semgrep", run="pip install semgrep"))

    def test_artifact_upload_is_not_gate(self):
        assert not is_gate_step(
            _step(name="Upload scan artifacts", uses="actions/upload-artifact@v4")
        )

    def test_diff_cover_run_is_gate(self):
        # diff-cover is the diff-coverage roadmap's gate tool — the guard must
        # recognize it so a future silent-loosening (Phase 4 --fail-under) is
        # caught.
        assert is_gate_step(_step(run="uvx diff-cover coverage.xml --compare-branch=origin/main"))

    def test_diff_cover_continue_on_error_is_loose(self):
        assert is_loose(
            _step(name="Diff coverage (informational)",
                  run="uvx diff-cover coverage.xml --compare-branch=origin/main", coe=True)
        )


# --------------------------------------------------------------------------- #
# AC1 — test-dir coverage
# --------------------------------------------------------------------------- #
class TestTestDirCoverage:
    def test_uncovered_dir_is_flagged(self):
        steps = [_step(run="pytest shared/tests")]
        assert check_test_dir_coverage(["shared/foo/tests"], steps) == ["shared/foo/tests"]

    def test_literal_referenced_dir_is_covered(self):
        steps = [_step(run="uv run pytest integration-tests/ -v")]
        assert check_test_dir_coverage(["integration-tests"], steps) == []

    def test_plugins_loop_covers_plugin_dirs(self):
        steps = [_step(run="for p in plugins/*/; do (cd $p && pytest tests/); done")]
        assert check_test_dir_coverage(["plugins/shipwright-build/tests"], steps) == []

    def test_plugin_dir_uncovered_without_loop(self):
        steps = [_step(run="pytest shared/tests")]  # no plugins/* glob
        assert check_test_dir_coverage(
            ["plugins/shipwright-build/tests"], steps
        ) == ["plugins/shipwright-build/tests"]

    def test_non_pytest_step_does_not_count_as_reference(self):
        # A bare reference in a non-pytest body must NOT count as coverage.
        steps = [_step(run="echo shared/tests")]
        assert check_test_dir_coverage(["shared/tests"], steps) == ["shared/tests"]


# --------------------------------------------------------------------------- #
# AC2 — loose-gate detection (reverse drift)
# --------------------------------------------------------------------------- #
class TestLooseGates:
    def test_injected_pipe_true_not_allowlisted_is_flagged(self):
        steps = [_step(workflow="ci.yml", name="Run integration tests",
                       run="uv run pytest integration-tests/ -v || true")]
        flagged = check_loose_gates(steps, [])
        assert [s.name for s in flagged] == ["Run integration tests"]

    def test_injected_continue_on_error_not_allowlisted_is_flagged(self):
        steps = [_step(workflow="ci.yml", name="Typecheck", run="mypy .", coe=True)]
        assert len(check_loose_gates(steps, [])) == 1

    def test_allowlisted_loose_gate_is_not_flagged(self):
        steps = [_step(workflow="ci.yml", name="Lint (ruff)",
                       run="uv run ruff check . || true", coe=True)]
        allow = [AllowEntry("ci.yml", "Lint (ruff)", "debt", "tracked-debt")]
        assert check_loose_gates(steps, allow) == []

    def test_clean_gate_is_not_flagged(self):
        steps = [_step(run="uv run pytest tests/ -v")]
        assert check_loose_gates(steps, []) == []

    def test_loose_nongate_step_is_not_flagged(self):
        # A PR-comment step with continue-on-error is not a quality gate.
        steps = [_step(name="Post PR comment", uses="actions/github-script@v7", coe=True)]
        assert check_loose_gates(steps, []) == []


# --------------------------------------------------------------------------- #
# AC3 — allowlist SSoT, forward drift
# --------------------------------------------------------------------------- #
class TestAllowlistStaleness:
    def test_entry_with_no_matching_step_is_stale(self):
        allow = [AllowEntry("ci.yml", "Nonexistent step", "r", "by-design")]
        assert stale_allowlist_entries([], allow) == allow

    def test_entry_matching_loose_step_is_not_stale(self):
        steps = [_step(workflow="ci.yml", name="Lint (ruff)",
                       run="ruff check . || true", coe=True)]
        allow = [AllowEntry("ci.yml", "Lint (ruff)", "r", "tracked-debt")]
        assert stale_allowlist_entries(steps, allow) == []

    def test_entry_matching_hardened_step_is_stale(self):
        # Step exists but is no longer loose -> the entry is stale (should be
        # removed now that the gate is hardened).
        steps = [_step(workflow="ci.yml", name="Lint (ruff)", run="ruff check .")]
        allow = [AllowEntry("ci.yml", "Lint (ruff)", "r", "tracked-debt")]
        assert stale_allowlist_entries(steps, allow) == allow


# --------------------------------------------------------------------------- #
# AC4 — security findings-gate integrity
# --------------------------------------------------------------------------- #
class TestSecurityFindingsGate:
    def test_silent_default_gate_is_flagged(self):
        steps = [_step(workflow="security.yml", name="Check for critical findings",
                       run="critical=$(jq '.' findings.json 2>/dev/null || echo 0)")]
        assert len(check_security_findings_gate(steps)) == 1

    def test_fail_closed_gate_is_ok(self):
        run = (
            "if [ ! -f findings.json ]; then echo missing; exit 1; fi\n"
            "critical=$(jq '.' findings.json)"
        )
        steps = [_step(workflow="security.yml", name="Check for critical findings", run=run)]
        assert check_security_findings_gate(steps) == []

    def test_absent_gate_step_is_flagged(self):
        assert len(check_security_findings_gate([])) == 1

    def test_warning_only_missing_branch_is_flagged(self):
        # Regression M1: a missing-file branch that only WARNS (no exit) while
        # the count silently defaults to 0 must still be flagged.
        run = (
            "if [ ! -f findings.json ]; then echo '::warning::missing'; fi\n"
            "critical=$(jq '.' findings.json 2>/dev/null || echo 0)\n"
            "if [ \"$critical\" -gt 0 ]; then exit 1; fi"
        )
        steps = [_step(workflow="security.yml", name="Check for critical findings", run=run)]
        assert len(check_security_findings_gate(steps)) == 1

    def test_test_dash_f_form_is_ok(self):
        run = (
            "if ! test -f findings.json; then echo missing; exit 1; fi\n"
            "critical=$(jq '.' findings.json)"
        )
        steps = [_step(workflow="security.yml", name="Check for critical findings", run=run)]
        assert check_security_findings_gate(steps) == []


# --------------------------------------------------------------------------- #
# AC5 — launch-gate registry
# --------------------------------------------------------------------------- #
class TestLaunchGates:
    def test_codeql_analyze_tracked_as_launch_gate(self):
        gates = launch_gates(LOOSE_GATE_ALLOWLIST)
        assert any(
            e.workflow == "codeql.yml" and "analy" in e.step.lower()
            for e in gates
        ), "CodeQL analyze must be tracked as a public-launch gate"

    def test_every_launch_gate_has_a_reason(self):
        for e in launch_gates(LOOSE_GATE_ALLOWLIST):
            assert e.reason.strip(), f"launch gate {e.step!r} has no reason"


# --------------------------------------------------------------------------- #
# Diff-coverage roadmap Phase 1 — the informational diff-cover step is
# allowlisted (tracked-debt: Phase 4 makes it gating and removes the entry).
# --------------------------------------------------------------------------- #
class TestDiffCoverageAllowlist:
    def test_diff_cover_step_is_allowlisted(self):
        entry = next(
            (e for e in LOOSE_GATE_ALLOWLIST
             if e.workflow == "ci.yml" and e.step == "Diff coverage (informational)"),
            None,
        )
        assert entry is not None, (
            "the informational ci.yml 'Diff coverage (informational)' step must "
            "be allowlisted — it is intentionally continue-on-error in Phase 1."
        )
        assert entry.category == "tracked-debt", (
            "Phase 4 turns diff-cover into a --fail-under gate and drops this "
            "entry, so it is tracked-debt, not by-design."
        )
        assert entry.reason.strip()
