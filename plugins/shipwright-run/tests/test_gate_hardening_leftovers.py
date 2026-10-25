"""Leftovers of campaign brief-driven-run-a-real-gates (iterate gate-hardening-leftovers).

- one default for a task's CAS ``version`` (absent = 1) everywhere it is read;
- the override refusal is recognised by its exception TYPE, not by its class name;
- a design apply rejected by the gate freezes nothing;
- a guided run past its gate-retry cap is not re-dispatched: ``single-session-next``
  answers ``ask_human`` until a person overrides or recovers the task.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "lib"))

import phase_task_core as core  # noqa: E402
import phase_task_lifecycle as lc  # noqa: E402
from orchestrator import create_config  # noqa: E402
from orchestrator_pkg import cli as cli_mod  # noqa: E402
from orchestrator_pkg import phase_gate  # noqa: E402
from orchestrator_pkg import single_session_loop as loop  # noqa: E402
from orchestrator_pkg.single_session_recovery import recover_single_session  # noqa: E402
from single_session.loop_state import MAX_GATE_RETRIES, load_loop_state  # noqa: E402
from single_session.result_contract import build_phase_runner_result  # noqa: E402

pytestmark = pytest.mark.covers("FR-01.01/AC02")

ASK = {"severity": "ask", "message": "Missing spec.md. Continue?"}
CONFIG = "shipwright_run_config.json"
DEGRADED_ASK = {"severity": "ask", "kind": "canon_degraded", "message": "[canon-degraded] y"}


def _config(root: Path, autonomy: str = "guided") -> None:
    create_config("full_app", "supabase-nextjs", "guided", "jelastic-dev", root,
                  mode="single_session")
    if autonomy != "guided":
        _edit(root, lambda data: data.__setitem__("autonomy", autonomy))


def _edit(root: Path, change) -> None:
    path = root / CONFIG
    data = json.loads(path.read_text(encoding="utf-8"))
    change(data)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _result(root: Path, phase: str = "project") -> dict:
    (root / "artifacts").mkdir(exist_ok=True)
    (root / "artifacts" / f"{phase}.md").write_text(f"# {phase}\n", encoding="utf-8")
    return build_phase_runner_result(ok=True, phase=phase, summary=phase,
                                     artifacts=[f"artifacts/{phase}.md"])


def _gate(ask=()):
    return lambda _root, _step, *, split_id=None, run_id=None: (list(ask), [], True)


def _next(root: Path) -> dict:
    return loop.next_dispatch(root)


def _apply(root: Path, d: dict, phase: str = "project", **kw) -> dict:
    return loop.apply_phase_result(
        root, phase_task_id=d["phaseTaskId"], session_uuid=d["sessionUuid"],
        expected_version=d["version"], result=_result(root, phase), **kw)


def _task(root: Path, ptk: str) -> dict:
    return lc.get_phase_task(root, ptk)["phase_task"]


# --- one default task version ----------------------------------------------------------

def test_a_missing_version_reads_as_the_one_default_everywhere():
    assert core.DEFAULT_TASK_VERSION == 1
    assert core.task_version({}) == 1 and core.task_version({"version": "3"}) == 3
    assert core._check_owner_version(
        {"phaseTaskId": "p", "claimedBySessionUuid": "s", "status": "in_progress"}, "s", 1,
    ) is None


def test_a_version_less_task_completes_with_the_version_its_descriptor_carries(tmp_project):
    _config(tmp_project)
    d = _next(tmp_project)["dispatch"]
    _edit(tmp_project, lambda data: next(
        t for t in data["phase_tasks"] if t["phaseTaskId"] == d["phaseTaskId"]).pop("version"))
    preview = loop.resolve_next_dispatch(tmp_project)["dispatch"]
    assert preview["version"] == core.DEFAULT_TASK_VERSION
    done = _apply(tmp_project, preview, gate=_gate())
    assert done["ok"] is True, done
    assert _task(tmp_project, d["phaseTaskId"])["status"] == "done"


def test_recover_and_redispatch_bump_a_version_less_task_from_the_default(tmp_project):
    _config(tmp_project)
    d = _next(tmp_project)["dispatch"]
    drop = lambda data: next(  # noqa: E731
        t for t in data["phase_tasks"] if t["phaseTaskId"] == d["phaseTaskId"]).pop("version")
    _edit(tmp_project, drop)
    rotated = lc.redispatch_phase_task(tmp_project, phase_task_id=d["phaseTaskId"],
                                       session_uuid=d["sessionUuid"])
    assert (rotated["rotated_from"], rotated["new_version"]) == (1, 2)
    _edit(tmp_project, drop)
    recovered = lc.recover_phase_task(tmp_project, phase_task_id=d["phaseTaskId"])
    assert recovered["new_version"] == 2


# --- the override refusal is a type check --------------------------------------------

def _override_raising(monkeypatch, exc_type) -> None:
    def hook(*, reason, verdict):
        def _raise(_config, _task):
            raise exc_type("no human on the locked config")
        return _raise, {}
    monkeypatch.setattr(phase_gate, "override_hook", hook)


def test_a_subclass_of_the_refusal_reads_override_requires_human(tmp_project, monkeypatch):
    class LockedConfigLostItsHuman(phase_gate.OverrideRefused):
        pass

    _config(tmp_project)
    d = _next(tmp_project)["dispatch"]
    _override_raising(monkeypatch, LockedConfigLostItsHuman)
    res = _apply(tmp_project, d, gate=_gate(ask=[ASK]), override_reason="why")
    assert (res["ok"], res["reason"]) == (False, "override_requires_human")
    assert _task(tmp_project, d["phaseTaskId"])["status"] == "in_progress"


def test_an_unrelated_exception_named_like_the_refusal_is_not_one(tmp_project, monkeypatch):
    impostor = type("OverrideRefused", (RuntimeError,), {})
    _config(tmp_project)
    d = _next(tmp_project)["dispatch"]
    _override_raising(monkeypatch, impostor)
    res = _apply(tmp_project, d, gate=_gate(ask=[ASK]), override_reason="why")
    assert (res["ok"], res["reason"]) == (False, "on_complete_failed")
    assert "validation_overrides" not in json.loads((tmp_project / CONFIG).read_text("utf-8"))


# --- the freeze stays behind the gate ------------------------------------------------

@pytest.mark.parametrize("ask,terminal", [(ASK, None), (DEGRADED_ASK, "ask_human")])
def test_a_design_apply_the_gate_rejects_freezes_nothing(tmp_project, ask, terminal):
    _config(tmp_project)
    project = _next(tmp_project)["dispatch"]
    assert _apply(tmp_project, project, enforce_gate=False)["ok"] is True
    (tmp_project / "shipwright_design_config.json").write_text(
        json.dumps({"splits": ["01-core", "02-api"]}), encoding="utf-8")
    design = _next(tmp_project)["dispatch"]
    assert design["phase"] == "design"
    before = (tmp_project / CONFIG).read_bytes()
    rejected = _apply(tmp_project, design, phase="design", gate=_gate(ask=[ask]))
    assert rejected["reason"] == "phase_gate_failed" and rejected["terminal"] == terminal
    assert (tmp_project / CONFIG).read_bytes() == before


# --- the guided retry cap is enforced at single-session-next -------------------------

DEGRADED = {"severity": "ask", "kind": "canon_degraded", "message": "[canon-degraded] x"}


def _exhaust(root: Path, ask=ASK, rounds: int = MAX_GATE_RETRIES + 1) -> dict:
    """Reject the frontier task until its rejection takes the terminal; return the last
    descriptor (the one a person's override must use)."""
    for _ in range(rounds):
        nxt = _next(root)
        assert nxt["action"] == "dispatch", nxt
        rejected = _apply(root, nxt["dispatch"], gate=_gate(ask=[ask]))
        assert rejected["reason"] == "phase_gate_failed"
    assert rejected["terminal"] == "ask_human", rejected
    return nxt["dispatch"]


def test_a_guided_run_past_the_cap_is_not_redispatched(tmp_project):
    _config(tmp_project)
    last = _exhaust(tmp_project)
    config_before = (tmp_project / CONFIG).read_bytes()
    state_before = load_loop_state(tmp_project)

    answer = _next(tmp_project)
    assert answer["action"] == "ask_human" and answer["reason"] == "phase_gate_terminal"
    assert answer["task"]["phaseTaskId"] == last["phaseTaskId"]
    assert answer["version"] == last["version"] and answer["issues"] == [ASK]
    assert answer["override_allowed"] is True and answer["recover_useful"] is True
    assert (tmp_project / CONFIG).read_bytes() == config_before  # no claim, no rotation
    assert load_loop_state(tmp_project) == state_before          # no dispatch counted
    assert loop.resolve_next_dispatch(tmp_project)["action"] == "ask_human"  # resume card too


def test_the_cli_answers_ask_human_with_exit_0(tmp_project, monkeypatch, capsys):
    _config(tmp_project)
    _exhaust(tmp_project)
    capsys.readouterr()
    monkeypatch.setattr(sys, "argv", ["orchestrator.py", "single-session-next",
                                      "--project-root", str(tmp_project)])
    assert cli_mod.main() == 0
    assert json.loads(capsys.readouterr().out)["action"] == "ask_human"


def test_a_non_retryable_terminal_waits_at_once(tmp_project):
    _config(tmp_project)
    _exhaust(tmp_project, ask=DEGRADED, rounds=1)
    assert _next(tmp_project)["action"] == "ask_human"


def test_an_unknown_autonomy_waits_and_offers_no_override(tmp_project):
    _config(tmp_project, autonomy="bogus")
    _exhaust(tmp_project)
    answer = _next(tmp_project)
    assert answer["action"] == "ask_human" and answer["override_allowed"] is False


def test_a_person_can_still_override_with_the_last_descriptor(tmp_project):
    _config(tmp_project)
    last = _exhaust(tmp_project)
    assert _next(tmp_project)["action"] == "ask_human"
    done = _apply(tmp_project, last, gate=_gate(ask=[ASK]), override_reason="accepted gap")
    assert done["ok"] is True and done["override"]
    assert _next(tmp_project)["action"] == "dispatch"  # the successor


def test_a_plain_pass_with_the_last_descriptor_moves_on(tmp_project):
    """A person fixed the artifacts instead of overriding: the gate passes, the frontier
    moves, and the marker of the finished task no longer matches anything."""
    _config(tmp_project)
    last = _exhaust(tmp_project)
    assert _apply(tmp_project, last, gate=_gate())["ok"] is True
    nxt = _next(tmp_project)
    assert nxt["action"] == "dispatch" and nxt["dispatch"]["phaseTaskId"] != last["phaseTaskId"]


def test_recover_gives_the_task_fresh_tries(tmp_project):
    _config(tmp_project)
    last = _exhaust(tmp_project)
    assert recover_single_session(tmp_project, phase_task_id=last["phaseTaskId"])["ok"]
    again = _next(tmp_project)
    assert again["action"] == "dispatch" and again["attempt"] == 1


def test_an_autonomous_run_still_takes_the_failed_terminal(tmp_project):
    _config(tmp_project, autonomy="autonomous")
    for _ in range(MAX_GATE_RETRIES + 1):
        nxt = _next(tmp_project)
        assert nxt["action"] == "dispatch", nxt
        out = _apply(tmp_project, nxt["dispatch"], gate=_gate(ask=[ASK]))
    assert out["run_status"] == "failed"
    assert "gateTerminal" not in load_loop_state(tmp_project)
    assert _next(tmp_project)["action"] == "failed"


def test_a_crash_resume_after_a_retryable_rejection_still_dispatches(tmp_project):
    """Two retryable rejections, then a dispatch whose result is lost in a crash: the
    counters are past the cap but no rejection took the terminal, so this is no reason to
    ask (plan review: the counters alone cannot tell the two apart)."""
    _config(tmp_project)
    for _ in range(MAX_GATE_RETRIES):
        d = _next(tmp_project)["dispatch"]
        assert _apply(tmp_project, d, gate=_gate(ask=[ASK]))["terminal"] is None
    for _ in range(2):  # the dispatch that crashed, then the resume
        assert _next(tmp_project)["action"] == "dispatch"


def test_a_marker_for_another_run_task_or_version_is_ignored():
    from single_session.loop_state import gate_terminal_for, record_gate_terminal

    state = record_gate_terminal({"runId": "r1"}, phase_task_id="p1", version=3, issues=[])
    assert gate_terminal_for(state, run_id="r1", phase_task_id="p1", version=3)
    assert gate_terminal_for(state, run_id="r2", phase_task_id="p1", version=3) is None
    assert gate_terminal_for(state, run_id="r1", phase_task_id="p2", version=3) is None
    assert gate_terminal_for(state, run_id="r1", phase_task_id="p1", version=4) is None
    bad = {**state, "gateTerminal": {"phaseTaskId": "p1", "version": "x"}}
    assert gate_terminal_for(bad, run_id="r1", phase_task_id="p1", version=3) is None
    assert gate_terminal_for(None, run_id="r1", phase_task_id="p1", version=3) is None


def test_an_unreadable_loop_state_does_not_block_the_resolver(tmp_project):
    _config(tmp_project)
    _exhaust(tmp_project)
    (tmp_project / ".shipwright" / "run_loop_state.json").write_text("{bad", encoding="utf-8")
    assert loop.resolve_next_dispatch(tmp_project)["action"] == "dispatch"
