"""INTEGRATION: a full pipeline still runs to completion, with the engine deleted.

Failure-mode **(B)** of `iterate-2026-07-14-remove-multi-session`: *too much was removed*.
The dangerous half — it type-checks and lints perfectly clean; the pipeline just quietly
stops working. Siblings, together the `cross_component` coverage for this iterate:

  * `test_multi_session_removal_residue.py` — nothing dangling, nothing over-removed;
  * `test_removal_survivors_offpath.py` — the survivors the loop never touches
    (gate-policy inertness, the generic handoff).

Everything here drives the **real orchestrator CLI as a real subprocess** — the exact
surface the `/shipwright-run` master invokes — with the external per-phase-session engine
gone.

**Scope, stated honestly (external review, GPT).** This test PLAYS the phase-runner: it
writes the artifacts and hands back a RESULT CONTRACT, exactly as the subagent would. It
does NOT spawn a real `shipwright-run:phase-runner` subagent or execute the phase SKILLS —
those are LLM agents and cannot run inside pytest. So what it proves is the **orchestrator
half** of the pipeline: claim, freeze_splits, the persistence guard, complete, plan-next,
per-split fan-out, the tracked events, and the mode guard — i.e. everything the deleted
hooks used to touch. What it CANNOT catch is a regression *inside* a phase skill; that
surface is guarded instead by
`test_multi_session_removal_residue.py::test_no_shipped_skill_gates_on_the_deleted_context_block`.
The runner's own side of the contract is pinned by
`plugins/shipwright-run/tests/test_single_session_result_contract.py` and
`test_single_session_artifact_guard.py`.

What was genuinely at risk, and is proven here: `phase_task_lifecycle` (every mutator in
it was CALLED by the deleted Stop hook, and its docstring said "multi-session" — but it is
SHARED, and is the loop's only path); `sessionUuid` (which *sounds* like a Claude session
id, and was one, but is really the CAS claim token); and the tracked
`phase_started`/`phase_completed` pair (which had TWO producers, one inside the deleted hook).
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
ORCHESTRATOR = REPO_ROOT / "plugins" / "shipwright-run" / "scripts" / "lib" / "orchestrator.py"

CONFIG_NAME = "shipwright_run_config.json"
PIPELINE_PHASES = ("project", "design", "plan", "build", "test", "changelog", "deploy")


def _orch(project_root: Path, *args: str) -> subprocess.CompletedProcess:
    """Drive the REAL orchestrator CLI — the exact surface the master invokes."""
    return subprocess.run(
        [sys.executable, str(ORCHESTRATOR), *args, "--project-root", str(project_root)],
        capture_output=True, text=True, timeout=90,
    )


def _cfg(project_root: Path) -> dict:
    return json.loads((project_root / CONFIG_NAME).read_text(encoding="utf-8"))


def _events(project_root: Path) -> list[dict]:
    path = project_root / "shipwright_events.jsonl"
    if not path.exists():
        return []
    return [json.loads(ln) for ln in path.read_text("utf-8").splitlines() if ln.strip()]


SPLITS = ("01-core", "02-ui")


def _run_phase(project_root: Path, dispatch: dict) -> subprocess.CompletedProcess:
    """Play the phase-runner subagent: persist the artifact to DISK, then apply the
    RESULT CONTRACT. The on-disk persistence guard rejects a claimed-but-unwritten
    artifact, so this has to be a real file.

    The design phase also writes ``shipwright_design_config.json`` carrying SPLITS —
    that is what `freeze_splits` reads, so plan/build genuinely FAN OUT per split. Without
    it the whole pipeline would run split-less and the per-split event assertions below
    would be vacuous.
    """
    split = dispatch["splitId"]
    artifact_rel = f"artifacts/{dispatch['phase']}{'-' + split if split else ''}.md"
    artifact = project_root / artifact_rel
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text(f"# {dispatch['phase']}\n", encoding="utf-8")

    if dispatch["phase"] == "design":
        (project_root / "shipwright_design_config.json").write_text(
            json.dumps({"status": "complete", "splits": list(SPLITS)}), encoding="utf-8",
        )

    result = {
        "ok": True,
        "phase": dispatch["phase"],
        "summary": f"{dispatch['phase']} done",
        "artifacts": [artifact_rel],
    }
    if split:
        result["splitId"] = split
    result_path = project_root / "result.json"
    result_path.write_text(json.dumps(result), encoding="utf-8")

    return _orch(
        project_root, "single-session-apply",
        "--phase-task-id", dispatch["phaseTaskId"],
        "--session-uuid", dispatch["sessionUuid"],
        "--version", str(dispatch["version"]),
        "--result-json", str(result_path),
    )


def _drive_to_completion(project_root: Path) -> list[tuple[str, str | None]]:
    """Run the whole loop; return the (phase, splitId) pairs actually dispatched."""
    seen: list[tuple[str, str | None]] = []
    for _ in range(40):  # generous bound; 7 phases + 2 splits finish well inside it
        payload = json.loads(_orch(project_root, "single-session-next").stdout)
        if payload["action"] == "complete":
            return seen
        assert payload["action"] == "dispatch", f"unexpected loop action: {payload}"
        dispatch = payload["dispatch"]
        seen.append((dispatch["phase"], dispatch["splitId"]))
        applied = _run_phase(project_root, dispatch)
        assert applied.returncode == 0, (
            f"apply failed for {dispatch['phase']}: {applied.stdout}{applied.stderr}"
        )
    pytest.fail(f"pipeline never terminated; dispatched: {seen}")


@pytest.fixture()
def fresh_run(tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    res = _orch(project, "write-config", "--scope", "full_app", "--profile", "supabase-nextjs")
    assert res.returncode == 0, res.stderr
    return project


# --------------------------------------------------------------------------- #
# The survivor contract: a full 7-phase pipeline, engine deleted
# --------------------------------------------------------------------------- #

def test_fresh_run_is_single_session(fresh_run):
    assert _cfg(fresh_run)["mode"] == "single_session"


def test_full_pipeline_runs_to_complete_without_the_engine(fresh_run):
    """THE proof that nothing needed was cut.

    Drives all 7 phases (plan/build fanning out over 2 splits) through the real
    `single-session-next` / `single-session-apply` loop, and asserts the run reaches
    `status: complete`. Every lifecycle mutator the deleted Stop hook used to call is
    exercised here — claim, freeze_splits (at design), complete, plan_next_phase — with
    that hook absent.
    """
    seen = _drive_to_completion(fresh_run)

    cfg = _cfg(fresh_run)
    assert cfg["status"] == "complete", f"run did not complete: {cfg['status']}"
    # The state machine still plans every successor — without the Stop hook that used to
    # trigger plan_next_phase.
    phases = [p for p, _ in seen]
    for phase in PIPELINE_PHASES:
        assert phase in phases, f"phase {phase!r} never dispatched (seen: {seen})"
    # freeze_splits still ran at design, so plan/build genuinely FANNED OUT per split.
    assert set(cfg["splits_frozen"]) == set(SPLITS), f"splits not frozen: {cfg['splits_frozen']}"
    for phase in ("plan", "build"):
        got = sorted(s for p, s in seen if p == phase)
        assert got == sorted(SPLITS), f"{phase} did not fan out per split: {got}"
    assert all(t["status"] in ("done", "skipped") for t in cfg["phase_tasks"])


def test_session_uuid_is_still_the_claim_token(fresh_run):
    """`sessionUuid` survives as the CAS claim token. If it had been cut as a
    'multi-session' field, the claim below could not happen."""
    dispatch = json.loads(_orch(fresh_run, "single-session-next").stdout)["dispatch"]
    assert dispatch["sessionUuid"], "dispatch carries no claim token"

    task = _cfg(fresh_run)["phase_tasks"][0]
    assert task["status"] == "in_progress", "next-dispatch did not claim the task"
    assert task["claimedBySessionUuid"] == task["sessionUuid"] == dispatch["sessionUuid"], (
        "the task was not claimed by its own sessionUuid — the CAS claim token broke"
    )


def test_loop_emits_one_tracked_start_end_pair_per_split(fresh_run):
    """`phase_started` had TWO producers; one lived inside the deleted hook. The loop is
    now the SOLE producer, and it must still emit a complete start+end pair **per
    (phase, splitId)** into the TRACKED shipwright_events.jsonl.

    Driven through the REAL loop, on a pipeline that actually fans out — asserting this
    only against `record_event` directly (or only against a split-less phase) would let a
    regression where `single-session-next`/`-apply` stop propagating `splitId` pass
    unnoticed, and per-phase durations would silently under-count.
    """
    dispatched = _drive_to_completion(fresh_run)
    events = _events(fresh_run)

    for phase, split in dispatched:
        starts = [e for e in events
                  if e.get("type") == "phase_started"
                  and e.get("phase") == phase and e.get("splitId") == split]
        ends = [e for e in events
                if e.get("type") == "phase_completed"
                and e.get("phase") == phase and e.get("splitId") == split]
        assert len(starts) == 1, f"({phase}, {split}): expected 1 phase_started, got {len(starts)}"
        assert len(ends) == 1, f"({phase}, {split}): expected 1 phase_completed, got {len(ends)}"

    # Both build splits kept their OWN end — the per-split dedup regression
    # (iterate-2026-07-11) is still fixed through the surviving emitter.
    build_ends = [e for e in events
                  if e.get("type") == "phase_completed" and e.get("phase") == "build"]
    assert {e["splitId"] for e in build_ends} == set(SPLITS)


# --------------------------------------------------------------------------- #
# A stale config fails CLOSED — and leaves the run untouched
# --------------------------------------------------------------------------- #

def test_stale_multi_session_config_is_refused_with_no_side_effects(fresh_run):
    """Migrating must be a one-line edit, not a cleanup job: the refusal happens BEFORE
    any claim, mutation, event append, or loop-pointer write."""
    cfg = _cfg(fresh_run)
    cfg["mode"] = "multi_session"
    (fresh_run / CONFIG_NAME).write_text(json.dumps(cfg, indent=2), encoding="utf-8")

    res = _orch(fresh_run, "single-session-next")
    assert res.returncode == 1
    payload = json.loads(res.stdout)
    assert payload["action"] == "mode_unsupported"
    assert '"mode": "single_session"' in payload["message"], "no actionable fix in the message"

    after = _cfg(fresh_run)
    assert after["phase_tasks"][0]["status"] == "awaiting_launch"
    assert after["phase_tasks"][0]["claimedBySessionUuid"] is None
    assert not (fresh_run / ".shipwright" / "run_loop_state.json").exists()
    assert _events(fresh_run) == []


def test_write_config_refuses_the_removed_mode(tmp_path):
    """The parser intercepts it (exit 2), and says WHAT TO DO — not `invalid choice`."""
    project = tmp_path / "proj"
    project.mkdir()
    res = _orch(project, "write-config", "--scope", "full_app", "--mode", "multi_session")
    assert res.returncode != 0
    assert "invalid choice" not in res.stderr, "generic argparse error, no migration path"
    assert '"mode": "single_session"' in res.stderr, "no actionable fix in the message"
    assert not (project / CONFIG_NAME).exists(), "a refused mode must not leave a config"


def test_help_does_not_advertise_the_removed_mode(tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    res = _orch(project, "write-config", "--help")
    assert "multi_session" not in res.stdout, "--help still offers the removed mode"
    assert "single_session" in res.stdout
