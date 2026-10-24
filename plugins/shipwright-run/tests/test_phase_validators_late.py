"""Post-build phase validators (test / changelog / deploy / compliance) and the canon bridge.

These moved out of ``phase_validators`` unchanged (campaign A2); this file pins their
branches in-process, which the project-phase tests do not reach.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_LIB = _REPO_ROOT / "plugins" / "shipwright-run" / "scripts" / "lib"
_SHARED_SCRIPTS = _REPO_ROOT / "shared" / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

_spec = importlib.util.spec_from_file_location("phase_validators_late_entry", _LIB / "phase_validators.py")
_pv = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_pv)

# importable by bare name once phase_validators has put its lib dir on sys.path
import phase_validators_canon as canon  # noqa: E402
import phase_validators_late as late  # noqa: E402

validate_phase = _pv.validate_phase

pytestmark = pytest.mark.covers("FR-01.01/AC01")


@pytest.fixture(autouse=True)
def _no_canon(monkeypatch):
    """Isolate the validators' own branches from the canon verifiers."""
    monkeypatch.setattr(late, "_run_canon_checks", lambda *_a, **_k: None)


def _write_results(root: Path, results: dict) -> None:
    (root / "shipwright_test_results.json").write_text(json.dumps(results), encoding="utf-8")


def _good_results() -> dict:
    return {
        "unit": {"total": 4, "passed": 4},
        "smoke": {"status": "pass"},
        "e2e": {"total": 2, "passed": 2},
    }


def _messages(issues: list[dict]) -> str:
    return " | ".join(i["message"] for i in issues)


def test_registry_routes_every_late_phase():
    assert _pv._VALIDATORS["test"] is late._validate_test
    assert _pv._VALIDATORS["changelog"] is late._validate_changelog
    assert _pv._VALIDATORS["deploy"] is late._validate_deploy
    assert _pv._VALIDATORS["compliance"] is late._validate_compliance
    assert validate_phase("no-such-phase", Path(".")) == (True, [])


def test_test_phase_missing_results_file(tmp_path):
    valid, issues = validate_phase("test", tmp_path)
    assert not valid and "No shipwright_test_results.json" in _messages(issues)


def test_test_phase_corrupt_results_file(tmp_path):
    (tmp_path / "shipwright_test_results.json").write_text("{not json", encoding="utf-8")
    valid, issues = validate_phase("test", tmp_path)
    assert not valid and "corrupt or unreadable" in _messages(issues)


def test_test_phase_standalone_results_rejected(tmp_path):
    _write_results(tmp_path, {"mode": "standalone", **_good_results()})
    valid, issues = validate_phase("test", tmp_path)
    assert not valid and "standalone mode" in _messages(issues)


def test_test_phase_all_green(tmp_path):
    _write_results(tmp_path, _good_results())
    valid, issues = validate_phase("test", tmp_path)
    assert valid and issues == []


def test_test_phase_missing_layers_all_ask(tmp_path):
    _write_results(tmp_path, {})
    valid, issues = validate_phase("test", tmp_path)
    text = _messages(issues)
    assert not valid
    for needle in ("Unit test layer", "Smoke test layer", "E2E test layer"):
        assert needle in text


def test_test_phase_failing_layers(tmp_path):
    _write_results(tmp_path, {
        "unit": {"total": 4, "passed": 3},
        "integration": {"total": 2, "passed": 1},
        "pgtap": {"total": 2, "passed": 0},
        "smoke": {"status": "fail"},
        "e2e": {"total": 5, "passed": 3},
        "consistency": {"total": 3, "passed": 1},
    })
    valid, issues = validate_phase("test", tmp_path)
    text = _messages(issues)
    assert not valid
    for needle in ("Unit tests failing", "Integration tests failing", "pgTAP tests failing",
                   "Smoke test failed", "E2E tests: 3/5", "UI consistency: 1/3"):
        assert needle in text
    severities = {i["message"].split(":")[0]: i["severity"] for i in issues}
    assert severities["E2E tests"] == "inform"
    assert severities["UI consistency"] == "inform"


