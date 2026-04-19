"""Version gate + import-sanity tests (plan v7, Step 3).

These tests are the safety net for iterate-12 import drift. They call
``verify_imports`` directly, not through the detector, so breakage here
pinpoints "a symbol the audit imports has been renamed / removed" with
zero ambiguity.
"""

from __future__ import annotations

import inspect
import subprocess
import sys
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLUGIN_ROOT))

# Also ensure shared/scripts is on path so `tools.verifiers.*` resolves
# when tests run from the plugin directory.
REPO_ROOT = PLUGIN_ROOT.parent.parent
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))

from scripts.audit.audit_adapters import (  # noqa: E402
    REQUIRED_SYMBOLS,
    SOURCE_DETECTIVE_ONLY,
    SOURCE_PREVENTIVE_RERUN,
    Finding,
    ImportGateError,
    check_result_to_finding,
    import_iterate12_checks,
    verify_imports,
)


def test_verify_imports_passes_on_current_main():
    """Sanity: every named iterate-12 symbol exists with the expected arity."""
    verify_imports()


def test_verify_imports_raises_on_missing_symbol():
    """The gate must surface a rename / removal with a clear message."""
    with pytest.raises(ImportGateError) as exc_info:
        verify_imports([
            ("tools.verifiers.plan_checks", "check_nope_does_not_exist", 1),
        ])
    msg = str(exc_info.value)
    assert "check_nope_does_not_exist" in msg
    assert "missing" in msg


def test_verify_imports_raises_on_arity_drift():
    """If an imported function loses a required positional arg, gate fails."""
    # CheckResult has no positional args accepting project_root, so it's
    # a natural low-arity target — ``min_arity=5`` must trip the gate.
    with pytest.raises(ImportGateError):
        verify_imports([("tools.verifiers.common", "CheckResult", 5)])


def test_verify_imports_raises_on_missing_module():
    with pytest.raises(ImportGateError) as exc_info:
        verify_imports([("tools.verifiers.not_a_module", "x", 1)])
    assert "not a module" not in str(exc_info.value)  # sanity
    assert "not_a_module" in str(exc_info.value)


def test_required_symbols_covers_all_plan_named_checks():
    """Every check the plan's Architecture section names is in the registry."""
    # Plan's "Imported from iterate 12 / PR 4" list.
    expected = {
        "check_fr_orphans_in_plan",
        "check_section_files_match_manifest",
        "check_section_id_validity",
        "check_design_fr_coverage",
        "check_build_test_files_exist",
        "check_commit_sha_in_git",
        "check_adr_ids_sequential",
        "check_adr_status_valid",
        "check_adr_supersession_exists",
    }
    got = {sym for _mod, sym, _arity in REQUIRED_SYMBOLS}
    missing = expected - got
    assert not missing, f"plan-named imports missing from registry: {missing}"


def test_import_iterate12_checks_returns_callables():
    """Every value must be directly callable with (project_root,)."""
    checks = import_iterate12_checks()
    assert len(checks) == 9
    for name, fn in checks.items():
        sig = inspect.signature(fn)
        positional = [
            p for p in sig.parameters.values()
            if p.kind in (inspect.Parameter.POSITIONAL_ONLY,
                          inspect.Parameter.POSITIONAL_OR_KEYWORD)
        ]
        assert positional, f"{name} has no positional arg"


# ---------------------------------------------------------------------------
# Finding + check_result_to_finding
# ---------------------------------------------------------------------------


def test_finding_rejects_invalid_source():
    with pytest.raises(ValueError):
        Finding(group="A", check_id="A2", name="x", severity="LOW",
                source="invented-source", status="pass")


def test_finding_accepts_both_valid_sources():
    Finding(group="C", check_id="C2", name="x", severity="HIGH",
            source=SOURCE_PREVENTIVE_RERUN, status="pass")
    Finding(group="B", check_id="B1", name="x", severity="HIGH",
            source=SOURCE_DETECTIVE_ONLY, status="pass")


class _FakeCheckResult:
    def __init__(self, ok, severity="error", detail="", name="fake"):
        self.ok = ok
        self.severity = severity
        self.detail = detail
        self.name = name


def test_check_result_to_finding_maps_ok_true():
    f = check_result_to_finding(
        _FakeCheckResult(ok=True), group="C", check_id="C2",
        source=SOURCE_PREVENTIVE_RERUN,
    )
    assert f.status == "pass"
    assert f.severity == "HIGH"
    assert f.source == SOURCE_PREVENTIVE_RERUN


def test_check_result_to_finding_maps_ok_none_to_skip():
    f = check_result_to_finding(
        _FakeCheckResult(ok=None, severity="skipped"),
        group="C", check_id="C2", source=SOURCE_PREVENTIVE_RERUN,
    )
    assert f.status == "skip"


def test_check_result_to_finding_maps_warning_to_medium():
    f = check_result_to_finding(
        _FakeCheckResult(ok=False, severity="warning"),
        group="F", check_id="F2", source=SOURCE_PREVENTIVE_RERUN,
    )
    assert f.severity == "MEDIUM"
    assert f.status == "fail"


def test_check_result_to_finding_respects_severity_override():
    f = check_result_to_finding(
        _FakeCheckResult(ok=False, severity="error"),
        group="D", check_id="D1", source=SOURCE_DETECTIVE_ONLY,
        severity_override="LOW",
    )
    assert f.severity == "LOW"


# ---------------------------------------------------------------------------
# run_audit CLI can be invoked even with no checks registered
# ---------------------------------------------------------------------------


RUN_AUDIT = PLUGIN_ROOT / "scripts" / "audit" / "run_audit.py"


def test_run_audit_skeleton_runs_with_no_checks(tmp_path):
    """Skeleton produces a valid JSON report even before checks are wired."""
    # Minimal fake project — enough for run_audit to find the root.
    (tmp_path / "shipwright_run_config.json").write_text(
        '{"status": "in_progress"}\n', encoding="utf-8",
    )

    result = subprocess.run(
        [sys.executable, str(RUN_AUDIT),
         "--project-root", str(tmp_path)],
        capture_output=True, text=True, encoding="utf-8",
    )
    assert result.returncode == 0, result.stderr

    import json
    payload = json.loads(result.stdout)
    # Before Steps 4-8, every group is "not-implemented".
    assert payload["findings"] == []
    skipped_groups = {s["group"] for s in payload["groups_skipped"]}
    assert skipped_groups == {"A", "B", "C", "D", "E", "F", "G"}


def test_run_audit_rejects_missing_project_root():
    result = subprocess.run(
        [sys.executable, str(RUN_AUDIT),
         "--project-root", str(PLUGIN_ROOT / "__does_not_exist__")],
        capture_output=True, text=True, encoding="utf-8",
    )
    assert result.returncode == 2
