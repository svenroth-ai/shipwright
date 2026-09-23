"""CLI tests for shared/scripts/checks/check_unit_attempt.py
(campaign-dag-scheduler R4) — the runner's own pre-F6/pre-push fencing
pre-flight. Same ``importlib``-loaded-module pattern as the sibling
``test_check_unit_lease.py`` (``checks/`` is not an importable package).
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CLI = _REPO_ROOT / "shared" / "scripts" / "checks" / "check_unit_attempt.py"

_spec = importlib.util.spec_from_file_location("check_unit_attempt_for_test", _CLI)
assert _spec is not None and _spec.loader is not None
check_unit_attempt = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check_unit_attempt)


def _write_state(path: Path, units: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"loop_id": "test-loop", "units": units}), encoding="utf-8")


def test_matching_token_allows(tmp_path, capsys):
    state = tmp_path / "loop_state.json"
    _write_state(state, [{"id": "R4", "status": "running", "attempt_id": "loop-R4-a0"}])

    rc = check_unit_attempt.main([
        "--state", str(state), "--unit", "R4", "--attempt-id", "loop-R4-a0", "--json",
    ])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["decision"] == "allow"
    assert payload["reason_code"] == "ok"


def test_stale_token_blocks_with_exit_5(tmp_path, capsys):
    state = tmp_path / "loop_state.json"
    _write_state(state, [{"id": "R4", "status": "running", "attempt_id": "loop-R4-a1"}])

    rc = check_unit_attempt.main([
        "--state", str(state), "--unit", "R4", "--attempt-id", "loop-R4-a0", "--json",
    ])
    assert rc == 5
    payload = json.loads(capsys.readouterr().out)
    assert payload["decision"] == "block"
    assert payload["reason_code"] == "stale_attempt"


def test_missing_unit_blocks_with_exit_1(tmp_path, capsys):
    state = tmp_path / "loop_state.json"
    _write_state(state, [{"id": "R4", "status": "running", "attempt_id": "loop-R4-a0"}])

    rc = check_unit_attempt.main([
        "--state", str(state), "--unit", "R99", "--attempt-id", "loop-R4-a0", "--json",
    ])
    assert rc == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["decision"] == "block"
    assert payload["reason_code"] == "unit_not_found"


def test_missing_state_file_blocks_with_exit_1(tmp_path, capsys):
    rc = check_unit_attempt.main([
        "--state", str(tmp_path / "nope.json"), "--unit", "R4", "--attempt-id", "x", "--json",
    ])
    assert rc == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["reason_code"] == "state_not_found"


def test_never_claimed_unit_with_no_attempt_id_field_blocks(tmp_path, capsys):
    # A row that was never claimed at all has no `attempt_id` key — a
    # runner asserting one is a structural mismatch, never silently allowed.
    state = tmp_path / "loop_state.json"
    _write_state(state, [{"id": "R4", "status": "pending"}])

    rc = check_unit_attempt.main([
        "--state", str(state), "--unit", "R4", "--attempt-id", "loop-R4-a0", "--json",
    ])
    assert rc == 5
    payload = json.loads(capsys.readouterr().out)
    assert payload["reason_code"] == "stale_attempt"
