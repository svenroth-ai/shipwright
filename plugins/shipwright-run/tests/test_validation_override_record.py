"""Overriding a phase gate runs the check anyway and leaves evidence.

FR-01.01 (E): *"Given a person decides to go ahead regardless, when the phase is
marked finished anyway, then what was overridden and why is recorded — so
afterwards 'passed its checks' and 'was waved through' can still be told apart."*

Before this suite, ``update_step(force=True)`` skipped ``validate_phase``
entirely: no finding, no record, and a completed step that passed cleanly was
byte-identical to one that was waved through. Every test below pins one half of
that: **the check still runs**, and **the answer lands somewhere**.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "lib"))

from orchestrator import create_config, load_run_config, update_step  # noqa: E402
from orchestrator_pkg.validation_record import (  # noqa: E402
    GATE_ERROR_PREFIX,
    MAX_VALIDATION_OVERRIDES,
    VALIDATION_OVERRIDES_DROPPED_KEY,
    VALIDATION_OVERRIDES_KEY,
    record_validation_override,
)

REASON = "release window closes tonight; missing mockups tracked in #123"
ASK = {"severity": "ask", "message": "Missing spec.md for splits: 01-core"}
INFORM = {"severity": "inform", "message": "E2E flakiness noted"}


@pytest.fixture
def run_project(tmp_project, mocker):
    """A non-standalone run the v1 completion path can actually advance, with the
    compliance subprocess stubbed out.

    The `mode` literal is dropped on purpose: `update-step` is INERT in a driven
    `mode: single_session` run (`single-session-apply` owns completion there, and
    that path has no `--force` at all), so the override rule under test is only
    reachable on a v1 / legacy / adopted config.
    """
    mocker.patch("orchestrator.run_compliance_update", return_value=None)
    create_config(
        scope="full_app", profile="supabase-nextjs", autonomy="guided",
        deploy_target="jelastic-dev", project_root=tmp_project,
    )
    path = tmp_project / "shipwright_run_config.json"
    config = json.loads(path.read_text(encoding="utf-8"))
    del config["mode"]
    path.write_text(json.dumps(config), encoding="utf-8")
    return tmp_project


def _gate(mocker, *issues):
    """Patch the gate's verdict. Patches the MODULE attribute, which only works
    because run_phase_gate imports validate_phase lazily at call time."""
    return mocker.patch(
        "phase_validators.validate_phase",
        return_value=(not any(i["severity"] == "ask" for i in issues), list(issues)),
    )


def _overrides(project_root):
    return load_run_config(project_root).get(VALIDATION_OVERRIDES_KEY, [])


# --------------------------------------------------------------------------- #
# The check runs regardless (AC1)
# --------------------------------------------------------------------------- #

def test_force_still_runs_the_phase_gate(run_project, mocker):
    """The regression this whole iterate exists for: `not force` used to gate the
    validator call itself, so an override produced no finding to record."""
    spy = _gate(mocker)
    update_step(run_project, "project", "complete", force=True, force_reason=REASON)
    spy.assert_called_once_with("project", run_project)


def test_the_validate_phase_patch_target_still_intercepts(run_project, mocker):
    """Guard on the lazy import in run_phase_gate. Hoisting it to module scope
    would bind past `phase_validators.validate_phase` and silently un-patch every
    test above — a failure that shows up as tests passing for the wrong reason."""
    spy = _gate(mocker, ASK)
    update_step(run_project, "project", "complete", force=True, force_reason=REASON)
    assert spy.called
    assert _overrides(run_project)[-1]["overridden_issues"] == [ASK]


# --------------------------------------------------------------------------- #
# Passed vs waved through (AC2, AC3)
# --------------------------------------------------------------------------- #

def test_a_clean_completion_records_no_override(run_project, mocker):
    """The other half of "tellable apart": a step that genuinely passed writes no
    record, so the mere presence of one is the signal."""
    _gate(mocker)
    update_step(run_project, "project", "complete")
    assert VALIDATION_OVERRIDES_KEY not in load_run_config(run_project)


def test_a_waved_through_completion_is_recorded_with_what_and_why(run_project, mocker):
    _gate(mocker, ASK, INFORM)
    update_step(run_project, "project", "complete", force=True, force_reason=REASON)

    record = _overrides(run_project)[-1]
    assert record["step"] == "project"
    assert record["waived"] is True
    assert record["gate_result"] == "fail"
    assert record["reason"] == REASON
    assert record["overridden_issues"] == [ASK]
    assert record["inform_count"] == 1
    assert record["at"]
    # …and the step really did complete — the override is evidence, not a block.
    assert "project" in load_run_config(run_project)["completed_steps"]


def test_force_over_a_clean_gate_records_a_pass_not_a_waiver(run_project, mocker):
    """Force was used but nothing was actually waived. That is a third state and
    it must not masquerade as a waiver."""
    _gate(mocker)
    update_step(run_project, "project", "complete", force=True, force_reason=REASON)

    record = _overrides(run_project)[-1]
    assert record["waived"] is False
    assert record["gate_result"] == "pass"
    assert record["overridden_issues"] == []


def test_the_record_survives_the_real_config_writer(run_project, mocker):
    """Round-trip through save_run_config to on-disk JSON — not an in-memory dict.
    A reserialization path that dropped unknown keys would erase the evidence."""
    _gate(mocker, ASK)
    update_step(run_project, "project", "complete", force=True, force_reason=REASON)

    on_disk = json.loads(
        (run_project / "shipwright_run_config.json").read_text(encoding="utf-8"),
    )
    assert on_disk[VALIDATION_OVERRIDES_KEY][-1]["reason"] == REASON

    # …and a later unrelated write does not drop it.
    update_step(run_project, "design", "in_progress")
    assert _overrides(run_project)[-1]["reason"] == REASON


# --------------------------------------------------------------------------- #
# The pause rule is unchanged (AC5) + retry (O5)
# --------------------------------------------------------------------------- #

def test_ask_issues_without_force_still_pause_the_run(run_project, mocker):
    _gate(mocker, ASK)
    config = update_step(run_project, "project", "complete")

    assert config["status"] == "needs_validation"
    assert config["validation_issues"] == [{"step": "project", **ASK}]
    assert "project" not in config.get("completed_steps", [])
    assert VALIDATION_OVERRIDES_KEY not in config


def test_a_forced_retry_clears_the_stale_pause_issues(run_project, mocker):
    """Pause, then go ahead. The completed step must not still carry findings that
    imply it is stuck — what the gate said is preserved in the override record."""
    gate = _gate(mocker, ASK)
    update_step(run_project, "project", "complete")
    assert load_run_config(run_project)["status"] == "needs_validation"

    gate.return_value = (True, [])          # the operator fixed it in between
    config = update_step(run_project, "project", "complete", force=True, force_reason=REASON)

    assert "validation_issues" not in config
    assert "project" in config["completed_steps"]
    assert _overrides(run_project)[-1]["gate_result"] == "pass"


# --------------------------------------------------------------------------- #
# A reason is mandatory (AC4)
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("reason", [None, "", "   ", "\n\t "])
def test_force_without_a_reason_is_refused_before_anything_is_written(
    run_project, mocker, reason,
):
    spy = _gate(mocker, ASK)
    with pytest.raises(ValueError, match="requires a reason"):
        update_step(run_project, "project", "complete", force=True, force_reason=reason)

    spy.assert_not_called()                                  # refused up front
    config = load_run_config(run_project)
    assert "project" not in config.get("completed_steps", [])
    assert VALIDATION_OVERRIDES_KEY not in config


# The CLI surface for the same rule lives in test_update_step_force_reason_cli.py.


# --------------------------------------------------------------------------- #
# Standalone (AC6)
# --------------------------------------------------------------------------- #

def test_standalone_skips_the_gate_and_records_nothing(tmp_path, mocker):
    """No interactive person means nobody overrode anything — so there is nothing
    to record, and a reason is not demanded either."""
    mocker.patch("orchestrator.run_compliance_update", return_value=None)
    spy = _gate(mocker, ASK)

    config = update_step(tmp_path, "project", "complete", force=True)

    spy.assert_not_called()
    assert config["standalone"] is True
    assert VALIDATION_OVERRIDES_KEY not in config


# --------------------------------------------------------------------------- #
# A broken validator must not wedge the run (external review G1)
# --------------------------------------------------------------------------- #

def test_a_crashing_validator_does_not_wedge_the_force_path(run_project, mocker):
    """Force used to be the escape hatch for a broken validator precisely because
    it skipped it. Now that force runs the gate, a raising validator would
    otherwise leave no way to complete the phase at all."""
    mocker.patch("phase_validators.validate_phase", side_effect=RuntimeError("boom"))

    config = update_step(run_project, "project", "complete", force=True, force_reason=REASON)

    assert "project" in config["completed_steps"]
    record = _overrides(run_project)[-1]
    assert record["waived"] is True
    assert GATE_ERROR_PREFIX in record["overridden_issues"][0]["message"]
    assert "RuntimeError: boom" in record["overridden_issues"][0]["message"]


def test_a_crashing_validator_pauses_the_unforced_path(run_project, mocker):
    """Fail-closed with a readable reason rather than a traceback out of the CLI."""
    mocker.patch("phase_validators.validate_phase", side_effect=RuntimeError("boom"))

    config = update_step(run_project, "project", "complete")

    assert config["status"] == "needs_validation"
    assert GATE_ERROR_PREFIX in config["validation_issues"][0]["message"]


# --------------------------------------------------------------------------- #
# Findings that are not ask-level, and the opt-in critical gate (external review O2)
# --------------------------------------------------------------------------- #

def test_inform_notes_are_recorded_on_the_forced_path_too(run_project, mocker):
    """They used to be dropped: force skipped the validator, so there were no
    inform issues to record either."""
    _gate(mocker, INFORM)
    config = update_step(run_project, "project", "complete", force=True, force_reason=REASON)

    assert config["validation_notes"] == [{"step": "project", **INFORM}]
    assert _overrides(run_project)[-1]["gate_result"] == "pass"   # inform never blocks


def test_critical_gate_failures_are_overridable_and_recorded(run_project, mocker, monkeypatch):
    """The opt-in Phase-Quality gate keeps its semantics through the extraction —
    and is no longer skipped under force."""
    monkeypatch.setenv("SHIPWRIGHT_ENFORCE_CRITICAL_GATES", "1")
    findings = run_project / ".shipwright" / "compliance" / "skill-compliance"
    findings.mkdir(parents=True)
    (findings / "project-run1-sess1.json").write_text(json.dumps({
        "workflow": [{"id": "W5", "status": "FAIL", "evidence": "no ADR for the run"}],
    }), encoding="utf-8")
    _gate(mocker)

    paused = update_step(run_project, "project", "complete")
    assert paused["status"] == "needs_validation"

    update_step(run_project, "project", "complete", force=True, force_reason=REASON)
    record = _overrides(run_project)[-1]
    assert record["waived"] is True
    assert "W5" in record["overridden_issues"][0]["name"]


# --------------------------------------------------------------------------- #
# Retention is bounded but never silent (external review O6)
# --------------------------------------------------------------------------- #

def test_override_retention_is_capped_and_the_drop_is_counted(run_project):
    config = load_run_config(run_project)
    for i in range(MAX_VALIDATION_OVERRIDES + 3):
        record_validation_override(
            config, "project", reason=f"reason {i}", ask_issues=[ASK], inform_issues=[],
        )

    log = config[VALIDATION_OVERRIDES_KEY]
    assert len(log) == MAX_VALIDATION_OVERRIDES
    assert log[-1]["reason"] == f"reason {MAX_VALIDATION_OVERRIDES + 2}"
    # The evidence that went missing is counted, not silently dropped.
    assert config[VALIDATION_OVERRIDES_DROPPED_KEY] == 3
