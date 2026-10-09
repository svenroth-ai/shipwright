"""Stop-guard: an --autonomous iterate may not end its turn before it is delivered (decision + hook)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "shared" / "scripts"))

from _stop_guard_helpers import (  # noqa: E402
    BLOCKER_TOOL, CMD, RUN, _run_hook, _seed, _transcript,
)
from lib import iterate_stop_guard as guard  # noqa: E402

pytestmark = pytest.mark.covers("FR-01.11/AC43")


def test_autonomous_detection_reads_the_command_not_the_prose(tmp_path: Path) -> None:
    assert guard.scan_transcript(str(_transcript(tmp_path)))[0] is True
    assert guard.scan_transcript(str(_transcript(tmp_path, args="fix it")))[0] is False
    prose = tmp_path / "p.jsonl"
    prose.write_text(json.dumps({"type": "user", "message": {
        "content": "please explain --autonomous"}}) + "\n", encoding="utf-8")
    assert guard.scan_transcript(str(prose))[0] is False


def test_skill_tool_invocation_counts_as_autonomous(tmp_path: Path) -> None:
    path = tmp_path / "s.jsonl"
    path.write_text(json.dumps({"type": "assistant", "message": {"content": [{
        "type": "tool_use", "name": "Skill",
        "input": {"skill": "shipwright-iterate:shipwright-iterate", "args": "--autonomous x"},
    }]}}) + "\n", encoding="utf-8")
    assert guard.scan_transcript(str(path))[0] is True


def test_open_autonomous_run_is_blocked_with_next_phase(tmp_path: Path) -> None:
    main, _ = _seed(tmp_path)
    out = _run_hook(main, _transcript(tmp_path))
    assert out and out["decision"] == "block"
    assert RUN in out["reason"] and "self-review" in out["reason"]


def test_interactive_run_and_retired_pointer_are_never_blocked(tmp_path: Path) -> None:
    main, _ = _seed(tmp_path)
    assert _run_hook(main, _transcript(tmp_path, args="fix it")) is None
    (main / ".shipwright" / "iterate_active" / "sess1.json").unlink()  # deliver_pr retired it
    assert _run_hook(main, _transcript(tmp_path)) is None


def test_loop_unit_is_left_alone(tmp_path: Path) -> None:
    main, _ = _seed(tmp_path)
    assert _run_hook(main, _transcript(tmp_path), loop_id="loop1") is None


def test_recorded_blocker_lifts_the_guard(tmp_path: Path) -> None:
    main, _ = _seed(tmp_path)
    done = subprocess.run(
        [sys.executable, str(BLOCKER_TOOL), "--project-root", str(main), "--run-id", RUN,
         "--reason-code", "admin-merge-required", "--detail", "needs --admin"],
        capture_output=True, text=True, check=False)
    assert done.returncode == 0, done.stderr
    assert _run_hook(main, _transcript(tmp_path)) is None


def test_unknown_blocker_code_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        guard.record_hard_blocker(tmp_path, RUN, "tired", "x")


def test_prose_only_answers_run_out_but_real_work_resets(tmp_path: Path) -> None:
    kw = dict(main_root=tmp_path, run_id=RUN, worktree=tmp_path, branch="b", autonomous=True)
    # first Stop blocks (new work); then MAX_FUTILE_BLOCKS-1 prose-only blocks; the next passes
    results = [guard.decide(tool_count=5, **kw) for _ in range(guard.MAX_FUTILE_BLOCKS + 1)]
    assert all(results[:-1])  # every one of those was a block
    assert results[-1] is None  # prose-only again -> the loop is released
    assert guard.decide(tool_count=9, **kw)  # work happened -> blocked again, counter reset


def test_total_cap_releases_the_guard(tmp_path: Path) -> None:
    guard.write_state(tmp_path, RUN, {"blocks": guard.MAX_TOTAL_BLOCKS})
    assert guard.decide(main_root=tmp_path, run_id=RUN, worktree=tmp_path, branch="b",
                        autonomous=True, tool_count=99) is None


def test_hint_walks_the_phases_in_order(tmp_path: Path) -> None:
    rec = tmp_path / ".shipwright" / "planning" / "iterate" / RUN
    rec.mkdir(parents=True)
    (rec / "reviews.json").write_text(json.dumps({"reviews": {
        "self": {"status": "completed"}, "code": {"status": "pending"}}}), encoding="utf-8")
    assert "code" in guard.next_phase_hint(tmp_path, RUN, "b")
    (rec / "reviews.json").write_text(json.dumps({"reviews": {
        "self": {"status": "completed"}}}), encoding="utf-8")
    assert "work_completed" in guard.next_phase_hint(tmp_path, RUN, "b")


def test_hook_and_cli_agree_from_main_checkout_and_from_worktree(tmp_path: Path) -> None:
    main, worktree = _seed(tmp_path)
    t = _transcript(tmp_path)
    assert _run_hook(main, t, cwd=worktree)["decision"] == "block"
    done = subprocess.run(
        [sys.executable, str(BLOCKER_TOOL), "--project-root", str(worktree), "--run-id", RUN,
         "--reason-code", "abandoned-by-operator", "--detail", "operator walked away"],
        cwd=worktree, capture_output=True, text=True, check=False)
    assert done.returncode == 0, done.stderr
    assert _run_hook(main, t, cwd=main) is None  # blocker written from the worktree is honoured from main
    assert _run_hook(main, t, cwd=worktree) is None


def test_the_latest_iterate_invocation_decides(tmp_path: Path) -> None:
    lines = [json.dumps({"type": "user", "message": {"content": CMD.format(args="--autonomous a")}}),
             json.dumps({"type": "user", "message": {"content": CMD.format(args="b")}})]
    path = tmp_path / "two.jsonl"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert guard.scan_transcript(str(path))[0] is False  # interactive run came last
    path.write_text("\n".join(reversed(lines)) + "\n", encoding="utf-8")
    assert guard.scan_transcript(str(path))[0] is True


def test_a_pasted_command_line_without_the_command_tags_is_not_an_invocation(tmp_path: Path) -> None:
    path = tmp_path / "paste.jsonl"
    path.write_text(json.dumps({"type": "user", "message": {"content":
        "log: /shipwright-iterate:iterate --autonomous fix"}}) + "\n", encoding="utf-8")
    assert guard.scan_transcript(str(path))[0] is False


def test_operator_kill_switch_and_counter_boundaries(tmp_path: Path) -> None:
    main, _ = _seed(tmp_path)
    assert _run_hook(main, _transcript(tmp_path),
                     extra_env={"SHIPWRIGHT_ITERATE_STOP_GUARD": "0"}) is None
    kw = dict(main_root=tmp_path / "x", run_id=RUN, worktree=tmp_path, branch="b", autonomous=True)
    outcomes = [guard.decide(tool_count=n, **kw) for n in range(1, guard.MAX_TOTAL_BLOCKS + 2)]
    assert all(outcomes[:guard.MAX_TOTAL_BLOCKS])  # progress every time: blocked up to the cap
    assert outcomes[-1] is None  # the 41st Stop passes
