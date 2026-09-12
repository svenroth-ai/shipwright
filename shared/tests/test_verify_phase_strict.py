"""`verify_phase.py --strict`'s blocking decision must honor
`CheckResult.strict_exempt` (`trg-b996bc21`).

Before this fix, `main()`'s blocking calc read `summary.warnings` directly —
a raw count that includes `strict_exempt` warnings (a rollout-transition
grace, a layer-coverage advisory-collision/legacy finding, a plan-gate
migration notice). A direct `verify_phase.py --phase project --strict` call
therefore still hard-blocked on a fully-graced legacy violation, contradicting
the very field that was supposed to make it non-blocking under `--strict`.
`verify_iterate_finalization.py` already got this right with its own,
separately-duplicated calc — this pins the shared `verify_phase.py` path too,
via `ReportSummary.strict_blocking_warnings` in `common.py`.

`dispatch_project` is monkeypatched to a fixed `CheckResult` list rather than
run against a real project: this test is about `main()`'s own blocking
arithmetic, not about exercising `project_checks.run_all_checks` itself
(already covered by its own test suite).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))

import tools.verify_phase as verify_phase  # noqa: E402
from tools.verifiers.common import CheckResult, Severity  # noqa: E402


def _run_main_with(monkeypatch, tmp_path, results, *, strict: bool) -> int:
    monkeypatch.setattr(verify_phase, "dispatch_project", lambda *_a, **_kw: results)
    argv = ["verify_phase.py", "--phase", "project", "--project-root", str(tmp_path)]
    if strict:
        argv.append("--strict")
    monkeypatch.setattr(sys, "argv", argv)
    with pytest.raises(SystemExit) as excinfo:
        verify_phase.main()
    return excinfo.value.code


def test_strict_does_not_block_on_a_fully_graced_warning(tmp_path, monkeypatch):
    results = [
        CheckResult(
            "rollout grace", ok=False, severity=Severity.WARNING.value, strict_exempt=True,
        ),
    ]
    assert _run_main_with(monkeypatch, tmp_path, results, strict=True) == 0


def test_strict_still_blocks_on_a_genuine_warning(tmp_path, monkeypatch):
    results = [
        CheckResult("real warning", ok=False, severity=Severity.WARNING.value),
    ]
    assert _run_main_with(monkeypatch, tmp_path, results, strict=True) == 1


def test_non_strict_never_blocks_on_any_warning(tmp_path, monkeypatch):
    results = [
        CheckResult("real warning", ok=False, severity=Severity.WARNING.value),
    ]
    assert _run_main_with(monkeypatch, tmp_path, results, strict=False) == 0


def test_an_error_blocks_even_under_a_fully_graced_warning(tmp_path, monkeypatch):
    results = [
        CheckResult("rollout grace", ok=False, severity=Severity.WARNING.value, strict_exempt=True),
        CheckResult("real error", ok=False, severity=Severity.ERROR.value),
    ]
    assert _run_main_with(monkeypatch, tmp_path, results, strict=True) == 1
