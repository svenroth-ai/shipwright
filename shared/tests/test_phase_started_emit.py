"""phase_started emit at the SessionStart hook (B1 / M-Pre-1).

The multi_session SessionStart hook is the durable phase-ENTRY emit site — the
exact mirror of ``phase_session_stop``'s ``phase_completed``. Concept §5a: the
``phase_started`` event TYPE existed but nothing emitted it, so the WebUI
PhaseRail had only END timestamps. These tests pin: one phase_started per
happy-path claim, no double-emit on idempotent re-entry, none on a blocked
claim, and pairing with the existing phase_completed end event (AC2).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT / "plugins" / "shipwright-run" / "scripts" / "lib"))
sys.path.insert(0, str(_REPO_ROOT / "shared" / "scripts" / "hooks"))
sys.path.insert(0, str(_REPO_ROOT / "shared" / "scripts"))

from orchestrator import create_config  # noqa: E402

from lib.phase_event_emit import emit_phase_event  # noqa: E402

import phase_session_start  # noqa: E402
import phase_session_stop  # noqa: E402


@pytest.fixture
def v2_project(tmp_path, monkeypatch):
    monkeypatch.delenv("AIKIDO_CLIENT_ID", raising=False)
    project = tmp_path / "proj"
    project.mkdir()
    # multi_session: the mode whose SessionStart hook emits phase_started
    # (single_session emits at the CLI instead — FIX 3 keeps the two exclusive).
    create_config(
        scope="full_app", profile="supabase-nextjs",
        autonomy="guided", deploy_target="jelastic-dev",
        project_root=project, mode="multi_session",
    )
    return project


def _read_cfg(project_root: Path) -> dict:
    return json.loads((project_root / "shipwright_run_config.json").read_text("utf-8"))


def _project_task(project_root: Path) -> dict:
    return _read_cfg(project_root)["phase_tasks"][0]


def _events_of_type(project_root: Path, event_type: str) -> list[dict]:
    path = project_root / "shipwright_events.jsonl"
    if not path.exists():
        return []
    events = [json.loads(ln) for ln in path.read_text("utf-8").splitlines() if ln.strip()]
    return [e for e in events if e.get("type") == event_type]


def test_start_happy_path_emits_phase_started(v2_project):
    task = _project_task(v2_project)
    phase_session_start.run(
        v2_project, session_uuid=task["sessionUuid"],
        plugin_root="shipwright-project",
    )
    started = _events_of_type(v2_project, "phase_started")
    assert len(started) == 1
    ev = started[0]
    assert ev["type"] == "phase_started"
    assert ev.get("ts")  # every event carries an ISO timestamp
    assert ev["phase"] == "project"
    detail = json.loads(ev["detail"])
    assert detail["phaseTaskId"] == task["phaseTaskId"]
    assert detail["splitId"] is None  # project is not a split phase
    assert detail["runId"] == _read_cfg(v2_project)["runId"]


def test_start_idempotent_reentry_emits_single_phase_started(v2_project):
    """A re-entrant SessionStart (reconnect) must NOT double-emit."""
    task = _project_task(v2_project)
    phase_session_start.run(
        v2_project, session_uuid=task["sessionUuid"],
        plugin_root="shipwright-project",
    )
    phase_session_start.run(  # idempotent re-claim by the same session
        v2_project, session_uuid=task["sessionUuid"],
        plugin_root="shipwright-project",
    )
    assert len(_events_of_type(v2_project, "phase_started")) == 1


def test_start_block_path_emits_no_phase_started(v2_project):
    """A blocked SessionStart (wrong skill) never claims, so never emits."""
    task = _project_task(v2_project)
    phase_session_start.run(
        v2_project, session_uuid=task["sessionUuid"],
        plugin_root="shipwright-build",  # task.phase is project -> wrong_skill
    )
    assert _events_of_type(v2_project, "phase_started") == []


def test_emit_phase_event_never_raises_on_subprocess_failure(monkeypatch, tmp_path):
    """The emit is best-effort: a spawn failure must be swallowed, never
    propagate to the unwrapped SessionStart-hook caller (FIX 2)."""
    import subprocess

    def boom(*_a, **_k):
        raise OSError("cannot spawn")

    monkeypatch.setattr(subprocess, "run", boom)
    emit_phase_event(tmp_path, "phase_started", "build", {"runId": "r"})  # no raise


def test_emit_phase_event_decodes_child_output_with_replace(monkeypatch, tmp_path):
    """Child output is decoded utf-8/replace so a cp1252 byte can't raise
    UnicodeDecodeError (uncaught by the except) — the Windows landmine (FIX 2)."""
    import subprocess

    captured: dict = {}

    class _Proc:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_run(_args, **kwargs):
        captured.update(kwargs)
        return _Proc()

    monkeypatch.setattr(subprocess, "run", fake_run)
    emit_phase_event(tmp_path, "phase_started", "build", {"runId": "r"})
    assert captured.get("encoding") == "utf-8"
    assert captured.get("errors") == "replace"


def test_emit_phase_event_forwards_split_id_from_detail(monkeypatch, tmp_path):
    """AC3 — the emit wrapper promotes detail.splitId to a top-level --split-id
    arg so record_event can dedup phase_completed by (phase, splitId)."""
    import subprocess

    captured: dict = {}

    class _Proc:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_run(args, **_kwargs):
        captured["args"] = args
        return _Proc()

    monkeypatch.setattr(subprocess, "run", fake_run)
    emit_phase_event(tmp_path, "phase_completed", "build",
                     {"phaseTaskId": "ptk-x", "splitId": "02-ui", "runId": "r"})
    args = captured["args"]
    assert "--split-id" in args
    assert args[args.index("--split-id") + 1] == "02-ui"


def test_emit_phase_event_no_split_id_when_detail_split_none(monkeypatch, tmp_path):
    """A single-split (splitId=None) phase must NOT pass --split-id — it dedups by
    (phase, None), identical to the historical phase-only behavior."""
    import subprocess

    captured: dict = {}

    class _Proc:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_run(args, **_kwargs):
        captured["args"] = args
        return _Proc()

    monkeypatch.setattr(subprocess, "run", fake_run)
    emit_phase_event(tmp_path, "phase_completed", "project",
                     {"phaseTaskId": "ptk-y", "splitId": None, "runId": "r"})
    assert "--split-id" not in captured["args"]


def test_phase_started_pairs_with_phase_completed(v2_project):
    """A full phase (SessionStart -> Stop) yields exactly one phase_started
    paired with the existing phase_completed for the same phase (AC2)."""
    task = _project_task(v2_project)
    phase_session_start.run(
        v2_project, session_uuid=task["sessionUuid"],
        plugin_root="shipwright-project",
    )
    (v2_project / "shipwright_project_config.json").write_text(
        json.dumps({"status": "complete"}), encoding="utf-8",
    )
    phase_session_stop.run(v2_project, task["sessionUuid"])

    started = _events_of_type(v2_project, "phase_started")
    completed = _events_of_type(v2_project, "phase_completed")
    assert len(started) == 1
    assert len(completed) == 1
    assert started[0]["phase"] == completed[0]["phase"] == "project"
