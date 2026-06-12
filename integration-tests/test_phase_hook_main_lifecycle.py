"""Integration coverage: phase-hook ``main()`` end-to-end via the stdin payload.

**Why this file exists (deep-audit F1).** Every other phase-hook test calls the
pure ``run(project_root, session_uuid, …)`` function directly, bypassing
``main()`` — exactly where the F1 bug lived: ``main()`` read project root +
session id from process env vars that no launcher sets, so the whole v2
claim/validate/complete lifecycle silently no-op'd. These tests drive each hook's
**real ``main()``** with a realistic Claude Code stdin payload and **no env vars**,
proving the components compose:

    stdin payload  →  lib.hook_session.resolve_hook_context  →  hook run()
                   →  phase_task_lifecycle (claim/complete)   →  record_event

This is the ``cross_component`` risk-flag's INTEGRATION coverage behavior
(Confidence-Calibration §Integration Stopping Rule); the F11 verifier
``check_integration_coverage`` requires it because the diff touches hooks +
the event-log writer.
"""
from __future__ import annotations

import concurrent.futures
import io
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
RUN_LIB = REPO_ROOT / "plugins" / "shipwright-run" / "scripts" / "lib"
SHARED_HOOKS = REPO_ROOT / "shared" / "scripts" / "hooks"
SHARED_TOOLS = REPO_ROOT / "shared" / "scripts" / "tools"
for _p in (RUN_LIB, SHARED_HOOKS, SHARED_TOOLS):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import phase_session_start as hook_start  # noqa: E402
import phase_session_stop as hook_stop  # noqa: E402
import phase_user_prompt_validate as hook_prompt  # noqa: E402
import record_event  # noqa: E402

from orchestrator import create_config  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures + helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def fresh_project(tmp_path, monkeypatch):
    """v2 run_config project + a clean env (no SHIPWRIGHT_* identity vars).

    The cleared env is the heart of the test: the launcher never sets these, so
    the hooks must work from the stdin payload alone.
    """
    monkeypatch.delenv("AIKIDO_CLIENT_ID", raising=False)
    monkeypatch.delenv("SHIPWRIGHT_PROJECT_ROOT", raising=False)
    monkeypatch.delenv("SHIPWRIGHT_SESSION_ID", raising=False)
    project = tmp_path / "proj"
    project.mkdir()
    create_config(
        scope="full_app", profile="supabase-nextjs",
        autonomy="guided", deploy_target="jelastic-dev",
        project_root=project,
    )
    return project


def _read_cfg(project_root: Path) -> dict:
    return json.loads((project_root / "shipwright_run_config.json").read_text("utf-8"))


def _project_task(project_root: Path) -> dict:
    return _read_cfg(project_root)["phase_tasks"][0]


def _plugin_root_for(phase: str) -> str:
    return str(REPO_ROOT / "plugins" / f"shipwright-{phase}")


def _drive_main(monkeypatch, capsys, hook_module, payload: dict,
                *, plugin_root: str | None = None) -> tuple[int, str]:
    """Drive ``hook_module.main()`` with ``payload`` on stdin and no identity env."""
    monkeypatch.delenv("SHIPWRIGHT_PROJECT_ROOT", raising=False)
    monkeypatch.delenv("SHIPWRIGHT_SESSION_ID", raising=False)
    if plugin_root is not None:
        monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", plugin_root)
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
    capsys.readouterr()  # drop anything buffered
    rc = hook_module.main()
    return rc, capsys.readouterr().out


def _payload(project_root: Path, session_uuid: str, event_name: str) -> dict:
    return {"session_id": session_uuid, "cwd": str(project_root),
            "hook_event_name": event_name}


# ---------------------------------------------------------------------------
# F1 — main() engages the lifecycle from the stdin payload, no env vars
# ---------------------------------------------------------------------------

def test_start_main_claims_from_payload_without_env(fresh_project, monkeypatch, capsys):
    task = _project_task(fresh_project)
    rc, out = _drive_main(
        monkeypatch, capsys, hook_start,
        _payload(fresh_project, task["sessionUuid"], "SessionStart"),
        plugin_root=_plugin_root_for("project"),
    )
    assert rc == 0
    # The whole point of F1: with NO env vars, the lifecycle now ENGAGES.
    assert "SHIPWRIGHT-PIPELINE-CONTEXT" in out
    assert task["phaseTaskId"] in out
    cfg = _read_cfg(fresh_project)
    assert cfg["phase_tasks"][0]["status"] == "in_progress"
    assert cfg["phase_tasks"][0]["claimedBySessionUuid"] == task["sessionUuid"]


