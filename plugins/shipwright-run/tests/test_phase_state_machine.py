"""Tests for phase_state_machine — pure-function pipeline transitions.

Covers all 14 transitions in the Plan v3 state-machine table plus error/edge
cases (unknown phase, splitId mismatch, defensive coercions).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "lib"))

from phase_state_machine import (  # noqa: E402
    CompletedPhaseTask,
    RunConditions,
    freeze_run_conditions,
    initial_phase_spec,
    next_phase_task,
)


# ---- Test fixtures ----


def _rc(*, security: bool = False, split_mode=None) -> RunConditions:
    return {
        "securityEnabled": security,
        "splitMode": split_mode,
        "aikidoClientIdPresent": security,
    }


def _completed(phase, *, split_id=None, status="done") -> CompletedPhaseTask:
    return {
        "phaseTaskId": f"ptk-{phase[:4]}",
        "phase": phase,
        "splitId": split_id,
        "status": status,
    }


# ---- Initial state ----


def test_initial_phase_is_project():
    spec = initial_phase_spec()
    assert spec["phase"] == "project"
    assert spec["splitId"] is None
    assert spec["prerequisites"] == []
    assert spec["slashCommand"] == "/shipwright-project"
    assert spec["titleSuffix"] == "project"


# ---- 14 transitions from the plan v3 table ----


def test_project_done_to_design():
    spec = next_phase_task(
        run_conditions=_rc(),
        splits_frozen=[],
        completed=_completed("project"),
    )
    assert spec is not None
    assert spec["phase"] == "design"
    assert spec["splitId"] is None
    assert spec["prerequisites"] == ["ptk-proj"]


def test_design_done_per_split_to_first_plan_split():
    spec = next_phase_task(
        run_conditions=_rc(split_mode="per_split"),
        splits_frozen=["01-core", "02-ui"],
        completed=_completed("design"),
    )
    assert spec is not None
    assert spec["phase"] == "plan"
    assert spec["splitId"] == "01-core"
    assert spec["titleSuffix"] == "plan / 01-core"


def test_design_done_no_split_mode_to_split_less_plan():
    spec = next_phase_task(
        run_conditions=_rc(split_mode="none"),
        splits_frozen=[],
        completed=_completed("design"),
    )
    assert spec is not None
    assert spec["phase"] == "plan"
    assert spec["splitId"] is None
    assert spec["titleSuffix"] == "plan"


def test_design_done_per_split_with_no_splits_coerces_to_split_less():
    """Defensive: per_split declared but splits_frozen empty -> single pass."""
    spec = next_phase_task(
        run_conditions=_rc(split_mode="per_split"),
        splits_frozen=[],
        completed=_completed("design"),
    )
    assert spec is not None
    assert spec["phase"] == "plan"
    assert spec["splitId"] is None


def test_plan_split_done_to_build_same_split():
    spec = next_phase_task(
        run_conditions=_rc(split_mode="per_split"),
        splits_frozen=["01-core"],
        completed=_completed("plan", split_id="01-core"),
    )
    assert spec is not None
    assert spec["phase"] == "build"
    assert spec["splitId"] == "01-core"


def test_plan_split_less_done_to_split_less_build():
    spec = next_phase_task(
        run_conditions=_rc(split_mode="none"),
        splits_frozen=[],
        completed=_completed("plan"),
    )
    assert spec is not None
    assert spec["phase"] == "build"
    assert spec["splitId"] is None


def test_build_split_done_with_more_splits_to_next_plan_split():
    spec = next_phase_task(
        run_conditions=_rc(split_mode="per_split"),
        splits_frozen=["01-core", "02-ui", "03-features"],
        completed=_completed("build", split_id="01-core"),
    )
    assert spec is not None
    assert spec["phase"] == "plan"
    assert spec["splitId"] == "02-ui"


def test_build_split_done_last_split_to_test():
    spec = next_phase_task(
        run_conditions=_rc(split_mode="per_split"),
        splits_frozen=["01-core", "02-ui"],
        completed=_completed("build", split_id="02-ui"),
    )
    assert spec is not None
    assert spec["phase"] == "test"
    assert spec["splitId"] is None


def test_build_split_less_done_to_test():
    spec = next_phase_task(
        run_conditions=_rc(split_mode="none"),
        splits_frozen=[],
        completed=_completed("build"),
    )
    assert spec is not None
    assert spec["phase"] == "test"
    assert spec["splitId"] is None


def test_test_done_always_to_changelog():
    """Post-decouple (sec-report-and-orchestrator-decouple): test → changelog
    unconditionally. The securityEnabled field stays in RunConditions for
    schema compatibility with shipwright-webui but no longer gates routing.
    """
    spec = next_phase_task(
        run_conditions=_rc(security=False),
        splits_frozen=[],
        completed=_completed("test"),
    )
    assert spec is not None
    assert spec["phase"] == "changelog"


def test_test_done_to_changelog_even_when_securityenabled_true_legacy_value():
    """Legacy run-configs may have ``securityEnabled: true`` baked in. Post-
    decouple the state machine must NOT route to security based on that flag —
    test always advances to changelog.
    """
    spec = next_phase_task(
        run_conditions=_rc(security=True),  # legacy field value, ignored now
        splits_frozen=[],
        completed=_completed("test"),
    )
    assert spec is not None
    assert spec["phase"] == "changelog"


def test_security_done_to_changelog_legacy_grace_path():
    """Legacy phase_tasks already serialized with ``phase: "security"`` (e.g.
    from runs that started before this iterate shipped) must still advance
    to changelog when their status becomes terminal. The branch is dead for
    new runs but kept as legacy-grace.
    """
    spec = next_phase_task(
        run_conditions=_rc(security=True),
        splits_frozen=[],
        completed=_completed("security"),
    )
    assert spec is not None
    assert spec["phase"] == "changelog"


def test_changelog_done_to_deploy():
    spec = next_phase_task(
        run_conditions=_rc(),
        splits_frozen=[],
        completed=_completed("changelog"),
    )
    assert spec is not None
    assert spec["phase"] == "deploy"


def test_deploy_done_returns_none_pipeline_terminal():
    spec = next_phase_task(
        run_conditions=_rc(),
        splits_frozen=[],
        completed=_completed("deploy"),
    )
    assert spec is None


# ---- Edge cases ----


def test_unknown_phase_raises():
    with pytest.raises(ValueError, match="Unknown phase"):
        next_phase_task(
            run_conditions=_rc(),
            splits_frozen=[],
            completed={
                "phaseTaskId": "ptk-bogus",
                "phase": "bogus",  # type: ignore[typeddict-item]
                "splitId": None,
                "status": "done",
            },
        )


def test_build_split_id_not_in_frozen_falls_through_to_test():
    """Defensive: corrupted state where split_id is no longer in splits_frozen."""
    spec = next_phase_task(
        run_conditions=_rc(split_mode="per_split"),
        splits_frozen=["01-core", "02-ui"],
        completed=_completed("build", split_id="99-orphan"),
    )
    assert spec is not None
    assert spec["phase"] == "test"


def test_failure_status_returns_structural_successor():
    """next_phase_task does not branch on failure — orchestrator decides whether to materialize."""
    spec = next_phase_task(
        run_conditions=_rc(),
        splits_frozen=[],
        completed=_completed("project", status="failed"),
    )
    assert spec is not None
    assert spec["phase"] == "design"


def test_skipped_status_returns_structural_successor():
    spec = next_phase_task(
        run_conditions=_rc(),
        splits_frozen=[],
        completed=_completed("test", status="skipped"),
    )
    assert spec is not None
    assert spec["phase"] == "changelog"


# ---- runConditions freeze helper (post-decouple signature) ----
#
# Iterate `sec-report-and-orchestrator-decouple` removed `scanner_available`
# from the parameter list. `securityEnabled` is hardcoded to False because
# security is no longer a pipeline phase. `aikidoClientIdPresent` is kept as
# a diagnostic so WebUI consumers can tell whether the user has Aikido
# configured (informational only — does not gate anything).


def test_freeze_run_conditions_default_returns_security_off():
    rc = freeze_run_conditions()
    assert rc["securityEnabled"] is False
    assert rc["aikidoClientIdPresent"] is False
    assert rc["splitMode"] is None


def test_freeze_run_conditions_aikido_id_sets_diagnostic_flag():
    rc = freeze_run_conditions(aikido_client_id="ak_live_xxxx")
    # Diagnostic: user has Aikido configured. Does NOT enable any pipeline phase.
    assert rc["aikidoClientIdPresent"] is True
    # Security still off — the orchestrator no longer auto-runs security.
    assert rc["securityEnabled"] is False


def test_freeze_run_conditions_whitespace_aikido_id_treated_as_absent():
    rc = freeze_run_conditions(aikido_client_id="   ")
    assert rc["aikidoClientIdPresent"] is False
    assert rc["securityEnabled"] is False


def test_freeze_run_conditions_empty_aikido_id_treated_as_absent():
    rc = freeze_run_conditions(aikido_client_id="")
    assert rc["aikidoClientIdPresent"] is False


# ---- Title and slash command sanity ----


def test_slash_commands_match_plugin_names():
    """Each phase planned by the orchestrator has a /shipwright-<phase> slash command.

    Post-decouple (sec-report-and-orchestrator-decouple), security is no longer
    on the planned-successor chain. The test→changelog transition is exercised
    here; the legacy-grace security→changelog path is covered by
    `test_security_done_to_changelog_legacy_grace_path` separately.
    """
    # 'project' is the initial state, no predecessor
    assert initial_phase_spec()["slashCommand"] == "/shipwright-project"

    successors = {
        "design": ("project", None, []),
        "plan": ("design", None, []),  # split_mode=none branch
        "build": ("plan", None, []),
        "test": ("build", None, []),
        "changelog": ("test", None, []),  # was ("security", ...) pre-decouple
        "deploy": ("changelog", None, []),
    }
    for phase, (pred_phase, pred_split, splits) in successors.items():
        spec = next_phase_task(
            run_conditions=_rc(),
            splits_frozen=splits,
            completed=_completed(pred_phase, split_id=pred_split),
        )
        assert spec is not None, f"no spec for predecessor {pred_phase}"
        assert spec["slashCommand"] == f"/shipwright-{phase}"
