"""CLI tests for shared/scripts/checks/check_unit_lease.py (R2 capability)."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CLI = _REPO_ROOT / "shared" / "scripts" / "checks" / "check_unit_lease.py"

_spec = importlib.util.spec_from_file_location("check_unit_lease_for_test", _CLI)
assert _spec is not None and _spec.loader is not None
check_unit_lease = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check_unit_lease)


def _write_state(path: Path, units: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"loop_id": "test-loop", "units": units}), encoding="utf-8")


def test_touch_allow_prints_lease_json(tmp_path, capsys):
    state = tmp_path / "loop_state.json"
    _write_state(state, [{"id": "R2", "status": "in_progress"}])

    rc = check_unit_lease.main([
        "touch", "--state", str(state), "--unit-id", "R2",
        "--worktree", str(tmp_path), "--branch", "iterate/x-r2", "--json",
    ])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["decision"] == "allow"
    assert payload["lease"]["worktree"] == str(tmp_path)
    assert payload["lease"]["branch"] == "iterate/x-r2"


def test_touch_block_for_missing_unit(tmp_path, capsys):
    state = tmp_path / "loop_state.json"
    _write_state(state, [{"id": "R2", "status": "in_progress"}])

    rc = check_unit_lease.main([
        "touch", "--state", str(state), "--unit-id", "R99",
        "--worktree", str(tmp_path), "--branch", "b", "--json",
    ])
    assert rc == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["decision"] == "block"


def test_touch_block_for_missing_state_file(tmp_path, capsys):
    rc = check_unit_lease.main([
        "touch", "--state", str(tmp_path / "nope.json"), "--unit-id", "R2",
        "--worktree", str(tmp_path), "--branch", "b", "--json",
    ])
    assert rc == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["decision"] == "block"


def test_touch_allow_with_matching_campaign_worktree(tmp_path, capsys):
    campaign_wt = tmp_path
    state = campaign_wt / ".shipwright" / "loop_state.json"
    _write_state(state, [{"id": "R2", "status": "in_progress"}])

    rc = check_unit_lease.main([
        "touch", "--state", str(state), "--unit-id", "R2",
        "--worktree", str(campaign_wt), "--branch", "b",
        "--campaign-worktree", str(campaign_wt), "--json",
    ])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["decision"] == "allow"


def test_touch_block_for_mismatched_campaign_worktree(tmp_path, capsys):
    state = tmp_path / ".shipwright" / "loop_state.json"
    _write_state(state, [{"id": "R2", "status": "in_progress"}])
    other = tmp_path / "other-campaign"
    other.mkdir()

    rc = check_unit_lease.main([
        "touch", "--state", str(state), "--unit-id", "R2",
        "--worktree", str(tmp_path), "--branch", "b",
        "--campaign-worktree", str(other), "--json",
    ])
    assert rc == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["decision"] == "block"


def test_touch_warns_on_stderr_for_a_stale_attempt_conflict(tmp_path, capsys):
    state = tmp_path / "loop_state.json"
    _write_state(state, [{"id": "R2", "status": "in_progress"}])

    check_unit_lease.main([
        "touch", "--state", str(state), "--unit-id", "R2",
        "--worktree", str(tmp_path), "--branch", "b", "--attempt", "2", "--json",
    ])
    capsys.readouterr()  # discard first call's output

    rc = check_unit_lease.main([
        "touch", "--state", str(state), "--unit-id", "R2",
        "--worktree", str(tmp_path), "--branch", "b", "--attempt", "0", "--json",
    ])
    assert rc == 0
    captured = capsys.readouterr()
    assert "WARNING" in captured.err
    assert "no longer mine" in captured.err
