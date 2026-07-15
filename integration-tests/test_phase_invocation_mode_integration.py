"""Integration: the phase skills' invocation-mode gate composes with the real lifecycle.

`cross_component` coverage for iterate-2026-07-14-phase-invocation-mode. The unit tests
pin each component in isolation; this drives the ACTUAL pipeline — `create_config` ->
`claim_phase_task` -> `freeze_splits` -> `complete_phase_task` -> `plan_next` — across a
full split-fanned run, and asserts that the thing a dispatched phase skill asks
("am I a pipeline phase?") gets the right answer at EVERY frontier.

That composition is exactly what was broken: the state *writer* (v2, `phase_tasks[]`) and
the invocation-mode *reader* (v1, `current_step`) were never wired to each other, and no
test drove them together — so a driven run silently classified itself as standalone from
the second phase onward.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO / "shared" / "scripts" / "tools"))
sys.path.insert(0, str(_REPO / "shared" / "scripts" / "lib"))
sys.path.insert(0, str(_REPO / "plugins" / "shipwright-run" / "scripts" / "lib"))

import phase_task_lifecycle as ptl  # noqa: E402
from get_phase_context import build_phase_context  # noqa: E402
from orchestrator import create_config  # noqa: E402

SPLITS = ["01-core", "02-ui"]

# The full frontier a 2-split run walks, in order. Splits are driven SERIALLY
# (plan/01 -> build/01 -> plan/02 -> build/02), so `plan` and `build` each appear twice —
# same phase name, different task identity. That is the shape a scalar `current_step`
# cannot represent even in principle: it would read "plan" for both splits.
EXPECTED_FRONTIER = [
    ("project", None),
    ("design", None),
    ("plan", "01-core"),
    ("build", "01-core"),
    ("plan", "02-ui"),
    ("build", "02-ui"),
    ("test", None),
    ("changelog", None),
    ("deploy", None),
]


def _read_cfg(project_root: Path) -> dict:
    return json.loads((project_root / "shipwright_run_config.json").read_text("utf-8"))


def _v1_step_c_says_pipeline(cfg: dict, phase: str) -> bool:
    """The step-C predicate as the 7 phase skills used to spell it, verbatim.

    Kept here as an executable regression pin: if someone reintroduces it, this test
    shows it is wrong for every driven phase past the first.
    """
    return cfg.get("status") == "in_progress" and cfg.get("current_step") == phase


@pytest.fixture
def driven_run(tmp_path, monkeypatch):
    monkeypatch.delenv("AIKIDO_CLIENT_ID", raising=False)
    project = tmp_path / "proj"
    project.mkdir()
    create_config(
        scope="full_app", profile="supabase-nextjs", autonomy="guided",
        deploy_target="jelastic-dev", project_root=project,
    )
    # The design phase writes the splits that `freeze_splits` later promotes.
    (project / "shipwright_design_config.json").write_text(
        json.dumps({"splits": SPLITS}), encoding="utf-8",
    )
    return project


def _drive(project: Path):
    """Walk the whole pipeline exactly as the single-session master does.

    Yields (phase, split_id, phase_task_id, cfg_at_dispatch) once per dispatch, after the
    task is claimed (the master claims via `single-session-next` BEFORE it briefs the
    phase-runner) and before the result is applied.
    """
    while True:
        cfg = _read_cfg(project)
        task = next(
            (t for t in cfg["phase_tasks"] if t["status"] == "awaiting_launch"), None,
        )
        if task is None:
            return
        ptk, phase = task["phaseTaskId"], task["phase"]
        session_uuid, version = task["sessionUuid"], task["version"]

        claimed = ptl.claim_phase_task(
            project, phase_task_id=ptk, session_uuid=session_uuid, expected_phase=phase,
        )
        assert claimed["ok"], claimed

        yield phase, task["splitId"], ptk, _read_cfg(project)

        # `single-session-apply` freezes splits when the design phase completes, so the
        # build fans out per split. Mirror that ordering.
        if phase == "design":
            assert ptl.freeze_splits(project)["ok"]

        applied = ptl.complete_phase_task(
            project, phase_task_id=ptk, session_uuid=session_uuid,
            expected_version=version,
            result={"ok": True, "phase": phase, "summary": "ok", "artifacts": []},
        )
        assert applied["ok"], applied


def test_every_dispatched_phase_resolves_as_pipeline(driven_run):
    """The headline: a driven phase must know it is driven — at every frontier.

    Also pins the bug: the old v1 predicate returns "standalone" for every phase after
    `project` (which only passed by accident, `current_step` being stamped "project" at
    run creation and never advanced).
    """
    seen: list[tuple[str, str | None]] = []
    v1_verdicts: dict[str, bool] = {}

    for phase, split_id, ptk, cfg in _drive(driven_run):
        seen.append((phase, split_id))

        # The fix: the dispatch token the orchestrator handed us.
        out = build_phase_context(driven_run, ptk, phase=phase)
        assert out["mode"] == "pipeline", (
            f"{phase}/{split_id} was dispatched by the orchestrator but resolved "
            f"{out['mode']!r} ({out.get('reason')})"
        )
        assert out["phaseTaskId"] == ptk
        assert out["splitId"] == split_id

        v1_verdicts[f"{phase}/{split_id}"] = _v1_step_c_says_pipeline(cfg, phase)

    assert seen == EXPECTED_FRONTIER, seen

    # The regression pin: only the first phase ever passed the v1 check.
    assert v1_verdicts["project/None"] is True
    assert not any(
        passed for key, passed in v1_verdicts.items() if key != "project/None"
    ), f"v1 predicate unexpectedly passed somewhere: {v1_verdicts}"


def test_current_step_never_advances_and_cannot_identify_a_split_task(driven_run):
    """Root cause, pinned two ways.

    (1) Nothing in the v2 lifecycle advances `current_step` — it stays at its
        creation-time value for the entire run, while `completed_phase_task_ids` grows.
    (2) Even if it *were* advanced, it is phase-scoped and the frontier is
        split-scoped: the two `plan` tasks share a phase name but are different tasks.
        A scalar cannot address them, which is why the v1 fields were not simply revived.
    """
    plan_tokens: list[str] = []
    for phase, _split, ptk, cfg in _drive(driven_run):
        assert cfg["current_step"] == "project", (
            f"current_step moved to {cfg['current_step']!r} at {phase} — if the v2 "
            f"lifecycle now maintains it, revisit the invocation-mode design"
        )
        if phase == "plan":
            plan_tokens.append(ptk)

    final = _read_cfg(driven_run)
    assert final["current_step"] == "project"
    assert final["completed_steps"] == []
    assert len(final["completed_phase_task_ids"]) == len(EXPECTED_FRONTIER)
    assert final["status"] == "complete"

    # Two distinct plan tasks, one phase name.
    assert len(plan_tokens) == 2
    assert plan_tokens[0] != plan_tokens[1]


def test_out_of_band_invocation_during_a_live_run_warns(driven_run):
    """A human running `/shipwright-build` by hand mid-run gets no token — that is
    standalone, and it must raise the out-of-sequence warning rather than proceed
    silently."""
    for phase, _split, _ptk, _cfg in _drive(driven_run):
        if phase != "build":
            continue
        out = build_phase_context(driven_run, None)  # no token == hand-invoked
        assert out["mode"] == "standalone"
        assert out["pipeline_active"] is True
        assert out["active_phases"] == ["build"]
        assert out["requires_out_of_sequence_warning"] is True
        return
    pytest.fail("never reached the build phase")


def test_replayed_token_from_a_finished_phase_is_an_error_not_standalone(driven_run):
    """The back door this iterate closes: a token that no longer resolves must STOP the
    caller, never silently degrade to standalone (which is what stamps
    `mode: standalone` onto a driven run's artifacts)."""
    tokens: dict[str, str] = {}
    for phase, _split, ptk, _cfg in _drive(driven_run):
        tokens.setdefault(phase, ptk)

    # Every task is terminal now — replaying the project token must not re-enter pipeline.
    out = build_phase_context(driven_run, tokens["project"], phase="project")
    assert out["mode"] == "error"
    assert out["reason"] == "phase_task_not_actionable"

    # And a token belonging to another phase must not grant this phase authority.
    out = build_phase_context(driven_run, tokens["test"], phase="deploy")
    assert out["mode"] == "error"
    assert out["reason"] == "wrong_phase_for_phase_task"
