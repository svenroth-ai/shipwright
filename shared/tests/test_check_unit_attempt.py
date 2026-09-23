"""CLI tests for shared/scripts/checks/check_unit_attempt.py
(campaign-dag-scheduler R4) — the runner's own pre-F6/pre-push fencing
pre-flight. Same ``importlib``-loaded-module pattern as the sibling
``test_check_unit_lease.py`` (``checks/`` is not an importable package).
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from lib.loop_state import enforce_record_fencing

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


def test_released_unit_with_still_matching_token_blocks(tmp_path, capsys):
    """External Tier-3 PR review (GPT, round 18): `cmd_release` moves a
    claimed unit back to `pending`/`failed` WITHOUT rotating `attempt_id`
    — a stale runner whose claim was released out from under it still
    presents a token that matches exactly. A matching token alone must not
    be enough; the row's status must also still be one `lib.loop_state.
    ACTIVE` recognizes as runner/merge-lane-owned."""
    state = tmp_path / "loop_state.json"
    _write_state(state, [{"id": "R4", "status": "pending", "attempt_id": "loop-R4-a0",
                           "released_at": "2026-09-23T00:00:00Z"}])

    rc = check_unit_attempt.main([
        "--state", str(state), "--unit", "R4", "--attempt-id", "loop-R4-a0", "--json",
    ])
    assert rc == 5
    payload = json.loads(capsys.readouterr().out)
    assert payload["decision"] == "block"
    assert payload["reason_code"] == "unit_not_active"


def test_a_reclaim_after_this_check_passes_is_still_caught_at_record_time(tmp_path, capsys):
    """External Tier-3 PR review (GPT, PR #790 round 20): this CLI and the
    runner's later `git push` are separate process invocations with no lock
    held across them, so a reclaim landing in that window is NOT something
    this check alone can prevent — see the round-20 addition to this
    module's own docstring. What this test demonstrates is the claim that
    docstring makes: the LOAD-BEARING atomic gate is
    `lib.loop_state.enforce_record_fencing`, called by `cmd_record` from
    inside the same `loop.lock` acquisition that performs the write. A unit
    reclaimed (a fresh `attempt_id` minted) AFTER this CLI allowed the push
    but BEFORE the runner's own `cmd_record` call still gets rejected there,
    under lock — the stale runner's completion report is parked, never
    silently recorded, regardless of what this earlier check said."""
    state = tmp_path / "loop_state.json"
    _write_state(state, [{"id": "R4", "status": "running", "attempt_id": "loop-R4-a0"}])

    rc = check_unit_attempt.main([
        "--state", str(state), "--unit", "R4", "--attempt-id", "loop-R4-a0", "--json",
    ])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["decision"] == "allow"

    # A reclaim happens in the window between this CLI's check and the
    # runner's own record call — same unit, fresh attempt_id.
    reclaimed_state = json.loads(state.read_text(encoding="utf-8"))
    reclaimed_state["units"][0]["attempt_id"] = "loop-R4-a1"
    state.write_text(json.dumps(reclaimed_state), encoding="utf-8")

    code = enforce_record_fencing(state, reclaimed_state, "R4", "loop-R4-a0",
                                   json.dumps({"status": "complete"}))
    assert code == 5  # stale_attempt — the OLD runner's report is rejected


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
