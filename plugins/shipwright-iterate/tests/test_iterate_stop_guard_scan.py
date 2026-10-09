"""Stop-guard: transcript scanning, flag parsing, state handling and the next-phase hint."""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "shared" / "scripts"))

from _stop_guard_helpers import (  # noqa: E402
    BLOCKER_TOOL, CMD, REPO_ROOT, RUN, _run_hook, _seed, _transcript,
)
from lib import iterate_stop_guard as guard  # noqa: E402

pytestmark = pytest.mark.covers("FR-01.11/AC43")


def test_real_transcript_shape_and_list_content_are_read(tmp_path: Path) -> None:
    real = ("<command-message>shipwright-iterate:iterate</command-message>\n"
            "<command-name>/shipwright-iterate:iterate</command-name>\n"
            "<command-args>--autonomous Found in a smoke run</command-args>")
    path = tmp_path / "real.jsonl"
    path.write_text(json.dumps({"type": "user", "message": {"content": real}}) + "\n", encoding="utf-8")
    assert guard.scan_transcript(str(path))[0] is True
    path.write_text(json.dumps({"type": "user", "message": {"content": [{"type": "text", "text": real}]}})
                    + "\n", encoding="utf-8")
    assert guard.scan_transcript(str(path))[0] is True  # WebUI / SDK style list content


def test_flag_inside_a_description_and_campaign_parents_are_not_autonomous(tmp_path: Path) -> None:
    def one(args: str) -> bool:
        path = tmp_path / "x.jsonl"
        path.write_text(json.dumps({"type": "user", "message": {"content": CMD.format(args=args)}})
                        + "\n", encoding="utf-8")
        return guard.scan_transcript(str(path))[0]

    assert one("make --autonomous stricter") is False
    assert one("--type bug --autonomous fix it") is True
    assert one("--campaign c1 --autonomous") is False


def test_incremental_scan_resumes_and_survives_a_shrunk_file(tmp_path: Path) -> None:
    path = _transcript(tmp_path, tools=2)
    auto, tools, offset, _ = guard.scan_transcript(str(path))
    assert (auto, tools) == (True, 2) and offset == path.stat().st_size
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"type": "assistant", "message": {"content": [
            {"type": "tool_use", "name": "Bash", "input": {}}]}}) + "\n")
    state = {"autonomous": auto, "tools": tools, "offset": offset}
    assert guard.scan_transcript(str(path), state)[:2] == (True, 3)
    path.write_text("", encoding="utf-8")  # rewritten / resumed
    assert guard.scan_transcript(str(path), state)[:2] == (False, 0)


def test_blocker_cli_refuses_a_run_without_a_live_pointer(tmp_path: Path) -> None:
    main, _ = _seed(tmp_path)
    bad = subprocess.run(
        [sys.executable, str(BLOCKER_TOOL), "--project-root", str(main), "--run-id", "iterate-typo",
         "--reason-code", "external-outage", "--detail", "x"], capture_output=True, text=True, check=False)
    assert bad.returncode == 2


def test_flag_parser_uses_real_arity_and_a_trailing_flag() -> None:
    assert guard.parse_flags("fix the login bug --autonomous") == (True, False)
    assert guard.parse_flags('--title "a b" --autonomous x') == (False, False)  # unknown flag ends the flags
    assert guard.parse_flags("--autonomous improve --campaign handling") == (True, False)
    assert guard.parse_flags("--campaign c1 --autonomous") == (True, True)
    assert guard.parse_flags("--autonomous-only fix") == (False, False)
    assert guard.parse_flags("--type=bug --autonomous") == (True, False)


def test_skill_call_args_follow_the_same_rules(tmp_path: Path) -> None:
    def one(args: str) -> bool:
        path = tmp_path / "s.jsonl"
        path.write_text(json.dumps({"type": "assistant", "message": {"content": [{
            "type": "tool_use", "name": "Skill",
            "input": {"skill": "shipwright-iterate:shipwright-iterate", "args": args}}]}}) + "\n",
            encoding="utf-8")
        return guard.scan_transcript(str(path)).autonomous

    assert one("make --autonomous stricter") is False
    assert one("--autonomous improve --campaign handling") is True
    assert one("--campaign c1 --autonomous") is False


