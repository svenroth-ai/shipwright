"""``runner_spawn_guard.py`` -- a campaign runner may spawn only its five reviewers."""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import pytest

HOOKS = Path(__file__).resolve().parent.parent / "scripts" / "hooks"
sys.path.insert(0, str(HOOKS))
import runner_spawn_guard as guard  # noqa: E402

pytestmark = pytest.mark.covers("FR-01.11")


@pytest.fixture(autouse=True)
def _state_in_tmp(tmp_path, monkeypatch):
    monkeypatch.delenv(guard._OFF_ENV, raising=False)
    monkeypatch.setattr(guard, "_state_file", lambda cwd, agent_id: tmp_path / f"{agent_id}.json")


def _payload(kind="spec-reviewer", agent_id="a1", agent_type="shipwright-iterate:sub-iterate-runner", tool="Agent"):
    p = {"hook_event_name": "PreToolUse", "tool_name": tool, "cwd": "/x",
         "tool_input": {"subagent_type": kind, "model": "opus", "prompt": "p"}}
    if agent_id:
        p["agent_id"] = agent_id
    if agent_type:
        p["agent_type"] = agent_type
    return p


def _denied(decision):
    return decision is not None and decision["hookSpecificOutput"]["permissionDecision"] == "deny"


@pytest.mark.parametrize("kind", sorted(guard.ALLOWED) + ["shipwright-build:spec-reviewer", "shipwright-plan:opus-plan-reviewer"])
def test_runner_may_spawn_each_of_its_five_reviewers(kind):
    assert guard.handle_payload(_payload(kind)) is None


@pytest.mark.parametrize("kind", ["sub-iterate-runner", "section-builder", "browser-fixer", "general-purpose", "", "shipwright-test:browser-fixer"])
def test_runner_spawning_anything_else_is_denied(kind):
    assert _denied(guard.handle_payload(_payload(kind)))


def test_missing_subagent_type_is_denied_not_defaulted():
    p = _payload()
    del p["tool_input"]["subagent_type"]
    assert _denied(guard.handle_payload(p))


def test_the_legacy_task_tool_name_is_guarded_too():
    assert _denied(guard.handle_payload(_payload("general-purpose", tool="Task")))


def test_the_fourth_spawn_of_one_type_is_denied_but_other_types_are_not():
    for _ in range(guard.MAX_SPAWNS_PER_TYPE):
        assert guard.handle_payload(_payload("code-reviewer")) is None
    assert _denied(guard.handle_payload(_payload("code-reviewer")))
    assert guard.handle_payload(_payload("doubt-reviewer")) is None


def test_the_cap_is_per_runner():
    for _ in range(guard.MAX_SPAWNS_PER_TYPE):
        guard.handle_payload(_payload("code-reviewer", agent_id="a1"))
    assert guard.handle_payload(_payload("code-reviewer", agent_id="a2")) is None


@pytest.mark.parametrize("override", [
    {"agent_id": None},                                              # main session
    {"agent_type": "shipwright-build:section-builder"},               # another subagent
    {"agent_type": None},
    {"agent_id": "../escape"},                                        # never a file name
])
def test_everything_that_is_not_a_runner_is_left_alone(override):
    assert guard.handle_payload(_payload("general-purpose", **override)) is None


def test_other_tools_and_events_are_left_alone():
    assert guard.handle_payload({**_payload("general-purpose"), "tool_name": "Bash"}) is None
    assert guard.handle_payload({**_payload("general-purpose"), "hook_event_name": "PostToolUse"}) is None


def test_the_operator_can_lift_the_guard(monkeypatch):
    monkeypatch.setenv(guard._OFF_ENV, "off")
    assert guard.handle_payload(_payload("general-purpose")) is None


def test_main_prints_the_deny_json_and_fails_open_on_garbage(monkeypatch, capsys):
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(_payload("general-purpose"))))
    assert guard.main() == 0
    assert json.loads(capsys.readouterr().out)["hookSpecificOutput"]["permissionDecision"] == "deny"
    monkeypatch.setattr(sys, "stdin", io.StringIO("not json"))
    assert guard.main() == 0
    assert capsys.readouterr().out == ""


def test_the_hook_is_registered_for_both_spawn_tool_names():
    hooks = json.loads((HOOKS.parent.parent / "hooks" / "hooks.json").read_text(encoding="utf-8"))
    blocks = [b for b in hooks["hooks"]["PreToolUse"]
              if any("runner_spawn_guard.py" in h["command"] for h in b["hooks"])]
    assert len(blocks) == 1 and set(blocks[0]["matcher"].split("|")) == {"Agent", "Task"}
