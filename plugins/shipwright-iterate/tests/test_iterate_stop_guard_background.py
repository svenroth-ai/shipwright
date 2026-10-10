"""Stop-guard: no block while a background reviewer / shell is still running."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "shared" / "scripts"))

from _stop_guard_helpers import RUN, _run_hook, _seed, _transcript  # noqa: E402
from lib import iterate_stop_guard as guard  # noqa: E402
from lib import iterate_stop_guard_background as bg  # noqa: E402

pytestmark = pytest.mark.covers("FR-01.11/AC43")

NOW = datetime(2026, 10, 10, 8, 0, tzinfo=timezone.utc)


AGENT = {"isAsync": True, "agentId": "a1", "status": "async_launched"}
SHELL = {"backgroundTaskId": "b1", "interrupted": False}


def _launch(tid: str, result: object = AGENT, when: datetime | None = NOW, text: str = "launched") -> str:
    entry = {"type": "user", "toolUseResult": result, "message": {"content": [
        {"type": "tool_result", "tool_use_id": tid, "content": [{"type": "text", "text": text}]}]}}
    if when is not None:
        entry["timestamp"] = when.isoformat()
    return json.dumps(entry)


def _done(*ids: str, status: str = "completed") -> str:
    body = "".join(f"<task-notification>\n<tool-use-id>{t}</tool-use-id>\n<status>{status}</status>\n"
                   "</task-notification>\n" for t in ids)
    return json.dumps({"type": "queue-operation", "operation": "enqueue", "content": body})


def test_a_launch_is_pending_until_its_terminal_notification() -> None:
    pending: dict = {}
    bg.track(pending, _launch("t1"))
    bg.track(pending, _launch("t3", SHELL))
    assert set(pending) == {"t1", "t3"} and bg.waiting(pending, NOW)
    bg.track(pending, _done("t1", "t3"))
    assert pending == {} and not bg.waiting(pending, NOW)


def test_each_id_is_paired_with_its_own_status() -> None:
    pending: dict = {}
    bg.track(pending, _launch("t1"))
    bg.track(pending, _launch("t2"))
    body = ("<task-notification><tool-use-id>t1</tool-use-id><status>running</status></task-notification>"
            "<task-notification><tool-use-id>t2</tool-use-id><status>completed</status></task-notification>")
    bg.track(pending, json.dumps({"type": "queue-operation", "content": body}))
    assert set(pending) == {"t1"}


def test_only_a_terminal_status_finishes_a_task() -> None:
    pending: dict = {}
    bg.track(pending, _launch("t1"))
    bg.track(pending, _done("t1", status="running"))
    assert "t1" in pending


@pytest.mark.parametrize("result", [
    None,                                                    # ordinary tool result
    "Async agent launched successfully. quoted by grep",     # text only, no structured launch fields
    {"stdout": "Command running in background with ID: b2"},  # a synchronous Bash that printed the sentence
    {"taskId": "m1", "persistent": True},                    # persistent monitor: never finishes
    {"isAsync": False},
])
def test_these_results_are_not_launches(result) -> None:
    pending: dict = {}
    bg.track(pending, _launch("t9", result, text="Async agent launched successfully."))
    assert pending == {}


def test_a_non_persistent_monitor_and_a_timed_out_command_are_launches() -> None:
    pending: dict = {}
    bg.track(pending, _launch("m", {"taskId": "m1", "persistent": False, "timeoutMs": 1}))
    bg.track(pending, _launch("c", {"backgroundTaskId": "b9", "timedOutAfterMs": 120000}))
    assert set(pending) == {"m", "c"}


def test_a_notice_on_the_same_line_as_its_own_launch_wins() -> None:
    pending: dict = {}
    entry = json.loads(_launch("t1", SHELL))
    entry["message"]["content"].append({"type": "text", "text": "<task-notification><tool-use-id>t1</tool-use-id>"
                                        "<status>completed</status></task-notification>"})
    bg.track(pending, json.dumps(entry))
    assert pending == {}


def test_a_notice_quoted_in_tool_output_or_assistant_text_clears_nothing() -> None:
    notice = ("<task-notification><tool-use-id>t1</tool-use-id><status>completed</status></task-notification>")
    pending: dict = {}
    bg.track(pending, _launch("t1"))
    quoted_result = json.dumps({"type": "user", "message": {"content": [
        {"type": "tool_result", "tool_use_id": "g", "content": notice}]}})
    quoted_assistant = json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": notice}]}})
    bg.track(pending, quoted_result)
    bg.track(pending, quoted_assistant)
    assert "t1" in pending
    bg.track(pending, _done("t1"))  # the real queue entry still clears it
    assert pending == {}


def test_a_poison_transcript_line_does_not_stop_the_scan(tmp_path: Path) -> None:
    path = tmp_path / "t.jsonl"
    path.write_text('{"toolUseResult": {"isAsync": true}, "message": 5}' + chr(10) + _launch("t1") + chr(10),
                    encoding="utf-8")
    assert set(guard.scan_transcript(str(path)).background) == {"t1"}


def test_a_task_that_never_reports_stops_counting_after_its_bound() -> None:
    pending: dict = {}
    bg.track(pending, _launch("a", when=NOW))
    bg.track(pending, _launch("s", SHELL, when=NOW))
    assert bg.waiting(pending, NOW + timedelta(seconds=bg.BG_MAX_AGE_SECONDS["shell"] - 1))
    only_agent = {"a": pending["a"]}
    assert bg.waiting(only_agent, NOW + timedelta(seconds=bg.BG_MAX_AGE_SECONDS["shell"] + 1))
    assert not bg.waiting(only_agent, NOW + timedelta(seconds=bg.BG_MAX_AGE_SECONDS["agent"] + 1))
    assert not bg.waiting({"s": pending["s"]}, NOW + timedelta(seconds=bg.BG_MAX_AGE_SECONDS["shell"] + 1))


def test_a_missing_launch_timestamp_is_replaced_and_an_unreadable_one_never_silences() -> None:
    pending: dict = {}
    bg.track(pending, _launch("t1", when=None), now=NOW)
    assert pending["t1"]["ts"] == NOW.isoformat()
    assert not bg.waiting({"t1": {"ts": "garbage", "kind": "agent"}}, NOW)
    assert not bg.waiting({"t1": {"kind": "agent"}}, NOW)


def test_a_future_timestamp_does_not_extend_the_silence() -> None:
    assert not bg.waiting({"t": {"ts": "2099-01-01T00:00:00Z", "kind": "agent"}}, NOW + timedelta(hours=3))


def test_a_notice_batched_with_a_tool_result_still_clears_and_expired_entries_are_pruned() -> None:
    pending: dict = {"old": {"ts": (NOW - timedelta(hours=5)).isoformat(), "kind": "agent"}}
    bg.track(pending, _launch("t1"))
    assert set(pending) == {"t1"}  # the expired entry was dropped on the next launch
    line = json.dumps({"type": "user", "message": {"content": [
        {"type": "tool_result", "tool_use_id": "z", "content": "x"},
        {"type": "text", "text": "<task-notification><tool-use-id>t1</tool-use-id><status>completed</status></task-notification>"}]}})
    bg.track(pending, line)
    assert pending == {}


def test_a_malformed_saved_bg_value_is_ignored(tmp_path: Path) -> None:
    path = tmp_path / "t.jsonl"
    path.write_text(_launch("t1") + chr(10), encoding="utf-8")
    assert set(guard.scan_transcript(str(path), {"bg": ["junk"]}).background) == {"t1"}
    monkey = {"bg": ["junk"]}
    assert guard.decide(main_root=tmp_path, run_id=RUN, worktree=tmp_path, branch="", autonomous=True,
                        tool_count=1, scan=monkey)  # no crash, no silence


def test_the_scan_collects_pending_tasks_incrementally(tmp_path: Path) -> None:
    path = tmp_path / "t.jsonl"
    path.write_text(_launch("t1") + "\n", encoding="utf-8")
    first = guard.scan_transcript(str(path))
    assert set(first.background) == {"t1"}
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(_launch("t2") + "\n" + _done("t1") + "\n")
    second = guard.scan_transcript(str(path), {"bg": first.background, "offset": first.offset, "path": str(path)})
    assert set(second.background) == {"t2"}


def test_decide_stays_silent_while_a_background_task_runs_and_blocks_after(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(guard, "_gh_prs", lambda wt, br: [])
    kw = dict(main_root=tmp_path, run_id=RUN, worktree=tmp_path, branch="iterate/demo", autonomous=True)
    running = {"bg": {"t1": {"ts": datetime.now(timezone.utc).isoformat(), "kind": "agent"}}}
    for tools in (1, 2, 3, 4):
        assert guard.decide(tool_count=tools, scan=running, **kw) is None
    assert guard.read_state(tmp_path, RUN).get("blocks", 0) == 0
    assert guard.decide(tool_count=5, scan={"bg": {}}, **kw)  # nothing runs any more: block again


def test_a_blocker_recorded_since_the_read_survives_a_silent_stop(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(guard, "_gh_prs", lambda wt, br: [])
    real = guard.background_waiting

    def waiting(pending):
        guard.record_hard_blocker(tmp_path, RUN, "external-outage", "arrived mid-stop")
        return real(pending)

    monkeypatch.setattr(guard, "background_waiting", waiting)
    running = {"bg": {"t1": {"ts": datetime.now(timezone.utc).isoformat(), "kind": "agent"}}}
    assert guard.decide(main_root=tmp_path, run_id=RUN, worktree=tmp_path, branch="b", autonomous=True,
                        tool_count=1, scan=running) is None
    assert guard.read_state(tmp_path, RUN)["blocker"]["reason_code"] == "external-outage"


def test_an_open_pr_alone_never_silences_the_guard(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(guard, "_gh_prs", lambda wt, br: [{"state": "OPEN", "mergedAt": None}])
    kw = dict(main_root=tmp_path, run_id=RUN, worktree=tmp_path, branch="iterate/demo", autonomous=True,
              run_started="2026-10-09T10:00:00Z")
    assert guard.decide(tool_count=1, **kw)  # ends the turn otherwise: an open PR is not a reason to stop


def test_the_hook_in_a_real_worktree_is_silent_while_a_reviewer_runs(tmp_path: Path) -> None:
    main, _ = _seed(tmp_path)
    transcript = _transcript(tmp_path)
    assert _run_hook(main, transcript)["decision"] == "block"  # baseline: open run, nothing in the background
    other = tmp_path / "bgrun"
    other.mkdir()
    main2, _ = _seed(other)
    t2 = _transcript(other)
    with open(t2, "a", encoding="utf-8") as fh:
        fh.write(_launch("toolu_1", when=datetime.now(timezone.utc)) + "\n")
    assert _run_hook(main2, t2) is None
    with open(t2, "a", encoding="utf-8") as fh:
        fh.write(_done("toolu_1") + "\n")
    assert _run_hook(main2, t2)["decision"] == "block"
