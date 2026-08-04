"""Integration contract for the unified verifier CLI and all-phase dispatch."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
VERIFY_PHASE = REPO_ROOT / "shared" / "scripts" / "tools" / "verify_phase.py"
EXPECTED_ALL_PHASE_ORDER = (
    "iterate",
    "project",
    "design",
    "plan",
    "build",
    "test",
    "changelog",
    "deploy",
)


def _load_verify_phase():
    spec = importlib.util.spec_from_file_location("verify_phase_cli_contract", VERIFY_PHASE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_runtime_phase_is_retired_from_real_cli(tmp_path: Path) -> None:
    help_result = subprocess.run(
        [sys.executable, str(VERIFY_PHASE), "--help"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert help_result.returncode == 0
    assert "runtime" not in (help_result.stdout + help_result.stderr).lower()

    retired = subprocess.run(
        [
            sys.executable,
            str(VERIFY_PHASE),
            "--phase",
            "runtime",
            "--project-root",
            str(tmp_path),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    combined = (retired.stdout + retired.stderr).lower()
    assert retired.returncode == 2
    assert "invalid choice" in combined
    assert "runtime" in combined

    surviving = subprocess.run(
        [
            sys.executable,
            str(VERIFY_PHASE),
            "--phase",
            "project",
            "--project-root",
            str(tmp_path),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    surviving_output = surviving.stdout + surviving.stderr
    assert surviving.returncode == 1
    assert "SHIPWRIGHT VERIFIER: project finalization" in surviving_output
    assert "invalid choice" not in surviving_output.lower()
    assert "traceback" not in surviving_output.lower()


def test_all_phase_dispatch_preserves_the_surviving_order(
    monkeypatch,
    tmp_path: Path,
) -> None:
    verify_phase = _load_verify_phase()
    calls: list[str] = []

    monkeypatch.setattr(
        verify_phase,
        "dispatch_iterate",
        lambda *_args: calls.append("iterate") or [],
    )
    for phase in EXPECTED_ALL_PHASE_ORDER[1:]:
        monkeypatch.setattr(
            verify_phase,
            f"dispatch_{phase}",
            lambda *_args, phase=phase: calls.append(phase) or [],
        )

    results = verify_phase.dispatch_all(tmp_path, "run-1", "commit-1")

    assert results == []
    assert tuple(calls) == EXPECTED_ALL_PHASE_ORDER
    assert tuple(verify_phase.ALL_PHASES) == EXPECTED_ALL_PHASE_ORDER
