"""Integration tests: Phase-Session Hook Chain (Plan v4 §Lifecycle).

Drives the three shared phase-session hooks in sequence on a real on-disk
config to verify they integrate correctly:

    SessionStart  → phase_session_start.py
    UserPromptSubmit → phase_user_prompt_validate.py
    Stop          → phase_session_stop.py

Each hook is unit-tested individually under shared/tests/test_phase_session_hooks.py
with mocked payloads and isolated assertions. This file's value is the
*chain*: do the file-system markers (sessionstart-validation.json,
.block-pending) flow correctly between hooks, and do the resulting
phase_tasks[] transitions match Plan v4 §State Machine when we walk a
realistic 7-phase pipeline?

Coverage:
    1. Happy-path 7-phase walk via hook chain (SessionStart -> UserPromptSubmit
       -> Stop, repeated for each phase, no faking the orchestrator subcommands).
    2. Wrong-skill block: SessionStart for project task launched under build
       plugin must write the .block-pending sentinel, and UserPromptSubmit must
       emit decision:"block" + exit 2 + then delete the marker (single-use).
    3. Standalone fallthrough: with no run_config or with a sessionUuid that
       doesn't match any phase_task, all three hooks must no-op silently.
"""
from __future__ import annotations

import contextlib
import io
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
RUN_LIB = REPO_ROOT / "plugins" / "shipwright-run" / "scripts" / "lib"
SHARED_HOOKS = REPO_ROOT / "shared" / "scripts" / "hooks"

if str(RUN_LIB) not in sys.path:
    sys.path.insert(0, str(RUN_LIB))
if str(SHARED_HOOKS) not in sys.path:
    sys.path.insert(0, str(SHARED_HOOKS))

# Hook entry points — pure functions so we can drive them without subprocess.
import phase_session_start as hook_start  # noqa: E402
import phase_user_prompt_validate as hook_prompt  # noqa: E402
import phase_session_stop as hook_stop  # noqa: E402

from orchestrator import create_config  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _plugin_root_for(phase: str) -> Path:
    """Map phase -> the on-disk plugin directory (e.g. plugins/shipwright-build/)."""
    return REPO_ROOT / "plugins" / f"shipwright-{phase}"


def _read_config(project_root: Path) -> dict:
    return json.loads(
        (project_root / "shipwright_run_config.json").read_text("utf-8"),
    )


def _next_awaiting(config: dict) -> dict | None:
    for t in config.get("phase_tasks", []):
        if t.get("status") == "awaiting_launch":
            return t
    return None


