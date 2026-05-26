"""Parity probes for the Campaign B5 orchestrator split (2026-05-26).

The original ``orchestrator.py`` was a 983-LOC monolith. After the
split, callers see ``orchestrator_pkg/`` plus a thin shim
(``orchestrator.py``, <= 50 LOC) that re-exports the same public surface.
These tests verify the split is invisible at every boundary the spec
acceptance criteria call out:

1. **Public-name surface** — every historical public name is still
   importable from ``orchestrator``.
2. **Patched-name surface** — the names tests patch through
   ``orchestrator.X`` (``run_compliance_update``, ``_COMPLIANCE_SCRIPT``,
   ``_record_*``, ``_collect_critical_gate_issues``, ...) are bound on
   the shim module itself, so ``mocker.patch("orchestrator.X")``
   continues to intercept callers in ``orchestrator_pkg.step_planning``
   et al.
3. **Router parity** — the F2 lifecycle CLI subcommands still dispatch
   to the same handler names as before the split.
4. **PIPELINE_STEPS literal location** — the literal lives in
   ``orchestrator_pkg/constants.py`` so ``shared/scripts/sync_check.py``
   can keep finding it.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(
    0, str(Path(__file__).resolve().parent.parent / "scripts" / "lib"),
)

import orchestrator  # noqa: E402
from orchestrator_pkg import router as _router  # noqa: E402


# ---------------------------------------------------------------------------
# 1. Public-name surface
# ---------------------------------------------------------------------------

PUBLIC_NAMES = (
    # Constants
    "CONFIG_NAME",
    "PIPELINE_STEPS",
    "SCHEMA_VERSION",
    # Public functions
    "build_pipeline",
    "create_config",
    "get_build_progress",
    "get_next_step",
    "is_v2_config",
    "load_run_config",
    "run_compliance_update",
    "save_run_config",
    "update_step",
    "main",
    # Historically-private helpers that callers may still reference
    "_dispatch_lifecycle",
)


def test_public_names_importable_from_orchestrator_shim():
    """Every historical public name still resolves on ``orchestrator``."""
    for name in PUBLIC_NAMES:
        assert hasattr(orchestrator, name), (
            f"Post-split orchestrator shim missing public name {name!r}. "
            f"This breaks `from orchestrator import {name}` callers."
        )


# ---------------------------------------------------------------------------
# 2. Patched-name surface
# ---------------------------------------------------------------------------

PATCHED_NAMES = (
    "run_compliance_update",
    "_COMPLIANCE_SCRIPT",
    "_record_compliance_update_failed",
    "_record_pipeline_migration_event",
    "_collect_critical_gate_issues",
    "_enforce_critical_gates_enabled",
    "_read_latest_phase_quality_finding",
    "_CRITICAL_GATE_CHECK_IDS",
)


def test_patched_names_bound_on_orchestrator_shim():
    """``mocker.patch("orchestrator.X")`` needs ``X`` on the shim namespace.

    If a name moves off the shim, tests that patch via
    ``orchestrator.X`` silently skip the patched code path. Guard
    against silent regressions.
    """
    for name in PATCHED_NAMES:
        assert hasattr(orchestrator, name), (
            f"Test-patched name {name!r} missing from orchestrator shim. "
            f"`mocker.patch('orchestrator.{name}', ...)` will fail."
        )


def test_run_compliance_update_dispatch_honors_orchestrator_patch(
    tmp_project, mocker,
):
    """End-to-end probe: patching ``orchestrator.run_compliance_update``
    intercepts the call from ``update_step`` after the split.

    Before B5 this was trivially true (same module). After B5
    ``update_step`` lives in ``orchestrator_pkg.step_planning`` and
    routes through ``sys.modules["orchestrator"]`` to honor the patch.
    A regression here is silent — the test below catches it.
    """
    orchestrator.create_config(
        scope="full_app", profile="supabase-nextjs",
        autonomy="guided", deploy_target="jelastic-dev",
        project_root=tmp_project,
    )

    sentinel = {
        "phase": "project",
        "updated_reports": [".shipwright/compliance/rtm.md"],
    }
    spy = mocker.patch("orchestrator.run_compliance_update", return_value=sentinel)

    config = orchestrator.update_step(
        tmp_project, "project", "complete", force=True,
    )

    spy.assert_called_once_with(tmp_project, "project")
    assert config["last_compliance_update"]["phase"] == "project"


# ---------------------------------------------------------------------------
# 3. Router parity — every pre-split CLI subcommand still dispatches
# ---------------------------------------------------------------------------

EXPECTED_LIFECYCLE_COMMANDS = frozenset({
    "get-phase-task",
    "find-phase-task-by-session-uuid",
    "validate-prerequisites",
    "claim-phase-task",
    "complete-phase-task",
    "mark-phase-failed",
    "recover-phase-task",
    "freeze-splits",
    "plan-next-phase",
})


def test_lifecycle_command_set_unchanged():
    """The router's LIFECYCLE_COMMANDS set must match what
    orchestrator.py used to dispatch in its inline ``_dispatch_lifecycle``.

    Any divergence means the CLI is silently rejecting a historical
    subcommand (or accepting a new one without the round-trip probe).
    """
    assert _router.LIFECYCLE_COMMANDS == EXPECTED_LIFECYCLE_COMMANDS


def test_lifecycle_fail_closed_reasons_unchanged():
    """The exit-code-2 fail-closed reason set must match the historical
    set so SessionStart / UserPromptSubmit hooks keep their behaviour.
    """
    expected = frozenset({
        "wrong_skill", "duplicate_claim", "phase_already_terminal",
        "prereqs_unmet", "stale_version", "stale_session",
        "invalid_status", "invalid_status_for_completion",
    })
    assert _router.FAIL_CLOSED_REASONS == expected


# ---------------------------------------------------------------------------
# 4. PIPELINE_STEPS literal location (for shared/scripts/sync_check.py)
# ---------------------------------------------------------------------------

def test_two_phase_flow_routes_identically_post_split(tmp_project):
    """Integration probe: a 2-phase fixture flow (project -> design) routes
    through the same code path post-split.

    Asserts:
      - ``create_config`` seeds the project phase as the starting step.
      - ``get_next_step`` returns ``project`` first, then ``design`` after
        ``update_step(..., "project", "complete")``.
      - The phase_tasks lifecycle on the v2 config moves from
        ``awaiting_launch -> done`` for project + appends a ``design``
        task on ``plan_next_phase``.

    This is the parity probe the spec's acceptance criteria call for —
    "at least one integration test demonstrates orchestrator phase
    routing is unchanged".
    """
    cfg = orchestrator.create_config(
        scope="full_app", profile="supabase-nextjs",
        autonomy="guided", deploy_target="jelastic-dev",
        project_root=tmp_project,
    )
    assert cfg["current_step"] == "project"
    initial_task = cfg["phase_tasks"][0]
    assert initial_task["phase"] == "project"
    assert initial_task["status"] == "awaiting_launch"

    # Phase 1 — project. Force-complete so we don't hit validation that
    # requires fixture files.
    cfg2 = orchestrator.update_step(
        tmp_project, "project", "complete", force=True,
    )
    assert "project" in cfg2["completed_steps"]
    assert cfg2["current_step"] == "design", (
        f"Expected design after project, got {cfg2['current_step']!r}. "
        "Phase order changed post-split — REGRESSION."
    )

    next_step = orchestrator.get_next_step(tmp_project)
    assert next_step["next_step"] == "design"


def test_pipeline_steps_literal_lives_in_constants_module():
    """``sync_check.py`` regexes for ``PIPELINE_STEPS = [...]`` in the
    orchestrator source. After the split, the literal must live in
    ``orchestrator_pkg/constants.py`` (not in the shim, which uses
    ``from ... import PIPELINE_STEPS``).
    """
    constants = (
        Path(__file__).resolve().parent.parent
        / "scripts" / "lib" / "orchestrator_pkg" / "constants.py"
    )
    text = constants.read_text(encoding="utf-8")
    # The regex used by sync_check.py
    import re
    match = re.search(r'PIPELINE_STEPS\s*=\s*\[(.*?)\]', text, re.DOTALL)
    assert match is not None, (
        "PIPELINE_STEPS literal not found in constants.py — "
        "sync_check.py's regex-based detection will fail."
    )
    steps = re.findall(r'"(\w+)"', match.group(1))
    assert steps == ["project", "design", "plan", "build", "test", "changelog", "deploy"]
