"""Iterate 12.1 — test the `_validate_project` canon augmentation.

Before 12.1 ``_validate_project`` only checked
``shipwright_project_config.json`` existence + splits + spec.md presence.
Iterate 12.1 augments it with the modular ``project_checks.run_project_checks``
verifier so missing canon artifacts (C1/C2/C3/C5 + phase_history + ADR
integrity) block the orchestrator's ``update-step --step project``.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest  # noqa: F401  — used for fixtures via conftest

# phase_validators.py imports `lib.config` from shared/scripts/. At module
# load it does its own `sys.path.insert(0, <shared/scripts>)` so we need
# to import it via the file path rather than via the `lib.*` namespace
# (the plugin-run conftest already put plugins/shipwright-run/scripts/lib
# on the path, so `import lib.phase_validators` would race with the
# shared/scripts `lib` package). Loading by file avoids the ambiguity.
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_PHASE_VALIDATORS_PATH = (
    _REPO_ROOT / "plugins" / "shipwright-run" / "scripts" / "lib" / "phase_validators.py"
)

# Ensure shared/scripts is first on sys.path so phase_validators's own
# `from lib.config import ...` resolves to shared/scripts/lib/config.py.
_SHARED_SCRIPTS = _REPO_ROOT / "shared" / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

_spec = importlib.util.spec_from_file_location(
    "phase_validators_under_test",
    _PHASE_VALIDATORS_PATH,
)
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)
validate_phase = _module.validate_phase


def _seed_basic_project(root: Path) -> None:
    """Minimum fields for the legacy (pre-12.1) path to succeed."""
    (root / "shipwright_project_config.json").write_text(
        json.dumps({
            "status": "complete",
            "splits": [{"name": "01-auth", "status": "complete"}],
        })
    )
    (root / ".shipwright" / "planning" / "01-auth").mkdir(parents=True)
    (root / ".shipwright" / "planning" / "01-auth" / "spec.md").write_text("# spec\n")


def _seed_canon_artifacts(root: Path, *, run_id: str = "project-20260414-x") -> None:
    """Seed every canon artifact that ``run_project_checks`` verifies."""
    (root / "shipwright_events.jsonl").write_text(
        json.dumps({"type": "phase_completed", "phase": "project"}) + "\n"
    )
    (root / "agent_docs").mkdir(exist_ok=True)
    (root / "agent_docs" / "build_dashboard.md").write_text("- project: complete\n")
    (root / "agent_docs" / "session_handoff.md").write_text("fresh")
    (root / "agent_docs" / "decision_log.md").write_text(
        "### ADR-027: Project decomposition\n- **Status:** accepted\n"
    )
    (root / "CHANGELOG.md").write_text(
        "# Changelog\n\n## [Unreleased]\n\n### Added\n- Project initialized: foo\n"
    )
    (root / "shipwright_run_config.json").write_text(json.dumps({
        "phase_history": {
            "project": [{"run_id": run_id, "date": "2026-04-14"}],
        },
    }))


def test_legacy_path_still_works_when_canon_artifacts_missing(tmp_path, monkeypatch):
    """Regression guard: a project without ANY canon artifacts fails on
    the canon checks, not on the legacy pre-12.1 logic."""
    _seed_basic_project(tmp_path)
    monkeypatch.setenv("SHIPWRIGHT_RUN_ID", "project-20260414-x")
    valid, issues = validate_phase("project", tmp_path)
    assert valid is False
    # Failures should be canon-tagged (not from the pre-12.1 gate)
    ask_messages = [i["message"] for i in issues if i["severity"] == "ask"]
    assert any("[canon]" in m for m in ask_messages)


def test_full_canon_project_passes(tmp_path, monkeypatch):
    _seed_basic_project(tmp_path)
    _seed_canon_artifacts(tmp_path, run_id="project-20260414-full")
    monkeypatch.setenv("SHIPWRIGHT_RUN_ID", "project-20260414-full")
    valid, issues = validate_phase("project", tmp_path)
    # Only inform-level notes (WARNING-severity) may remain; no ask items
    ask = [i for i in issues if i["severity"] == "ask"]
    assert ask == [], ask
    assert valid is True


def test_missing_c5_blocks_validation(tmp_path, monkeypatch):
    _seed_basic_project(tmp_path)
    _seed_canon_artifacts(tmp_path, run_id="project-c5-missing")
    # Break C5: CHANGELOG with empty Added section
    (tmp_path / "CHANGELOG.md").write_text(
        "# Changelog\n\n## [Unreleased]\n\n### Fixed\n- bug\n"
    )
    monkeypatch.setenv("SHIPWRIGHT_RUN_ID", "project-c5-missing")
    valid, issues = validate_phase("project", tmp_path)
    assert valid is False
    ask = [i["message"] for i in issues if i["severity"] == "ask"]
    assert any("C5" in m for m in ask)


def test_phase_history_missing_blocks_validation(tmp_path, monkeypatch):
    _seed_basic_project(tmp_path)
    _seed_canon_artifacts(tmp_path, run_id="project-no-history")
    (tmp_path / "shipwright_run_config.json").write_text(json.dumps({}))
    monkeypatch.setenv("SHIPWRIGHT_RUN_ID", "project-no-history")
    valid, issues = validate_phase("project", tmp_path)
    assert valid is False
    assert any("phase_history" in i["message"] for i in issues if i["severity"] == "ask")


def test_legacy_pre_12_1_gate_still_fires(tmp_path, monkeypatch):
    """If the project plugin's pre-12.1 gate fails (no splits), the
    canon verifier doesn't even run — we fail fast with the legacy
    ask message."""
    (tmp_path / "shipwright_project_config.json").write_text(
        json.dumps({"status": "complete", "splits": []})
    )
    monkeypatch.setenv("SHIPWRIGHT_RUN_ID", "project-empty")
    valid, issues = validate_phase("project", tmp_path)
    assert valid is False
    assert any("No splits" in i["message"] for i in issues)
