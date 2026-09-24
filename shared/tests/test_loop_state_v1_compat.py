"""v1-degrades-safely test (campaign-dag-scheduler R4, plan § R4 work
breakdown item 6): ``"version": 2`` is an ADDITIVE superset of v1's row
shape, and the guarantee is explicitly scoped to ``cmd_next``'s selection
logic only — a v1 (pre-R4) ``loop_state.json``, entirely missing the
``version`` key and every lease/fencing field this sub-iterate adds, must
still degrade safely through that one code path: plain FIFO among
``pending`` units, still honoring R1-vintage ``depends_on`` (which
predates this sub-iterate and is NOT one of the fields the "v1" label
excludes).

**Explicitly NOT covered here** (per the plan's own text: "true
mixed-binary safety across every v1 code path ... is out of scope,
accepted"): ``cmd_init``'s reconcile dispatch for `kind == "sub_iterate"`
unconditionally takes the NEW lease-based path the moment ANY code from
this sub-iterate touches the file, version key or not — there is no
promise that an `in_progress` v1 row reconciles identically to how the
pre-R4 binary would have. That is a real, accepted, documented gap, not
a regression to disprove.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "lib"))

from autonomous_loop import cmd_next  # noqa: E402


class FakeArgs:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


@pytest.fixture
def state_dir(tmp_path):
    ship = tmp_path / ".shipwright"
    ship.mkdir()
    return ship


def _v1_unit(id_, status="pending", depends_on=None, merged_commit=None):
    """A unit row shaped exactly as R1 (pre-R4) produced it: no
    `attempt_id`, no `lease_touched_at`/`lease_expires_at` — none of R4's
    fencing/lease vocabulary exists yet."""
    return {
        "id": id_, "spec_path": f"spec/{id_}.md", "status": status,
        "attempt": 0, "started_at": None, "finished_at": None,
        "commit": None, "head_sha": None, "branch": None,
        "result_path": None, "handoff_path": None, "failure_reason": None,
        "depends_on": depends_on or [], "merged_commit": merged_commit,
    }


def _write_v1_state(state_dir, units) -> Path:
    """No `"version"` key at all — the exact shape a pre-R4 file has."""
    state_path = state_dir / "loop_state.json"
    state = {
        "loop_id": "v1-loop", "kind": "sub_iterate", "root_session_id": "",
        "branch_strategy": "single-branch", "units": units,
    }
    assert "version" not in state
    state_path.write_text(json.dumps(state), encoding="utf-8")
    return state_path


@patch("autonomous_loop.subprocess.run")
class TestCmdNextDegradesSafelyOnV1File:
    def test_picks_first_pending_no_version_key_no_crash(self, mock_run, state_dir, capsys):
        mock_run.return_value = type("R", (), {"returncode": 0, "stdout": "abc123\n"})()
        state_path = _write_v1_state(state_dir, [_v1_unit("A"), _v1_unit("B")])
        ret = cmd_next(FakeArgs(state=str(state_path)))
        assert ret == 0
        out = json.loads(capsys.readouterr().out)
        assert out["id"] == "A"

    def test_still_honors_r1_vintage_depends_on(self, mock_run, state_dir, capsys):
        """`depends_on` is R1 vintage, not an R4 addition — a v1 file
        already had it, so the FIFO-skip-if-blocked behavior is unchanged,
        not "ignored" the way genuinely-new lease/fencing fields are."""
        mock_run.return_value = type("R", (), {"returncode": 0, "stdout": "abc123\n"})()
        state_path = _write_v1_state(state_dir, [
            _v1_unit("A", status="pending", depends_on=["B"]),
            _v1_unit("B", status="pending"),
        ])
        ret = cmd_next(FakeArgs(state=str(state_path)))
        assert ret == 0
        out = json.loads(capsys.readouterr().out)
        assert out["id"] == "B"  # A skipped (blocked on B), B is ready

    def test_missing_attempt_id_and_lease_fields_never_raise(self, mock_run, state_dir, capsys):
        """The literal absence of every R4 field (`attempt_id`,
        `lease_touched_at`, `lease_expires_at`) must not raise `KeyError`
        anywhere in the selection path."""
        mock_run.return_value = type("R", (), {"returncode": 0, "stdout": "abc123\n"})()
        unit = _v1_unit("A")
        assert "attempt_id" not in unit and "lease_expires_at" not in unit
        state_path = _write_v1_state(state_dir, [unit])
        ret = cmd_next(FakeArgs(state=str(state_path)))
        assert ret == 0
        out = json.loads(capsys.readouterr().out)
        assert out["id"] == "A"
        assert out["attempt"] == 0

    def test_all_merged_reports_done_same_as_before(self, mock_run, state_dir, capsys):
        mock_run.return_value = type("R", (), {"returncode": 0, "stdout": "abc123\n"})()
        state_path = _write_v1_state(state_dir, [
            _v1_unit("A", status="merged", merged_commit="sha-a"),
        ])
        ret = cmd_next(FakeArgs(state=str(state_path)))
        assert ret == 2
        out = json.loads(capsys.readouterr().out)
        assert out == {"done": True, "reason": "All units processed"}
