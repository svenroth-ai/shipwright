"""The gate cap is held at ``single-session-next`` also for terminals no loop state counted.

Doubt review of iterate gate-hardening-leftovers: when no loop state describes the task,
the rejection takes the ``ask_human`` terminal at once, and the marker must still be
written so the next dispatch waits for a person. And an archived split's terminal says
that recovering it would not help (a re-dispatched build works on the next split).
"""
from __future__ import annotations

import json

import pytest

from tests.test_gate_hardening_leftovers import (
    ASK,
    _apply,
    _config,
    _exhaust,
    _gate,
    _next,
    load_loop_state,
)

pytestmark = pytest.mark.covers("FR-01.01/AC02")


def test_an_uncounted_ask_human_terminal_is_held_at_next_too(tmp_project):
    """No loop state describes the task (a stale pointer at another task here), so the
    rejection takes the terminal at once; single-session-next must hold it all the same
    (doubt review)."""
    _config(tmp_project)
    d = _next(tmp_project)["dispatch"]
    path = tmp_project / ".shipwright" / "run_loop_state.json"
    state = json.loads(path.read_text(encoding="utf-8"))
    path.write_text(json.dumps({**state, "currentPhaseTaskId": "elsewhere"}), encoding="utf-8")
    rejected = _apply(tmp_project, d, gate=_gate(ask=[ASK]))
    assert rejected["terminal"] == "ask_human" and rejected["attempt"] is None
    assert _next(tmp_project)["action"] == "ask_human"
    assert load_loop_state(tmp_project)["currentPhaseTaskId"] == "elsewhere"  # pointer kept


def test_an_uncounted_terminal_without_any_loop_state_starts_one(tmp_project):
    _config(tmp_project)
    d = _next(tmp_project)["dispatch"]
    (tmp_project / ".shipwright" / "run_loop_state.json").unlink()
    assert _apply(tmp_project, d, gate=_gate(ask=[ASK]))["terminal"] == "ask_human"
    assert _next(tmp_project)["action"] == "ask_human"


def test_an_uncounted_terminal_leaves_an_unreadable_loop_state_alone(tmp_project):
    _config(tmp_project)
    d = _next(tmp_project)["dispatch"]
    path = tmp_project / ".shipwright" / "run_loop_state.json"
    path.write_text("{bad", encoding="utf-8")
    assert _apply(tmp_project, d, gate=_gate(ask=[ASK]))["terminal"] == "ask_human"
    assert path.read_text(encoding="utf-8") == "{bad"


def test_an_archived_split_terminal_says_recover_would_not_help(tmp_project):
    _config(tmp_project)
    archived = {"severity": "ask", "kind": "archived_split", "message": "Sections not complete"}
    _exhaust(tmp_project, ask=archived, rounds=1)
    answer = _next(tmp_project)
    assert answer["action"] == "ask_human" and answer["recover_useful"] is False


def test_an_archived_flag_on_another_kind_also_says_recover_would_not_help(tmp_project):
    _config(tmp_project)
    degraded = {"severity": "ask", "kind": "canon_degraded", "archived_split": True,
                "message": "old verifier"}
    _exhaust(tmp_project, ask=degraded, rounds=1)
    assert _next(tmp_project)["recover_useful"] is False

