"""Consistency test: all 8 phase plugins must wire the same F3a hook chain.

Plan v4 §F3b: every phase plugin must register
  - SessionStart: capture_session_id + phase_session_start (+ optional plugin-specific extras after)
  - UserPromptSubmit: phase_user_prompt_validate (only entry)
  - Stop: phase_session_stop FIRST, then audit_phase_quality, then generate_handoff
    (plus optional plugin-specific extras after)

This test catches drift if a future iterate adds/removes a hook in one
plugin without updating the others.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PHASE_PLUGINS = [
    "shipwright-project", "shipwright-design", "shipwright-plan",
    "shipwright-build", "shipwright-test", "shipwright-security",
    "shipwright-changelog", "shipwright-deploy",
]


def _hook_commands(hook_block: list[dict]) -> list[str]:
    """Flatten one event's hook chain into a list of script basenames."""
    out: list[str] = []
    for entry in hook_block:
        for hook in entry.get("hooks", []):
            cmd = hook.get("command", "")
            # Take the basename of the script — strip 'uv run' / 'bash' wrappers
            for token in cmd.split():
                if token.endswith(".py") or token.endswith(".sh"):
                    out.append(token.rsplit("/", 1)[-1])
                    break
    return out


def _load_hooks(plugin: str) -> dict:
    path = REPO_ROOT / "plugins" / plugin / "hooks" / "hooks.json"
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize("plugin", PHASE_PLUGINS)
def test_session_start_starts_with_capture_then_phase_session(plugin):
    hooks = _load_hooks(plugin)
    cmds = _hook_commands(hooks.get("SessionStart") or [])
    assert "capture_session_id.py" in cmds, f"{plugin}: missing capture_session_id.py"
    assert "phase_session_start.py" in cmds, f"{plugin}: missing phase_session_start.py"
    # phase_session_start MUST come AFTER capture_session_id (it depends on
    # SHIPWRIGHT_SESSION_ID being already set)
    assert cmds.index("phase_session_start.py") > cmds.index("capture_session_id.py"), (
        f"{plugin}: phase_session_start.py must come after capture_session_id.py"
    )


@pytest.mark.parametrize("plugin", PHASE_PLUGINS)
def test_user_prompt_submit_blocks_via_phase_validate(plugin):
    hooks = _load_hooks(plugin)
    cmds = _hook_commands(hooks.get("UserPromptSubmit") or [])
    assert cmds == ["phase_user_prompt_validate.py"], (
        f"{plugin}: UserPromptSubmit must be exactly [phase_user_prompt_validate.py], got {cmds}"
    )


@pytest.mark.parametrize("plugin", PHASE_PLUGINS)
def test_stop_starts_with_phase_session_stop_then_audit_then_handoff(plugin):
    hooks = _load_hooks(plugin)
    cmds = _hook_commands(hooks.get("Stop") or [])
    assert "phase_session_stop.py" in cmds, f"{plugin}: missing phase_session_stop.py"
    assert "audit_phase_quality_on_stop.py" in cmds, f"{plugin}: missing audit_phase_quality_on_stop.py"
    assert "generate_handoff_on_stop.py" in cmds, f"{plugin}: missing generate_handoff_on_stop.py"
    # Phase task lifecycle must complete BEFORE handoff is generated, so
    # the handoff sees the post-completion phase_tasks[] state.
    i_stop = cmds.index("phase_session_stop.py")
    i_audit = cmds.index("audit_phase_quality_on_stop.py")
    i_handoff = cmds.index("generate_handoff_on_stop.py")
    assert i_stop < i_audit < i_handoff, (
        f"{plugin}: Stop chain order must be phase_session_stop < audit < handoff, "
        f"got positions stop={i_stop} audit={i_audit} handoff={i_handoff}"
    )
    # And phase_session_stop must be FIRST in the Stop chain
    assert i_stop == 0, f"{plugin}: phase_session_stop.py must be first in Stop chain"


def test_master_run_plugin_has_master_stop_check():
    hooks = _load_hooks("shipwright-run")
    cmds = _hook_commands(hooks.get("Stop") or [])
    assert "master_stop_check.py" in cmds
    assert "phase_session_stop.py" not in cmds, (
        "shipwright-run is the master orchestrator, not a phase — phase_session_stop "
        "must NOT be wired here"
    )


def test_master_run_plugin_has_no_phase_user_prompt_validate():
    """Master /shipwright-run is not a phase session — no phase claim to validate."""
    hooks = _load_hooks("shipwright-run")
    cmds = _hook_commands(hooks.get("UserPromptSubmit") or [])
    assert "phase_user_prompt_validate.py" not in cmds


def test_master_run_plugin_has_no_phase_session_start():
    """Master is not a phase — no claim to do."""
    hooks = _load_hooks("shipwright-run")
    cmds = _hook_commands(hooks.get("SessionStart") or [])
    assert "phase_session_start.py" not in cmds
