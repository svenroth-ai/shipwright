"""Post-build phase validators: test, changelog, deploy, compliance.

Extracted from ``phase_validators`` (which re-imports them into ``_VALIDATORS``). Every
validator takes ``split_id`` / ``run_id`` keywords; none here is split-aware, and all but
compliance hand ``run_id`` to the canon bridge.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from phase_validators_canon import _run_canon_checks


def _skip_reason(block: dict) -> str:
    """The skip reason under either key producers write (``reason`` / ``skip_reason``)."""
    for key in ("reason", "skip_reason"):
        value = block.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _screenshot_tolerance() -> float | None:
    """The screenshot check's tolerance constant, loaded by file path (ADR-045); None when the test plugin is not beside this one."""
    path = Path(__file__).resolve().parents[3] / "shipwright-test" / "scripts" / "lib" / "png_compare.py"
    if not path.is_file():
        return None
    spec = importlib.util.spec_from_file_location("screenshot_png_compare_tolerance", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.TOLERANCE


def _screenshot_check_issue(project_root: Path, results: dict) -> str:
    """Blocking reason when Design applied a Brief package and the screenshot check did not pass for real, else ''."""
    if not (project_root / ".shipwright" / "designs" / "brief-package-applied.json").is_file():
        return ""
    block = results.get("screenshot_check")
    if not isinstance(block, dict):
        return "A Brief package was applied but the screenshot check has no result (Step 3.7b). Run it before continuing."
    expected = _screenshot_tolerance()
    if block.get("applies") is not True or block.get("status") != "pass":
        return f"Screenshot check did not pass (status={block.get('status')!r}); built screens do not match the approved mockups. STOP and report."
    if block.get("captured") is not True:
        return "Screenshot check result was not made from fresh screenshots (captured is not true)."
    if expected is not None and block.get("tolerance") != expected:
        return f"Screenshot check ran with tolerance {block.get('tolerance')!r}, not the standard {expected}."
    return ""


def _validate_test(
    project_root: Path, *, split_id: str | None = None, run_id: str | None = None,
) -> tuple[bool, list[dict[str, str]]]:
    """Test phase: results file exists, all layers have results or valid skip reasons.

    A skipped layer's reason is accepted under ``reason`` or ``skip_reason``.
    Standalone-mode results (mode == "standalone") are ignored by the pipeline
    validator — the test phase must run again within the pipeline context.
    """
    issues: list[dict[str, str]] = []
    results_path = project_root / "shipwright_test_results.json"

    if not results_path.exists():
        issues.append({
            "severity": "ask",
            "message": "No shipwright_test_results.json found. Were tests actually executed?",
        })
        return False, issues

    try:
        results = json.loads(results_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        issues.append({
            "severity": "ask",
            "message": "shipwright_test_results.json is corrupt or unreadable. Re-run tests?",
        })
        return False, issues

    # Ignore standalone results — pipeline must run its own test phase
    if results.get("mode") == "standalone":
        issues.append({
            "severity": "ask",
            "message": (
                "Test results were produced in standalone mode (not part of this pipeline run). "
                "Re-run /shipwright-test within the pipeline for accurate validation."
            ),
        })
        return False, issues

    has_ask = False

    # Unit tests: must have results
    unit = results.get("unit", {})
    if not unit or unit.get("total", 0) == 0:
        issues.append({
            "severity": "ask",
            "message": "Unit test layer has no results. Were unit tests executed?",
        })
        has_ask = True

    # Integration tests: optional — only validate if present or profile requires them
    integration = results.get("integration", {})
    integration_skipped = integration.get("skipped", False)
    if integration and not integration_skipped and integration.get("total", 0) > 0:
        if integration.get("passed", 0) < integration.get("total", 0):
            issues.append({
                "severity": "ask",
                "message": (
                    f"Integration tests failing: {integration.get('passed', 0)}/{integration['total']} passed. "
                    "Fix before continuing?"
                ),
            })
            has_ask = True
    elif integration_skipped and not _skip_reason(integration):
        issues.append({
            "severity": "ask",
            "message": "Integration tests were skipped without a reason. Was this intentional?",
        })
        has_ask = True

    # pgTAP tests: optional — only validate if present
    pgtap = results.get("pgtap", {})
    pgtap_skipped = pgtap.get("skipped", False)
    if pgtap and not pgtap_skipped and pgtap.get("total", 0) > 0:
        if pgtap.get("passed", 0) < pgtap.get("total", 0):
            issues.append({
                "severity": "ask",
                "message": (
                    f"pgTAP tests failing: {pgtap.get('passed', 0)}/{pgtap['total']} passed. "
                    "Fix before continuing?"
                ),
            })
            has_ask = True

    # Smoke test: must have status or valid skip reason
    smoke = results.get("smoke", {})
    smoke_status = smoke.get("status", "")
    if not smoke_status:
        issues.append({
            "severity": "ask",
            "message": "Smoke test layer has no result. Continue without smoke test?",
        })
        has_ask = True
    elif smoke_status == "skip" and not _skip_reason(smoke):
        issues.append({
            "severity": "ask",
            "message": "Smoke test was skipped without a reason. Was this intentional?",
        })
        has_ask = True

    # E2E: must have status or valid skip reason
    e2e = results.get("e2e", {})
    e2e_skipped = e2e.get("skipped", False)
    if not e2e and not e2e_skipped:
        issues.append({
            "severity": "ask",
            "message": "E2E test layer has no result. Continue without E2E tests?",
        })
        has_ask = True
    elif e2e_skipped and not _skip_reason(e2e):
        issues.append({
            "severity": "ask",
            "message": "E2E tests were skipped without a reason. Was this intentional?",
        })
        has_ask = True

    # --- Outcome checks (after existence checks) ---

    # Unit: blocking — must pass
    if unit.get("total", 0) > 0 and unit.get("passed", 0) < unit.get("total", 0):
        issues.append({
            "severity": "ask",
            "message": (
                f"Unit tests failing: {unit.get('passed', 0)}/{unit['total']} passed. "
                "Fix before continuing?"
            ),
        })
        has_ask = True

    # Smoke: blocking — must pass
    if smoke_status == "fail":
        issues.append({
            "severity": "ask",
            "message": "Smoke test failed — app not responding correctly. Continue anyway?",
        })
        has_ask = True

    # Screenshot check: blocking, only for a project whose Design applied a Brief package
    shot_issue = _screenshot_check_issue(project_root, results)
    if shot_issue:
        issues.append({"severity": "ask", "message": shot_issue})
        has_ask = True

    # E2E: non-blocking — warn only (per constitution, E2E can be flaky)
    e2e_passed = e2e.get("passed", 0)
    e2e_total = e2e.get("total", 0)
    if e2e_total > 0 and e2e_passed < e2e_total:
        issues.append({
            "severity": "inform",
            "message": (
                f"E2E tests: {e2e_passed}/{e2e_total} passed. "
                f"{e2e_total - e2e_passed} failures logged as warnings."
            ),
        })

    # Consistency: non-blocking — inform only (cross-page cosmetic issues)
    consistency = results.get("consistency", {})
    if consistency and not consistency.get("skipped", False):
        cons_total = consistency.get("total", 0)
        cons_passed = consistency.get("passed", 0)
        if cons_total > 0 and cons_passed < cons_total:
            issues.append({
                "severity": "inform",
                "message": (
                    f"UI consistency: {cons_passed}/{cons_total} categories consistent. "
                    f"{cons_total - cons_passed} inconsistencies logged."
                ),
            })

    _run_canon_checks("test", project_root, issues, run_id=run_id)
    has_ask = any(i["severity"] == "ask" for i in issues)
    return not has_ask, issues


def _validate_changelog(
    project_root: Path, *, split_id: str | None = None, run_id: str | None = None,
) -> tuple[bool, list[dict[str, str]]]:
    """Changelog phase: CHANGELOG.md exists. Iterate 12.4 augments with
    the modular ``changelog_checks`` verifier (canon C1/C2/C3 +
    Sonder-Checks ``check_git_tag_exists`` and
    ``check_changelog_version_matches_tag`` + ``phase_history`` + ADR
    integrity). C4/C5 are skipped by policy.
    """
    issues: list[dict[str, str]] = []

    if not (project_root / "CHANGELOG.md").exists():
        issues.append({
            "severity": "ask",
            "message": "No CHANGELOG.md found. Was /shipwright-changelog completed?",
        })
        return False, issues

    _run_canon_checks("changelog", project_root, issues, run_id=run_id)
    has_ask = any(i["severity"] == "ask" for i in issues)
    return not has_ask, issues


def _validate_deploy(
    project_root: Path, *, split_id: str | None = None, run_id: str | None = None,
) -> tuple[bool, list[dict[str, str]]]:
    """Deploy phase: iterate 12.4 wires the modular ``deploy_checks``
    verifier (test-gate pre-condition + canon C1/C2/C3 + phase_history
    + ADR integrity). C4/C5 are skipped by policy (deploy is execution
    + operational history, not a decision or product change).
    """
    issues: list[dict[str, str]] = []
    _run_canon_checks("deploy", project_root, issues, run_id=run_id)
    has_ask = any(i["severity"] == "ask" for i in issues)
    return not has_ask, issues


def _validate_compliance(
    project_root: Path, *, split_id: str | None = None, run_id: str | None = None,
) -> tuple[bool, list[dict[str, str]]]:
    """Compliance phase: check artifacts exist. INFORM only — non-blocking."""
    issues: list[dict[str, str]] = []
    compliance_dir = project_root / ".shipwright" / "compliance"

    required = ["dashboard.md", "traceability-matrix.md", "test-evidence.md", "change-history.md", "sbom.md"]
    present = []
    missing = []

    for name in required:
        if (compliance_dir / name).exists():
            present.append(name)
        else:
            missing.append(name)

    if missing:
        issues.append({
            "severity": "inform",
            "message": (
                f"Compliance artifacts: {len(present)}/{len(required)} present. "
                f"Missing: {', '.join(missing)}."
            ),
        })
    else:
        issues.append({
            "severity": "inform",
            "message": f"All {len(required)} compliance artifacts present.",
        })

    # Inform-level issues never make valid=False
    return True, issues