def test_half_written_last_line_is_not_consumed(tmp_path: Path) -> None:
    path = _transcript(tmp_path, tools=1)
    whole = path.stat().st_size
    with open(path, "a", encoding="utf-8") as fh:
        fh.write('{"type": "assistant", "message": {"content": [{"type": "tool_')  # no newline yet
    scan = guard.scan_transcript(str(path))
    assert scan.offset == whole and scan.tools == 1


def test_scan_state_is_saved_on_stops_that_are_let_through(tmp_path: Path) -> None:
    scan = {"autonomous": False, "tools": 7, "offset": 99, "path": "t.jsonl", "reset": False}
    assert guard.decide(main_root=tmp_path, run_id=RUN, worktree=tmp_path, branch="b",
                        autonomous=False, tool_count=7, scan=scan) is None
    saved = guard.read_state(tmp_path, RUN)
    assert saved["offset"] == 99 and saved["tools"] == 7


def test_a_rewritten_transcript_does_not_count_as_idleness(tmp_path: Path) -> None:
    kw = dict(main_root=tmp_path, run_id=RUN, worktree=tmp_path, branch="b", autonomous=True)
    assert guard.decide(tool_count=50, **kw)
    scan = {"autonomous": True, "tools": 3, "offset": 10, "path": "new.jsonl", "reset": True}
    assert guard.decide(tool_count=3, scan=scan, **kw)
    assert guard.read_state(tmp_path, RUN)["futile"] == 0


def test_corrupt_state_fails_open_through_the_real_hook(tmp_path: Path) -> None:
    main, _ = _seed(tmp_path)
    state_dir = main / ".shipwright" / "runtime" / "iterate-stop-guard"
    state_dir.mkdir(parents=True)
    (state_dir / f"{RUN}.json").write_text("{not json", encoding="utf-8")
    assert _run_hook(main, _transcript(tmp_path)) is None
    assert (state_dir / f"{RUN}.json").read_text(encoding="utf-8") == "{not json"  # not silently reset


def test_blocker_can_be_cleared_and_the_guard_rearms(tmp_path: Path) -> None:
    main, _ = _seed(tmp_path)
    base = [sys.executable, str(BLOCKER_TOOL), "--project-root", str(main), "--run-id", RUN]
    subprocess.run([*base, "--reason-code", "external-outage", "--detail", "x"], check=True,
                   capture_output=True)
    assert _run_hook(main, _transcript(tmp_path)) is None
    cleared = subprocess.run([*base, "--clear"], capture_output=True, text=True, check=False)
    assert cleared.returncode == 0 and json.loads(cleared.stdout)["cleared"] is True
    assert _run_hook(main, _transcript(tmp_path))["decision"] == "block"


def test_hint_reads_f6_by_run_id_then_push_then_delivery(tmp_path: Path) -> None:
    _, worktree = _seed(tmp_path)
    rec = worktree / ".shipwright" / "planning" / "iterate" / RUN
    rec.mkdir(parents=True)
    (rec / "reviews.json").write_text(json.dumps({"reviews": {"self": {"status": "completed"}}}),
                                      encoding="utf-8")
    (worktree / "shipwright_events.jsonl").write_text(
        json.dumps({"event": "work_completed", "run_id": RUN}) + "\n", encoding="utf-8")
    git = ["git", "-c", "user.email=t@t", "-c", "user.name=t", "-C", str(worktree)]
    subprocess.run([*git, "update-ref", "refs/remotes/origin/main", "main"], check=True)
    subprocess.run([*git, "commit", "--allow-empty", "-q", "-m", "chore: triage sweep"], check=True)
    assert "F6 commit is missing" in guard.next_phase_hint(worktree, RUN, "iterate/demo")  # other commit
    subprocess.run([*git, "commit", "--allow-empty", "-q", "-m", f"feat: x\n\nRun-ID: {RUN}"], check=True)
    assert "push" in guard.next_phase_hint(worktree, RUN, "iterate/demo")
    subprocess.run([*git, "update-ref", "refs/remotes/origin/iterate/demo", "HEAD"], check=True)
    assert "deliver_pr.py" in guard.next_phase_hint(worktree, RUN, "iterate/demo")