def test_test_phase_skips_need_reasons(tmp_path):
    _write_results(tmp_path, {
        "unit": {"total": 1, "passed": 1},
        "integration": {"skipped": True},
        "smoke": {"status": "skip"},
        "e2e": {"skipped": True},
    })
    valid, issues = validate_phase("test", tmp_path)
    text = _messages(issues)
    assert not valid
    assert "Integration tests were skipped without a reason" in text
    assert "Smoke test was skipped without a reason" in text
    assert "E2E tests were skipped without a reason" in text


def test_test_phase_skips_with_reasons_pass(tmp_path):
    _write_results(tmp_path, {
        "unit": {"total": 1, "passed": 1},
        "integration": {"skipped": True, "skip_reason": "no db"},
        "smoke": {"status": "skip", "reason": "no server"},
        "e2e": {"skipped": True, "reason": "no browser"},
    })
    valid, issues = validate_phase("test", tmp_path)
    assert valid and issues == []


def test_changelog_phase(tmp_path):
    valid, issues = validate_phase("changelog", tmp_path)
    assert not valid and "No CHANGELOG.md" in _messages(issues)
    (tmp_path / "CHANGELOG.md").write_text("# Changelog\n", encoding="utf-8")
    assert validate_phase("changelog", tmp_path) == (True, [])


def test_deploy_phase_returns_the_canon_verdict(tmp_path, monkeypatch):
    calls = []

    def recorder(phase, project_root, issues):
        calls.append((phase, project_root))
        issues.append({"severity": "ask", "message": "[canon] x: y"})

    monkeypatch.setattr(late, "_run_canon_checks", recorder)
    valid, issues = validate_phase("deploy", tmp_path)
    assert calls == [("deploy", tmp_path)]
    assert valid is False and [i["severity"] for i in issues] == ["ask"]


def test_compliance_phase_reports_missing_then_all_present(tmp_path):
    valid, issues = validate_phase("compliance", tmp_path)
    assert valid and issues[0]["severity"] == "inform" and "0/5 present" in issues[0]["message"]
    comp = tmp_path / ".shipwright" / "compliance"
    comp.mkdir(parents=True)
    for name in ("dashboard.md", "traceability-matrix.md", "test-evidence.md", "change-history.md", "sbom.md"):
        (comp / name).write_text("x", encoding="utf-8")
    valid, issues = validate_phase("compliance", tmp_path)
    assert valid and "All 5 compliance artifacts present" in issues[0]["message"]


_CANON_STUBS = {
    "project": ("project_checks", "run_project_checks"),
    "design": ("design_checks", "run_design_checks"),
    "plan": ("plan_checks", "run_plan_checks"),
    "build": ("build_checks", "run_build_checks"),
    "test": ("test_checks", "run_test_checks"),
    "changelog": ("changelog_checks", "run_changelog_checks"),
    "deploy": ("deploy_checks", "run_deploy_checks"),
}


@pytest.mark.parametrize("phase", sorted(_CANON_STUBS))
def test_canon_bridge_dispatches_every_phase(tmp_path, monkeypatch, phase):
    import importlib

    from tools.verifiers.common import Severity

    def result(name, *, ok, skipped, severity):
        return SimpleNamespace(name=name, detail=f"{name}-detail", ok=ok, is_skipped=skipped,
                               severity=severity)

    seen = []

    def stub(project_root, *, run_id):
        seen.append((project_root, run_id))
        return [
            result("err", ok=False, skipped=False, severity=Severity.ERROR.value),
            result("warn", ok=False, skipped=False, severity=Severity.WARNING.value),
            result("skipped", ok=False, skipped=True, severity=Severity.ERROR.value),
            result("green", ok=True, skipped=False, severity=Severity.ERROR.value),
        ]

    module_name, func_name = _CANON_STUBS[phase]
    module = importlib.import_module(f"tools.verifiers.{module_name}")
    monkeypatch.setattr(module, func_name, stub)
    monkeypatch.setenv("SHIPWRIGHT_RUN_ID", "run-x")

    issues: list[dict] = []
    canon._run_canon_checks(phase, tmp_path, issues)

    assert seen == [(tmp_path, "run-x")]
    assert issues == [
        {"severity": "ask", "message": "[canon] err: err-detail"},
        {"severity": "inform", "message": "[canon] warn: warn-detail"},
    ]


def test_canon_bridge_unknown_phase_is_a_noop(tmp_path):
    issues: list[dict] = []
    canon._run_canon_checks("not-a-phase", tmp_path, issues)
    assert issues == []
