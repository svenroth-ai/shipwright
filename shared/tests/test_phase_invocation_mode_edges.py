"""Adversarial edges of the invocation-mode resolver — every case from the review round.

The single invariant under test: **`standalone` is reachable ONLY by omitting the token.**
Every other degenerate input (empty token, unsubstituted placeholder, corrupt config,
stale/terminal/wrong-phase id) must produce a structured `error` that STOPs the caller —
never a silent downgrade to standalone, which is the bug this module exists to prevent.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO / "shared" / "scripts" / "lib"))

from phase_invocation_mode import resolve_invocation_mode  # noqa: E402

CONFIG = "shipwright_run_config.json"


def _write(root: Path, config) -> Path:
    (root / CONFIG).write_text(json.dumps(config), encoding="utf-8")
    return root


def _mode(root: Path, token, phase=None) -> dict:
    payload, _task, _config = resolve_invocation_mode(root, token, phase)
    return payload


# --- Only an ABSENT token means standalone -----------------------------------------------


def test_none_token_is_standalone(tmp_path):
    assert _mode(tmp_path, None)["mode"] == "standalone"


@pytest.mark.parametrize("token", ["", "   ", "\t"])
def test_empty_or_blank_token_is_error_not_standalone(tmp_path, token):
    """`--phase-task-id ""` is a briefing bug, not a standalone run. Downgrading it to
    standalone would let a broken dispatch run in the wrong mode (external review, GPT)."""
    out = _mode(tmp_path, token)
    assert out["mode"] == "error"
    assert out["reason"] == "invalid_phase_task_id"
    assert "OMIT the flag" in out["message"]


@pytest.mark.parametrize(
    "token", ["{phaseTaskId}", "<phaseTaskId>", "${phaseTaskId}", "{{phaseTaskId}}"],
)
def test_unsubstituted_placeholder_is_error_not_standalone(tmp_path, token):
    """The skills carry the flag inline in a template, so the literal placeholder is easy to
    pass. It could plausibly map to standalone — for a HAND invocation that would even be
    nicer — but the same shape arises when a driven master fails to substitute the real
    token, and there standalone is the silent catastrophe. Loud and recoverable wins: the
    message names the fix (Stage-3 doubt review)."""
    out = _mode(tmp_path, token)
    assert out["mode"] == "error"
    assert out["reason"] == "unsubstituted_phase_task_id_placeholder"
    assert "OMIT the" in out["message"]


def test_a_real_token_is_not_mistaken_for_a_placeholder(tmp_path):
    """The placeholder guard must not swallow genuine ids."""
    out = _mode(tmp_path, "ptk-0bb1b9a6")
    assert out["mode"] == "error"
    assert out["reason"] == "no_run_config"  # resolved as a real token, config just absent


# --- A v2-SHAPED but corrupt config must not raise ---------------------------------------


@pytest.mark.parametrize("tasks", [[None], [{}, "nope"], {}, 7, [[]]])
def test_structurally_corrupt_phase_tasks_never_raises(tmp_path, tasks):
    """`{"schemaVersion": 2, "phase_tasks": [null]}` used to reach `task.get(...)` and raise
    AttributeError — breaking the "never raises" contract precisely on the token-bearing
    path, which must yield a structured error (external review, GPT)."""
    _write(tmp_path, {"schemaVersion": 2, "status": "in_progress", "phase_tasks": tasks})

    out = _mode(tmp_path, "ptk-abc", phase="build")
    assert out["mode"] == "error"
    assert out["reason"] == "run_config_unreadable"


@pytest.mark.parametrize("tasks", [[None], {}, 7])
def test_corrupt_phase_tasks_on_the_tokenless_path_reports_not_live(tmp_path, tasks):
    """The no-token path must survive the same corruption and simply report "no live run"
    rather than crashing a hand-invoked skill."""
    _write(tmp_path, {"schemaVersion": 2, "status": "in_progress", "phase_tasks": tasks})

    out = _mode(tmp_path, None)
    assert out["mode"] == "standalone"
    assert out["pipeline_active"] is False
    assert out["requires_out_of_sequence_warning"] is False


# --- Unclaimed task: refuse, but name the remedy -----------------------------------------


def _cfg_with(status: str) -> dict:
    return {
        "schemaVersion": 2, "mode": "single_session", "status": "in_progress",
        "phase_tasks": [{
            "phaseTaskId": "ptk-1", "phase": "build", "splitId": None, "version": 1,
            "status": status, "sessionUuid": "s", "claimedBySessionUuid": None,
            "prerequisites": [],
        }],
    }


def test_unclaimed_task_error_names_the_resume_remedy(tmp_path):
    """A master that briefs a phase-runner straight from the READ-ONLY resume descriptor
    hands over an unclaimed (awaiting_launch) token. Refusing is right — an unclaimed task
    grants no pipeline authority — but a bare refusal would fail the whole run, so the
    message must say how to fix it (Stage-3 doubt review)."""
    _write(tmp_path, _cfg_with("awaiting_launch"))

    out = _mode(tmp_path, "ptk-1", phase="build")
    assert out["mode"] == "error"
    assert out["reason"] == "phase_task_not_actionable"
    assert "single-session-next" in out["message"]
    assert "never CLAIMED" in out["message"]


def test_terminal_task_error_names_the_recover_remedy(tmp_path):
    _write(tmp_path, _cfg_with("done"))

    out = _mode(tmp_path, "ptk-1", phase="build")
    assert out["mode"] == "error"
    assert out["reason"] == "phase_task_not_actionable"
    assert "recover-phase-task" in out["message"]