def test_the_guard_is_registered_in_the_stop_hooks_of_the_iterate_plugin() -> None:
    hooks = json.loads((REPO_ROOT / "plugins" / "shipwright-iterate" / "hooks" / "hooks.json")
                       .read_text(encoding="utf-8"))["hooks"]["Stop"]
    commands = [h["command"] for group in hooks for h in group["hooks"]]
    guard_cmd = [c for c in commands if "iterate_stop_guard.py" in c]
    assert guard_cmd == ['uv run --no-project "${CLAUDE_PLUGIN_ROOT}/scripts/hooks/iterate_stop_guard.py"']
    assert "if" not in str(hooks)  # never an `if:` filter on a Stop hook
    assert "write_terminal_marker.py" in commands[-4] or any("write_terminal_marker" in c for c in commands)


def _plant_pointer(main: Path, name: str, **fields) -> None:
    ptr = main / ".shipwright" / "iterate_active"
    ptr.mkdir(parents=True, exist_ok=True)
    (ptr / f"{name}.json").write_text(json.dumps(fields), encoding="utf-8")


def test_a_session_less_pointer_is_matched_by_the_run_id_in_the_transcript(tmp_path: Path) -> None:
    main, worktree = _seed(tmp_path)
    (main / ".shipwright" / "iterate_active" / "sess1.json").unlink()
    _plant_pointer(main, RUN, run_id=RUN, branch="iterate/demo", worktree_path=str(worktree),
                   session_id="", created_at=datetime.now(timezone.utc).isoformat())
    named = _transcript(tmp_path)
    with open(named, "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"type": "assistant", "message": {"content": [{
            "type": "tool_use", "name": "Bash", "input": {"command": f"setup --run-id {RUN}"}}]}}) + "\n")
    assert _run_hook(main, named)["decision"] == "block"
    assert _run_hook(main, _transcript(tmp_path)) is None  # transcript never names that run


def test_a_pointer_older_than_the_age_bound_is_ignored(tmp_path: Path) -> None:
    main, worktree = _seed(tmp_path)
    old = (datetime.now(timezone.utc) - timedelta(hours=guard.MAX_POINTER_AGE_HOURS + 1)).isoformat()
    _plant_pointer(main, "sess1", run_id=RUN, branch="iterate/demo", worktree_path=str(worktree),
                   session_id="sess1", created_at=old)
    assert _run_hook(main, _transcript(tmp_path)) is None


def test_only_the_iterate_skill_names_change_autonomy(tmp_path: Path) -> None:
    def skill(name: str, args: str) -> dict:
        return {"type": "assistant", "message": {"content": [{
            "type": "tool_use", "name": "Skill", "input": {"skill": name, "args": args}}]}}

    path = tmp_path / "sk.jsonl"
    path.write_text(json.dumps(skill("shipwright-iterate:shipwright-iterate", "--autonomous x"))
                    + "\n" + json.dumps(skill("iterate-review", "just look")) + "\n", encoding="utf-8")
    assert guard.scan_transcript(str(path)).autonomous is True


def test_a_blocker_recorded_during_a_stop_is_not_overwritten(tmp_path: Path, monkeypatch) -> None:
    kw = dict(main_root=tmp_path, run_id=RUN, worktree=tmp_path, branch="b", autonomous=True)
    guard.write_state(tmp_path, RUN, {})
    original = guard.read_state
    calls = {"n": 0}

    def read_then_race(*a, **k):
        calls["n"] += 1
        if calls["n"] == 2:  # between decide's first read and its final write
            guard.record_hard_blocker(tmp_path, RUN, "external-outage", "arrived mid-Stop")
        return original(*a, **k)

    monkeypatch.setattr(guard, "read_state", read_then_race)
    guard.decide(tool_count=4, **kw)
    assert original(tmp_path, RUN).get("blocker", {}).get("reason_code") == "external-outage"
