"""Fail-closed guard: a NON-DRIVABLE run config is refused with NO side effects.

Replaces the dual-mode back-compat suite (``test_single_session_backcompat.py``),
whose premise — "a ``multi_session`` run stays on the OLD path, untouched" — died with
the mode itself (``iterate-2026-07-14-remove-multi-session``). What survives, and
matters more now, is the belt-and-suspenders half of that suite: **every execution
entry point refuses a config it cannot drive, and writes nothing while doing so.**

THE INVARIANT under test: a run is drivable **iff** its config records the explicit
literal ``mode: "single_session"``. Two kinds of config are therefore non-drivable:

  * a stale ``mode: "multi_session"`` config — an explicit choice whose engine is gone;
  * a mode-less pre-SS1 config — one that never declared a mode at all.

Both are refused with ``mode_unsupported`` + an actionable migration message, and
crucially **before any claim, mutation, file write, or event append** — so a user who
hits this can migrate (one line) without first having to undo damage.

The configs here are written to disk DIRECTLY rather than through ``create_config``,
because the factory now rejects the removed mode outright (that rejection has its own
test in ``test_run_config_mode.py``).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "lib"))

from orchestrator import create_config  # noqa: E402
from orchestrator_pkg import single_session_loop as loop  # noqa: E402
from orchestrator_pkg import single_session_recovery as rec  # noqa: E402
from orchestrator_pkg.router import dispatch_lifecycle  # noqa: E402
from single_session import observability as obs  # noqa: E402
from single_session.loop_state import (  # noqa: E402
    init_loop_state,
    loop_state_path,
    save_loop_state,
)

CONFIG_NAME = "shipwright_run_config.json"


def _write_config(project_root: Path, mode: str | None) -> dict:
    """Write a v2 config carrying ``mode`` (or none at all) straight to disk."""
    config = {
        "schemaVersion": 2,
        "runId": "run-deadbeef",
        "status": "in_progress",
        "splits_frozen": [],
        "completed_phase_task_ids": [],
        "phase_tasks": [{
            "phaseTaskId": "ptk-00000001",
            "phase": "project",
            "splitId": None,
            "sessionUuid": "11111111-2222-3333-4444-555555555555",
            "version": 1,
            "status": "awaiting_launch",
            "slashCommand": "/shipwright-project",
            "prerequisites": [],
            "claimedBySessionUuid": None,
            "executionCount": 0,
            "result": None,
            "errors": [],
        }],
    }
    if mode is not None:
        config["mode"] = mode
    (project_root / CONFIG_NAME).write_text(json.dumps(config, indent=2), encoding="utf-8")
    return config


def _no_side_effects(project_root: Path) -> bool:
    """No loop pointer, no telemetry — the run was not touched."""
    return (
        not loop_state_path(project_root).exists()
        and not obs.events_path(project_root).exists()
    )


def _task_status(project_root: Path) -> str:
    cfg = json.loads((project_root / CONFIG_NAME).read_text(encoding="utf-8"))
    return cfg["phase_tasks"][0]["status"]


# Both flavours of non-drivable config get the identical treatment.
NON_DRIVABLE = ("multi_session", None)


# --------------------------------------------------------------------------- #
# The loop refuses to dispatch
# --------------------------------------------------------------------------- #

def test_resolve_next_dispatch_refuses_stale_multi_session(tmp_project):
    _write_config(tmp_project, "multi_session")
    res = loop.resolve_next_dispatch(tmp_project)
    assert res["action"] == "mode_unsupported"
    assert res["mode"] == "multi_session"
    # The message must name the removed mode AND the one-line fix.
    assert "multi_session" in res["message"]
    assert '"mode": "single_session"' in res["message"]
    assert "migrations/multi-session-to-single-session.md" in res["message"]


def test_resolve_next_dispatch_refuses_mode_less_legacy_config(tmp_project):
    """A pre-SS1 config never declared a mode. It is NOT inferred — inferring one is
    exactly the silent reinterpretation this guard exists to prevent."""
    _write_config(tmp_project, None)
    res = loop.resolve_next_dispatch(tmp_project)
    assert res["action"] == "mode_unsupported"
    assert res["mode"] is None
    assert '"mode": "single_session"' in res["message"]


# --------------------------------------------------------------------------- #
# Refusal is side-effect free — nothing claimed, nothing written, nothing emitted
# --------------------------------------------------------------------------- #

def test_next_dispatch_claims_nothing_on_refusal(tmp_project):
    """``next_dispatch`` (not just ``resolve_``) must not reach the CAS claim."""
    for mode in NON_DRIVABLE:
        _write_config(tmp_project, mode)
        res = loop.next_dispatch(tmp_project)
        assert res["action"] == "mode_unsupported", mode
        assert _task_status(tmp_project) == "awaiting_launch", (
            f"mode={mode}: the phase task was CLAIMED despite the refusal"
        )
        assert _no_side_effects(tmp_project), f"mode={mode}: refusal wrote state/telemetry"


def test_resume_refuses_and_writes_nothing(tmp_project):
    for mode in NON_DRIVABLE:
        _write_config(tmp_project, mode)
        assert rec.resume_run(tmp_project)["action"] == "mode_unsupported", mode
        # --confirm is the COMMITTING call: it must not emit a resume event either.
        assert rec.resume_run(tmp_project, confirm=True)["action"] == "mode_unsupported", mode
        assert _no_side_effects(tmp_project), mode


def test_human_gate_refuses_and_writes_nothing(tmp_project):
    for mode in NON_DRIVABLE:
        _write_config(tmp_project, mode)
        res = rec.mark_human_gate(tmp_project, phase_task_id="ptk", phase="plan", paused=True)
        assert res["ok"] is False and res["action"] == "mode_unsupported", mode
        assert _no_side_effects(tmp_project), mode


def test_recover_refuses_and_writes_nothing(tmp_project):
    for mode in NON_DRIVABLE:
        _write_config(tmp_project, mode)
        res = rec.recover_single_session(tmp_project, phase_task_id="ptk")
        assert res["ok"] is False and res["action"] == "mode_unsupported", mode
        assert _no_side_effects(tmp_project), mode


# --------------------------------------------------------------------------- #
# The GENERIC lifecycle CLI is guarded too (external code review, GPT F2)
#
# The loop's own guard would be worthless if the same mutations were one CLI call away:
# `claim-phase-task` et al. are mode-agnostic by design (they were the multi-session
# hooks' API), so without this they would happily advance a stale run.
# --------------------------------------------------------------------------- #

ADVANCING = (
    ("claim-phase-task", dict(phase_task_id="ptk-00000001",
                              session_uuid="11111111-2222-3333-4444-555555555555",
                              expected_phase="project")),
    ("complete-phase-task", dict(phase_task_id="ptk-00000001",
                                 session_uuid="11111111-2222-3333-4444-555555555555",
                                 version=1, result_json="unused.json")),
    ("mark-phase-failed", dict(phase_task_id="ptk-00000001",
                               session_uuid="11111111-2222-3333-4444-555555555555",
                               version=1, error="x")),
    ("freeze-splits", {}),
    ("plan-next-phase", dict(phase_task_id="ptk-00000001")),
)


@pytest.mark.parametrize("command,kwargs", ADVANCING, ids=[c for c, _ in ADVANCING])
def test_advancing_lifecycle_command_refused_on_non_drivable_config(
    tmp_project, command, kwargs, capsys,
):
    for mode in NON_DRIVABLE:
        _write_config(tmp_project, mode)
        rc = dispatch_lifecycle(
            argparse.Namespace(command=command, **kwargs), tmp_project,
        )
        assert rc == 1, f"{command} (mode={mode}) was not refused"
        payload = json.loads(capsys.readouterr().out)
        assert payload["reason"] == "mode_unsupported", command
        # ...and it mutated nothing on the way out.
        assert _task_status(tmp_project) == "awaiting_launch", command
        assert _no_side_effects(tmp_project), command


def test_read_only_lifecycle_commands_still_work_on_a_stale_config(tmp_project, capsys):
    """EXEMPT ON PURPOSE: the guard lives on the execution path, never the read path, so
    a historical run stays inspectable (WebUI run history, .shipwright/runs/**)."""
    _write_config(tmp_project, "multi_session")
    rc = dispatch_lifecycle(
        argparse.Namespace(command="get-phase-task", phase_task_id="ptk-00000001"),
        tmp_project,
    )
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True


def test_recover_phase_task_still_works_on_a_stale_config(tmp_project, capsys):
    """EXEMPT ON PURPOSE: `recover-phase-task` is the manual escape hatch, and the
    documented migration of a run whose phase is wedged `in_progress` CALLS it. Guarding
    it would make exactly the runs that most need migrating unrecoverable. It cannot
    advance a pipeline — it only releases a claim and bumps the CAS version."""
    _write_config(tmp_project, "multi_session")
    rc = dispatch_lifecycle(
        argparse.Namespace(command="recover-phase-task", phase_task_id="ptk-00000001",
                           force_status="awaiting_launch"),
        tmp_project,
    )
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True


# --------------------------------------------------------------------------- #
# The happy path still works (the guard is not over-broad)
# --------------------------------------------------------------------------- #

def test_removed_literal_is_refused_even_without_schema_version(tmp_project):
    """A hand-edited config that lost its `schemaVersion` but still records the REMOVED
    literal must get the migration message, not a misleading `no_config` — whoever wrote
    `mode: multi_session` meant a pipeline (external review, GPT).

    The mode-LESS arm stays scoped to v2 on purpose: a v1/standalone config also has no
    `mode`, but it is not a pipeline run at all, and telling its owner to "set
    mode: single_session" would be nonsense. Pinned below.
    """
    _write_config(tmp_project, "multi_session")
    config = json.loads((tmp_project / CONFIG_NAME).read_text(encoding="utf-8"))
    del config["schemaVersion"]
    (tmp_project / CONFIG_NAME).write_text(json.dumps(config), encoding="utf-8")

    res = loop.resolve_next_dispatch(tmp_project)
    assert res["action"] == "mode_unsupported"
    assert "REMOVED" in res["message"]


def test_v1_standalone_config_is_not_told_to_set_a_mode(tmp_project):
    """A standalone project (v1, no schemaVersion, no mode) is NOT a pipeline run. It must
    fall through to `no_config`, never to a migration message it cannot act on."""
    (tmp_project / CONFIG_NAME).write_text(
        json.dumps({"status": "complete", "standalone": True}), encoding="utf-8",
    )
    assert loop.resolve_next_dispatch(tmp_project)["action"] == "no_config"


def test_explicit_single_session_config_is_drivable(tmp_project):
    _write_config(tmp_project, "single_session")
    res = loop.resolve_next_dispatch(tmp_project)
    assert res["action"] == "dispatch"
    assert res["dispatch"]["phase"] == "project"


def test_pre_ss5_single_session_loop_state_resumes_without_events_file(tmp_project):
    """Back-compat that DOES still apply: an SS3/SS4-era single_session run (loop_state
    persisted, no run_loop_events.jsonl yet) resumes cleanly."""
    cfg = create_config(
        "full_app", "supabase-nextjs", "guided", "jelastic-dev",
        tmp_project, mode="single_session",
    )
    save_loop_state(tmp_project, init_loop_state(cfg["runId"]))
    assert not obs.events_path(tmp_project).exists()

    res = rec.resume_run(tmp_project)  # read-only detection must not choke
    assert res["action"] == "resume"
    assert res["resumeAction"] == "dispatch"
    # Still no events file — read-only detection emits nothing.
    assert not obs.events_path(tmp_project).exists()
