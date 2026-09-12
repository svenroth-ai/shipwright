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

import pytest

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
    """Minimum fields for the legacy (pre-12.1) path to succeed. scope=
    "extension" skips the new #11 guidance check (no CLAUDE.md/agent_docs
    modeled here); spec.md carries one FR row so the new #10 empty-split
    check doesn't itself redden this fixture (req3-06-enforcement-mono e2)."""
    (root / "shipwright_project_config.json").write_text(json.dumps({
        "status": "complete", "scope": "extension",
        "splits": [{"name": "01-auth", "status": "complete"}],
    }))
    (root / ".shipwright" / "planning" / "01-auth").mkdir(parents=True)
    (root / ".shipwright" / "planning" / "01-auth" / "spec.md").write_text(
        "# spec\n\n"
        "| ID | Name | Priority | Description | Basis |\n"
        "|---|---|---|---|---|\n"
        "| FR-01.01 | some capability | Must | a plain-language capability "
        "description | interview |\n"
    )


def _seed_canon_artifacts(root: Path, *, run_id: str = "project-20260414-x") -> None:
    """Seed every canon artifact that ``run_project_checks`` verifies."""
    (root / "shipwright_events.jsonl").write_text(
        json.dumps({"type": "phase_completed", "phase": "project"}) + "\n"
    )
    (root / ".shipwright" / "agent_docs").mkdir(parents=True, exist_ok=True)
    (root / ".shipwright" / "agent_docs" / "build_dashboard.md").write_text("- project: complete\n")
    # A REAL canon marker, naming this phase and the run phase_history records
    # below. The literal "fresh" here used to pass on filesystem mtime; once C3
    # became content-keyed it silently stopped exercising C3 at all — the
    # assertion below only looks at ask-level issues and C3 is inform-level, so
    # the suite stayed green while covering nothing
    # (iterate-2026-07-27-c3-phase-history-join).
    (root / ".shipwright" / "agent_docs" / "session_handoff.md").write_text(
        f'---\ncanon_generated: true\nrun_id: "{run_id}"\nphase: "project"\n'
        f'reason: "project scaffolding complete"\ndate: "2026-04-14"\n'
        f'timestamp: "2026-04-14T12:00:00+00:00"\n---\n\n# Session Handoff\n'
    )
    (root / ".shipwright" / "agent_docs" / "decision_log.md").write_text(
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


@pytest.mark.covers("FR-01.02/AC01")
def test_full_canon_project_passes(tmp_path, monkeypatch):
    _seed_basic_project(tmp_path)
    _seed_canon_artifacts(tmp_path, run_id="project-20260414-full")
    monkeypatch.setenv("SHIPWRIGHT_RUN_ID", "project-20260414-full")
    valid, issues = validate_phase("project", tmp_path)
    # Only inform-level notes (WARNING-severity) may remain; no ask items
    ask = [i for i in issues if i["severity"] == "ask"]
    assert ask == [], ask
    assert valid is True
    # "full canon" must actually mean C3 too. Asserting only on ask-level items
    # let a fixture that had stopped satisfying C3 keep this test green, because
    # C3 is inform-level (iterate-2026-07-27-c3-phase-history-join).
    assert not [i for i in issues if "C3" in i["message"]], issues


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


@pytest.mark.covers("FR-01.02/AC01")
def test_legacy_pre_12_1_gate_still_fires(tmp_path, monkeypatch):
    """If the project plugin's pre-12.1 gate fails (no splits), the
    canon verifier doesn't even run — we fail fast with the legacy
    ask message. AC01's other half: an empty catalogue must FAIL."""
    (tmp_path / "shipwright_project_config.json").write_text(
        json.dumps({"status": "complete", "splits": []})
    )
    monkeypatch.setenv("SHIPWRIGHT_RUN_ID", "project-empty")
    valid, issues = validate_phase("project", tmp_path)
    assert valid is False
    assert any("No splits" in i["message"] for i in issues)


# ---------------------------------------------------------------------------
# Grill-trace completeness gate (P4.2) — proves the gate is CODE-ENFORCED
# at the SAME boundary as C1-C5, not merely documented in Step-8 prose.
#
# The spec-reviewer's REJECT on the first P4.2.2 round: the gate existed
# (verify_grill_trace_completeness.py) but its only registration was prose
# in step-8-completion.md/SKILL.md telling the agent to run it and decide
# for itself — never through `run_project_checks()`, the actual
# `_run_canon_checks` dispatcher this test module exists to exercise. These
# tests call `validate_phase("project", ...)` — the exact function
# `update-step --step project` calls to decide whether completion is
# blocked — with a project whose grill-trace fails a STOP condition, and
# assert it participates in the SAME ask-level block C1-C5 already prove
# here, not a parallel mechanism that merely looks wired up.
# ---------------------------------------------------------------------------

def _write_failing_grill_trace(root: Path) -> None:
    """A shape-valid grill-trace with one dimension in STOP territory
    (greenfield 'assumed' — no exceptions permitted in the project
    surface, ``verify_grill_trace_completeness.check_greenfield_assumed``)."""
    trace_dir = root / ".shipwright" / "planning" / "grill-traces"
    trace_dir.mkdir(parents=True, exist_ok=True)
    (trace_dir / "export-data.json").write_text(json.dumps({
        "requirement_key": "export-data",
        "requirement_text": "Users can export their data",
        "surface": "project",
        "evidence": ["interview transcript line 42"],
        "dimensions": {
            "outcome": "answered",
            "purpose": "answered",
            "boundaries": "assumed:only CSV export was discussed",
            "failure": "answered",
            "glossary": "answered",
            "rationale": "answered",
            "out_of_scope": "answered",
        },
        "fit_criterion": "export completes in < 5s for a 10k-row account",
        "glossary_delta": [],
        "confirmed_by": "user",
        "terms_used": [],
    }))


def test_grill_trace_stop_blocks_validation_same_path_as_c1_c5(tmp_path, monkeypatch):
    """A full-canon project (would otherwise pass, per
    ``test_full_canon_project_passes``) with ONE failing grill-trace
    dimension must genuinely block ``validate_phase`` — proving the P4.2
    gate rides the same ``_run_canon_checks`` -> ask-level-issue ->
    ``valid=False`` path C1-C5 use, not a mechanism that only looks
    wired up."""
    _seed_basic_project(tmp_path)
    _seed_canon_artifacts(tmp_path, run_id="project-grill-fail")
    _write_failing_grill_trace(tmp_path)
    monkeypatch.setenv("SHIPWRIGHT_RUN_ID", "project-grill-fail")
    valid, issues = validate_phase("project", tmp_path)
    assert valid is False
    ask_messages = [i["message"] for i in issues if i["severity"] == "ask"]
    assert any("[canon]" in m and "greenfield_assumed" in m for m in ask_messages), issues


def test_clean_grill_trace_does_not_block_validation(tmp_path, monkeypatch):
    """A grill-trace with no STOP condition must not itself turn a
    full-canon project red — the gate blocks bad traces, not the mere
    presence of one."""
    _seed_basic_project(tmp_path)
    _seed_canon_artifacts(tmp_path, run_id="project-grill-clean")
    trace_dir = tmp_path / ".shipwright" / "planning" / "grill-traces"
    trace_dir.mkdir(parents=True, exist_ok=True)
    (trace_dir / "export-data.json").write_text(json.dumps({
        "requirement_key": "export-data",
        "requirement_text": "Users can export their data",
        "surface": "project",
        "evidence": ["interview transcript line 42"],
        "dimensions": {
            "outcome": "answered",
            "purpose": "answered",
            "boundaries": "answered",
            "failure": "answered",
            "glossary": "answered",
            "rationale": "answered",
            "out_of_scope": "answered",
        },
        "fit_criterion": "export completes in < 5s for a 10k-row account",
        "glossary_delta": [],
        "confirmed_by": "user",
        "terms_used": [],
    }))
    monkeypatch.setenv("SHIPWRIGHT_RUN_ID", "project-grill-clean")
    valid, issues = validate_phase("project", tmp_path)
    ask = [i for i in issues if i["severity"] == "ask"]
    assert ask == [], ask
    assert valid is True


def test_fr_trace_coverage_mismatch_does_not_block_validation(tmp_path, monkeypatch):
    """PR #705 Tier-3 review: the Name-cell-slug <-> requirement_key join has
    no stable identity contract, so a mismatch must not hard-block Step 8 the
    way a real STOP condition does — it rides the WARNING/'inform' path, not
    the ERROR/'ask' path C1-C5 and the four closed-vocabulary STOPs use. A
    full-canon project with one traced requirement but two FR rows (a
    genuinely legitimate state: the FR-join heuristic just can't confirm the
    second one) must still validate."""
    _seed_basic_project(tmp_path)
    _seed_canon_artifacts(tmp_path, run_id="project-fr-join-mismatch")
    trace_dir = tmp_path / ".shipwright" / "planning" / "grill-traces"
    trace_dir.mkdir(parents=True, exist_ok=True)
    (trace_dir / "user-login.json").write_text(json.dumps({
        "requirement_key": "user-login",
        "requirement_text": "Users can log in",
        "surface": "project",
        "evidence": ["interview transcript line 12"],
        "dimensions": {
            "outcome": "answered",
            "purpose": "answered",
            "boundaries": "answered",
            "failure": "answered",
            "glossary": "answered",
            "rationale": "answered",
            "out_of_scope": "answered",
        },
        "fit_criterion": "a valid email/password pair returns a session token",
        "glossary_delta": [],
        "confirmed_by": "user",
        "terms_used": [],
    }))
    # 01-auth/spec.md already exists (seeded by _seed_basic_project) — give it
    # an FR table with a second row that has no matching grill-trace.
    (tmp_path / ".shipwright" / "planning" / "01-auth" / "spec.md").write_text(
        "# spec\n\n## 2. Functional Requirements\n\n"
        "| ID | Area | Name | Priority | Description | Basis | Layers |\n"
        "|---|---|---|---|---|---|---|\n"
        "| FR-01.01 | Auth | User login | Must | ... | interview | unit |\n"
        "| FR-01.02 | Auth | Password reset | Must | ... | interview | unit |\n",
    )
    monkeypatch.setenv("SHIPWRIGHT_RUN_ID", "project-fr-join-mismatch")
    valid, issues = validate_phase("project", tmp_path)
    ask = [i["message"] for i in issues if i["severity"] == "ask"]
    inform = [i["message"] for i in issues if i["severity"] == "inform"]
    assert not any("fr_trace_coverage" in m for m in ask), ask
    assert any("fr_trace_coverage" in m for m in inform), inform
    assert valid is True, issues
