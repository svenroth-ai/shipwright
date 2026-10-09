"""The sub-iterate-runner carries the Agent tool and its lease touch carries the claim token.

Two pins, one change set: (1) the runner spawns the internal arms and the cascade
itself (3f-bis stays the fallback); (2) the lease-touch command in the runner brief
passes ``--attempt``/``--attempt-id`` so a claimed row accepts it and the unit's
``worktree`` reaches ``loop_state.json``.
"""

from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
_ITERATE = _REPO / "plugins" / "shipwright-iterate"
_RUNNER = _ITERATE / "agents" / "sub-iterate-runner.md"
_REFS = _ITERATE / "skills" / "iterate" / "references"
_CLI = _REPO / "shared" / "scripts" / "checks" / "check_unit_lease.py"

_spec = importlib.util.spec_from_file_location("check_unit_lease_for_runner_test", _CLI)
assert _spec is not None and _spec.loader is not None
check_unit_lease = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check_unit_lease)


def _runner() -> str:
    return _RUNNER.read_text(encoding="utf-8").replace("\r\n", "\n")


@pytest.mark.covers("FR-01.11")
def test_runner_tools_list_includes_agent():
    tools = re.search(r"^tools:\s*(.+)$", _runner(), re.M)
    assert tools is not None
    assert "Agent" in [t.strip() for t in tools.group(1).split(",")]


@pytest.mark.covers("FR-01.11")
def test_runner_spawns_internal_reviews_at_the_resolved_tiers_and_keeps_the_fallback():
    body = _runner()
    assert "campaign-step-3-7-internal-reviews.md" in body
    assert "delegated-to-orchestrator" in body, "3f-bis stays the fallback"
    ref = (_REFS / "campaign-step-3-7-internal-reviews.md").read_text(encoding="utf-8")
    for reviewer in ("architecture-internal-reviewer", "opus-plan-reviewer",
                     "spec-reviewer", "code-reviewer", "doubt-reviewer"):
        assert reviewer in ref, f"{reviewer} must be named in the spawn reference"
    assert "no-spawn-site" in ref


_TIER_FILES = ("agents/sub-iterate-runner.md",
               "skills/iterate/references/campaign-step-3-7-internal-reviews.md",
               "skills/iterate/references/campaign-step-3-5-plan-review.md",
               "skills/iterate/references/campaign-mode.md",
               "skills/iterate/references/iteration-reviews.md",
               "skills/iterate/SKILL.md")


@pytest.mark.covers("FR-01.11")
@pytest.mark.parametrize("rel", _TIER_FILES)
def test_no_runner_review_spawn_hardcodes_a_model_tier(rel):
    text = (_ITERATE / rel).read_text(encoding="utf-8")
    assert not re.search(r"model=(opus|sonnet|haiku|fable)(?![a-z])", text), (
        f"{rel}: a hard-coded model= overrides the operator's resolved review tier")
    assert not re.search(r"--model-tier (opus|sonnet|haiku|fable)(?![a-z])", text), (
        f"{rel}: a hard-coded --model-tier mis-records the tier the spawn used")

@pytest.mark.covers("FR-01.11")
def test_the_tiers_travel_orchestrator_to_runner_to_each_spawn():
    mode = (_REFS / "campaign-mode.md").read_text(encoding="utf-8")
    runner = _runner()
    ref = (_REFS / "campaign-step-3-7-internal-reviews.md").read_text(encoding="utf-8")
    # orchestrator briefs the runner with both resolved tiers …
    assert "review_tier (= `review.resolved`)" in mode and "(= `plan_review.resolved`)" in mode
    # … the runner declares them as inputs and spawns/records with them …
    assert "`review_tier` / `plan_review_tier`" in runner
    assert "model=<review_tier>" in runner and "model=<plan_review_tier>" in runner
    assert "--model-tier <review_tier>" in runner and "--model-tier <plan_review_tier>" in runner
    # … and the spawn reference owns the inherit rule.
    assert "only when the tier is `inherit`" in ref


@pytest.mark.covers("FR-01.11")
def test_3f_bis_stays_an_independent_gate_and_runner_spawns_are_allow_listed():
    text = (_REFS / "campaign-mode.md").read_text(encoding="utf-8")
    assert "runner_settled" not in text, "no self-attested skip of the orchestrator's gate"
    ref = (_REFS / "campaign-step-3-7-internal-reviews.md").read_text(encoding="utf-8")
    assert "never `sub-iterate-runner`, `section-builder`" in ref and "Cap re-review" in ref


def _runner_touch_argv(state: Path, unit: str, attempt_id: str) -> list[str]:
    """The runner brief's lease-touch flags, with the placeholders filled in."""
    block = _runner().split("check_unit_lease.py", 1)[1].split("```", 1)[0]
    flags = re.findall(r'(--[a-z-]+) "\{([a-z_]+)\}"', block)
    fill = {"state_path": str(state), "sub_iterate_id": unit, "attempt": "0",
            "attempt_id": attempt_id, "project_root": "/wt/unit",
            "branch_name": "iterate/x", "campaign_worktree": str(state.parent.parent)}
    return ["touch"] + [a for flag, name in flags for a in (flag, fill[name])]


@pytest.mark.covers("FR-01.11")
def test_the_runner_briefs_touch_writes_the_worktree_on_a_claimed_row(tmp_path):
    state = tmp_path / ".shipwright" / "loop_state.json"
    state.parent.mkdir(parents=True)
    state.write_text(json.dumps({"kind": "sub_iterate", "loop_id": "L", "units": [
        {"id": "R1", "status": "running", "attempt": 0, "attempt_id": "L-R1-a0"}]}),
        encoding="utf-8")
    argv = _runner_touch_argv(state, "R1", "L-R1-a0")
    assert "--attempt-id" in argv, "the brief's touch must carry the fencing token"
    assert check_unit_lease.main(argv) == 0
    row = json.loads(state.read_text(encoding="utf-8"))["units"][0]
    assert row["worktree"] == "/wt/unit" and row["branch"] == "iterate/x"
    # …and without the token a claimed row refuses (the original defect).
    tokenless = [a for i, a in enumerate(argv) if a != "--attempt-id" and argv[i - 1] != "--attempt-id"]
    assert check_unit_lease.main(tokenless) != 0


@pytest.mark.covers("FR-01.11")
def test_shared_tests_do_not_inherit_the_campaign_loop_env():
    """A runner's shell has SHIPWRIGHT_LOOP_ID / SHIPWRIGHT_LOOP_UNIT_ID set; with them
    inherited, test_generate_handoff_on_stop alone failed 8 of 24 tests."""
    import os
    import subprocess
    import sys

    env = {**os.environ, "SHIPWRIGHT_LOOP_ID": "loop-x", "SHIPWRIGHT_LOOP_UNIT_ID": "u1"}
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
         str(_REPO / "shared" / "tests" / "test_generate_handoff_on_stop.py")],
        env=env, cwd=_REPO, capture_output=True, text=True, timeout=300)
    assert proc.returncode == 0, proc.stdout[-1500:]