def _capture_stdout(fn, *args, **kwargs) -> tuple[int, str]:
    """Run `fn(*args)` capturing stdout. Returns (exit_code, stdout)."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = fn(*args, **kwargs)
    return rc, buf.getvalue()


def _write_phase_result_config(project_root: Path, phase: str, ok: bool = True) -> None:
    """Write the phase-specific config that phase_session_stop.py reads to
    derive result.ok. Different phases use different file names; security
    and changelog have no canonical config so this is a no-op for them."""
    name_map = hook_stop.PHASE_CONFIG_NAME
    cfg_name = name_map.get(phase)
    if cfg_name is None:
        return  # security / changelog
    payload = {"phase": phase, "ok": ok}
    if not ok:
        payload["reason"] = "test-injected-failure"
    (project_root / cfg_name).write_text(
        json.dumps(payload, indent=2), encoding="utf-8",
    )


def _walk_phase_via_hooks(
    project_root: Path, expected_phase: str, *, ok: bool = True,
) -> dict:
    """Drive SessionStart -> UserPromptSubmit -> Stop hooks for one phase.

    Returns the post-Stop config dict for caller assertions.
    Asserts: SessionStart emits non-empty PIPELINE-CONTEXT with the right
    phaseTaskId; UserPromptSubmit passes through (no marker on happy path);
    Stop completes the task and (for non-terminal phases) materialises the
    next phase_tasks[] entry.
    """
    cfg = _read_config(project_root)
    task = _next_awaiting(cfg)
    assert task is not None, f"no awaiting_launch task; tasks={cfg['phase_tasks']}"
    assert task["phase"] == expected_phase, \
        f"expected phase={expected_phase}, got {task['phase']}"

    plugin_root = _plugin_root_for(expected_phase)
    session_uuid = task["sessionUuid"]
    phase_task_id = task["phaseTaskId"]
    run_id = cfg["runId"]

    # 1) SessionStart hook
    rc, stdout = _capture_stdout(
        hook_start.run, project_root, session_uuid, str(plugin_root),
    )
    assert rc == 0, "SessionStart hook should always exit 0"
    assert "SHIPWRIGHT-PIPELINE-CONTEXT" in stdout, \
        f"expected PIPELINE-CONTEXT in stdout, got: {stdout!r}"
    assert phase_task_id in stdout, \
        f"expected phaseTaskId {phase_task_id!r} in stdout, got: {stdout!r}"

    # Validation marker should be valid=true (happy path)
    val_path = (
        project_root / ".shipwright" / "runs" / run_id / phase_task_id
        / "sessionstart-validation.json"
    )
    assert val_path.exists(), f"validation marker missing at {val_path}"
    val = json.loads(val_path.read_text("utf-8"))
    assert val["valid"] is True, f"expected valid=True, got: {val}"

    # No .block-pending sentinel on happy path
    block_path = val_path.parent / ".block-pending"
    assert not block_path.exists(), ".block-pending should not exist on happy path"

    # CAS-claim happened
    cfg = _read_config(project_root)
    claimed = next(t for t in cfg["phase_tasks"] if t["phaseTaskId"] == phase_task_id)
    assert claimed["status"] == "in_progress"
    assert claimed["claimedBySessionUuid"] == session_uuid

    # 2) UserPromptSubmit hook (happy path: no marker → no-op pass-through)
    rc, stdout = _capture_stdout(hook_prompt.run, project_root, session_uuid)
    assert rc == 0, f"UserPromptSubmit on happy path should exit 0, got {rc}"
    assert stdout.strip() == "", \
        f"UserPromptSubmit should be silent on happy path, got: {stdout!r}"

    # 3) Skill writes its phase config (simulated)
    _write_phase_result_config(project_root, expected_phase, ok=ok)

    # 4) Stop hook
    rc, _ = _capture_stdout(hook_stop.run, project_root, session_uuid)
    assert rc == 0, "Stop hook should always exit 0"

    cfg = _read_config(project_root)
    final_task = next(t for t in cfg["phase_tasks"] if t["phaseTaskId"] == phase_task_id)
    expected_status = "done" if ok else "failed"
    assert final_task["status"] == expected_status, \
        f"expected status={expected_status}, got: {final_task}"
    return cfg


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def fresh_project(tmp_path, monkeypatch):
    """Empty project root with an initialized v2 run_config."""
    project = tmp_path / "hook-chain-project"
    project.mkdir()
    monkeypatch.delenv("AIKIDO_CLIENT_ID", raising=False)
    create_config(
        scope="full_app", profile="supabase-nextjs",
        autonomy="guided", deploy_target="jelastic-dev",
        project_root=project,
    )
    return project


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestHappyPathHookChain:
    """Walk the whole pipeline through SessionStart/UserPromptSubmit/Stop chain."""

    def test_seven_phase_pipeline_via_hooks(self, fresh_project):
        # Walk all 7 phases. Each call asserts SessionStart emitted PIPELINE-CONTEXT,
        # UserPromptSubmit passed through silently, Stop completed the task and
        # materialised the next phase task.
        for phase in (
            "project", "design", "plan", "build",
            "test", "changelog", "deploy",
        ):
            _walk_phase_via_hooks(fresh_project, expected_phase=phase, ok=True)

        final = _read_config(fresh_project)
        assert final["status"] == "complete", \
            f"expected complete, got {final['status']}; " \
            f"tasks={[(t['phase'], t['status']) for t in final['phase_tasks']]}"
        for t in final["phase_tasks"]:
            assert t["status"] in ("done", "skipped")


class TestWrongSkillBlockChain:
    """Wrong-skill launch: SessionStart writes .block-pending,
    UserPromptSubmit emits decision:block + exit 2 and consumes the marker."""

    def test_wrong_skill_blocks_first_prompt_only(self, fresh_project):
        cfg = _read_config(fresh_project)
        project_task = cfg["phase_tasks"][0]
        assert project_task["phase"] == "project"

        session_uuid = project_task["sessionUuid"]
        phase_task_id = project_task["phaseTaskId"]
        run_id = cfg["runId"]

        # 1) SessionStart with WRONG plugin (build instead of project)
        wrong_plugin = _plugin_root_for("build")
        rc, stdout = _capture_stdout(
            hook_start.run, fresh_project, session_uuid, str(wrong_plugin),
        )
        assert rc == 0  # SessionStart never blocks
        assert "BLOCKED" in stdout, f"expected BLOCKED context, got: {stdout!r}"

        # Validation marker reflects block
        val_path = (
            fresh_project / ".shipwright" / "runs" / run_id / phase_task_id
            / "sessionstart-validation.json"
        )
        val = json.loads(val_path.read_text("utf-8"))
        assert val["valid"] is False
        assert val["reason"] == "wrong_skill"

        # .block-pending sentinel was written
        block_path = val_path.parent / ".block-pending"
        assert block_path.exists(), ".block-pending sentinel must be written"

        # Phase task NOT claimed (still awaiting_launch, no claimedBy)
        cfg = _read_config(fresh_project)
        task = cfg["phase_tasks"][0]
        assert task["status"] == "awaiting_launch"
        assert task["claimedBySessionUuid"] is None

        # 2) UserPromptSubmit hook fires — must emit decision:block + exit 2
        rc, stdout = _capture_stdout(hook_prompt.run, fresh_project, session_uuid)
        assert rc == 2, f"expected exit 2 for block, got {rc}"
        payload = json.loads(stdout)
        assert payload["decision"] == "block"
        assert "PIPELINE-BLOCK" in payload["hookSpecificOutput"]["additionalContext"]

        # Marker consumed (single-use)
        assert not block_path.exists(), \
            ".block-pending should be deleted after first read"

        # 3) UserPromptSubmit fires AGAIN (e.g. user submits another prompt) —
        #    should pass through silently.
        rc, stdout = _capture_stdout(hook_prompt.run, fresh_project, session_uuid)
        assert rc == 0
        assert stdout.strip() == "", \
            f"second UserPromptSubmit should pass through, got: {stdout!r}"


class TestStandaloneFallthrough:
    """No run_config or unmatched sessionUuid → all hooks no-op."""

    def test_no_run_config(self, tmp_path):
        # Empty project, no config at all — all hooks should be silent no-ops.
        project = tmp_path / "no-config"
        project.mkdir()

        rc, stdout = _capture_stdout(
            hook_start.run, project, "any-uuid", str(_plugin_root_for("build")),
        )
        assert rc == 0 and stdout == ""

        rc, stdout = _capture_stdout(hook_prompt.run, project, "any-uuid")
        assert rc == 0 and stdout == ""

        rc, _ = _capture_stdout(hook_stop.run, project, "any-uuid")
        assert rc == 0

    def test_unmatched_session_uuid(self, fresh_project):
        # Config exists but sessionUuid doesn't match any phase_task.
        bogus_uuid = "00000000-0000-0000-0000-000000000000"

        rc, stdout = _capture_stdout(
            hook_start.run, fresh_project, bogus_uuid, str(_plugin_root_for("project")),
        )
        assert rc == 0 and stdout == ""

        rc, stdout = _capture_stdout(hook_prompt.run, fresh_project, bogus_uuid)
        assert rc == 0 and stdout == ""

        rc, _ = _capture_stdout(hook_stop.run, fresh_project, bogus_uuid)
        assert rc == 0

        # Phase task is unchanged
        cfg = _read_config(fresh_project)
        assert cfg["phase_tasks"][0]["status"] == "awaiting_launch"
        assert cfg["phase_tasks"][0]["claimedBySessionUuid"] is None


class TestStaleStopAfterRecover:
    """If a session is recovered, the original session's Stop hook hits
    a stale-version owner check inside complete-phase-task and must exit 0
    cleanly with no state mutation."""

    def test_stop_after_recover_is_clean_noop(self, fresh_project):
        cfg = _read_config(fresh_project)
        task = cfg["phase_tasks"][0]
        session_uuid = task["sessionUuid"]
        phase_task_id = task["phaseTaskId"]

        # Original SessionStart claims the task
        rc, _ = _capture_stdout(
            hook_start.run, fresh_project, session_uuid,
            str(_plugin_root_for("project")),
        )
        assert rc == 0
        assert _read_config(fresh_project)["phase_tasks"][0]["status"] == "in_progress"

        # User runs recover-phase-task (simulated via direct lifecycle call)
        from phase_task_lifecycle import recover_phase_task
        recovery = recover_phase_task(
            fresh_project, phase_task_id=phase_task_id,
            force_status="awaiting_launch",
        )
        assert recovery["ok"] is True
        recovered_version = recovery["phase_task"]["version"]
        original_version = task["version"]
        assert recovered_version > original_version

        # Original session's Stop hook fires later — sessionstart-validation.json
        # still has the OLD version. complete-phase-task should reject as stale.
        # We simulate a result config (project completed normally before the crash)
        _write_phase_result_config(fresh_project, "project", ok=True)

        rc, _ = _capture_stdout(hook_stop.run, fresh_project, session_uuid)
        assert rc == 0, "Stop hook must exit 0 even when ownership is stale"

        # Phase task is back to awaiting_launch (recovered state preserved)
        post = _read_config(fresh_project)["phase_tasks"][0]
        assert post["status"] == "awaiting_launch"
        # No design successor was planned (Stop did not run complete-phase-task path)
        post_cfg = _read_config(fresh_project)
        assert all(t["phase"] != "design" for t in post_cfg["phase_tasks"])