def test_validate_main_blocks_wrong_skill_from_payload(fresh_project, monkeypatch, capsys):
    task = _project_task(fresh_project)
    # SessionStart under the WRONG plugin writes the .block-pending sentinel.
    _drive_main(monkeypatch, capsys, hook_start,
                _payload(fresh_project, task["sessionUuid"], "SessionStart"),
                plugin_root=_plugin_root_for("build"))
    # UserPromptSubmit main() must consume the marker and block — from payload alone.
    rc, out = _drive_main(monkeypatch, capsys, hook_prompt,
                          _payload(fresh_project, task["sessionUuid"], "UserPromptSubmit"))
    assert rc == 2
    assert json.loads(out)["decision"] == "block"


def test_standalone_when_payload_cwd_not_a_project(tmp_path, monkeypatch, capsys):
    # cwd in the payload is NOT a Shipwright project AND cwd has no project →
    # main() degrades to standalone (exit 0, silent), never crashes.
    empty = tmp_path / "empty"
    empty.mkdir()
    monkeypatch.chdir(empty)
    rc, out = _drive_main(monkeypatch, capsys, hook_start,
                          _payload(empty, "any-uuid", "SessionStart"),
                          plugin_root=_plugin_root_for("project"))
    assert rc == 0 and out == ""


# ---------------------------------------------------------------------------
# Composition: start.main() → stop.main() → record_event (F1 + F15)
# ---------------------------------------------------------------------------

def test_full_chain_via_main_records_completion_event(fresh_project, monkeypatch, capsys):
    """INTEGRATION: drive start+stop main() from payloads; the phase_completed
    event must reach events.jsonl via the record_event subprocess the Stop hook
    spawns — proving the hook stdin-resolution, the lifecycle, and the event
    writer compose end to end."""
    task = _project_task(fresh_project)
    sid = task["sessionUuid"]
    _drive_main(monkeypatch, capsys, hook_start,
                _payload(fresh_project, sid, "SessionStart"),
                plugin_root=_plugin_root_for("project"))
    # Phase produced its config → collect_result returns ok.
    (fresh_project / "shipwright_project_config.json").write_text(
        json.dumps({"status": "complete"}), encoding="utf-8")
    rc, _ = _drive_main(monkeypatch, capsys, hook_stop,
                        _payload(fresh_project, sid, "Stop"))
    assert rc == 0
    assert _read_cfg(fresh_project)["phase_tasks"][0]["status"] == "done"
    events = record_event.read_events(fresh_project)
    completed = [e for e in events if e.get("type") == "phase_completed"
                 and e.get("phase") == "project"]
    assert len(completed) == 1, f"expected one phase_completed, got {events!r}"


def test_stop_main_records_phase_failed_event(fresh_project, monkeypatch, capsys):
    """F15 end-to-end: a failed phase emits ``phase_failed`` — previously argparse
    rejected the type (exit 2) and the failure was silently dropped."""
    task = _project_task(fresh_project)
    sid = task["sessionUuid"]
    _drive_main(monkeypatch, capsys, hook_start,
                _payload(fresh_project, sid, "SessionStart"),
                plugin_root=_plugin_root_for("project"))
    # NO project config → collect_result ok=false → mark_phase_failed.
    rc, _ = _drive_main(monkeypatch, capsys, hook_stop,
                        _payload(fresh_project, sid, "Stop"))
    assert rc == 0
    cfg = _read_cfg(fresh_project)
    assert cfg["phase_tasks"][0]["status"] == "failed"
    failed = [e for e in record_event.read_events(fresh_project)
              if e.get("type") == "phase_failed"]
    assert len(failed) == 1 and failed[0]["phase"] == "project"


# ---------------------------------------------------------------------------
# F14 — no duplicate phase_completed under genuinely concurrent appends
# ---------------------------------------------------------------------------

def test_concurrent_phase_completed_records_no_duplicate(tmp_path):
    """AC2: N concurrent ``record_event`` processes recording phase_completed for
    one phase yield exactly ONE event (the in-lock dedup scan holds the line)."""
    record_script = SHARED_TOOLS / "record_event.py"

    def _record(_i: int) -> int:
        return subprocess.run(
            [sys.executable, str(record_script),
             "--project-root", str(tmp_path),
             "--type", "phase_completed", "--phase", "build"],
            capture_output=True, text=True, encoding="utf-8", timeout=60,
        ).returncode

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        codes = list(ex.map(_record, range(8)))

    assert all(c == 0 for c in codes), f"a record_event process failed: {codes}"
    events = record_event.read_events(tmp_path)
    completed = [e for e in events if e.get("type") == "phase_completed"
                 and e.get("phase") == "build"]
    assert len(completed) == 1, f"expected exactly 1 phase_completed, got {len(completed)}"
