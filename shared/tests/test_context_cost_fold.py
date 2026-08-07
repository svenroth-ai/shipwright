"""Tests for context_cost_core.fold_into_event and resolve_active_project_root.

Split out of test_context_cost_core.py, which had reached the 300-line
size guideline (context-cost-meter, adding external-review regression
coverage pushed it over) — same reasoning as the source-side
context_cost_session.py split: a one-way move of self-contained test
groups, no shared fixtures left behind.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(_SCRIPTS))

from lib import context_cost_core as ccc  # noqa: E402

_T0 = datetime(2026, 8, 7, 12, 0, 0, tzinfo=timezone.utc)


def _write_transcript(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in records) + "\n",
        encoding="utf-8",
    )


def _assistant_record(request_id: str, ts: datetime, model: str, usage: dict) -> dict:
    return {
        "type": "assistant",
        "requestId": request_id,
        "timestamp": ts.isoformat(),
        "message": {"model": model, "usage": usage},
    }


def test_fold_into_event_is_additive_first_write_wins():
    event = {"context_cost": {"calls": 999}}
    summary = {"calls": 1, "context_tokens": 10, "cost_usd": 0.1, "unpriced_calls": 0,
               "cost_complete": True, "by_phase": {}, "skipped_malformed": 0}
    ccc.fold_into_event(event, summary)
    assert event["context_cost"]["calls"] == 999  # unchanged, first-write-wins


def test_fold_into_event_sets_the_field_when_absent():
    event = {}
    summary = {"calls": 3, "context_tokens": 30, "cost_usd": 0.3, "unpriced_calls": 0,
               "cost_complete": True, "by_phase": {"build": {"calls": 3}}, "skipped_malformed": 0}
    ccc.fold_into_event(event, summary)
    assert event["context_cost"]["calls"] == 3
    assert event["context_cost"]["by_phase"]["build"]["calls"] == 3


def test_fold_into_event_never_raises_on_a_none_summary():
    event = {}
    ccc.fold_into_event(event, None)
    assert "context_cost" not in event


def test_fold_into_event_stamps_measured_through_and_measured_at():
    # A run's work_completed.context_cost is bounded to F0-F5b (F6-F12 —
    # commit, PR delivery, CI rework — happen after the fold), so the
    # truncation must be visible on the event itself, never silent.
    event = {}
    summary = {"calls": 5, "context_tokens": 50, "cost_usd": 0.5, "unpriced_calls": 0,
               "cost_complete": True, "by_phase": {}, "skipped_malformed": 0}
    ccc.fold_into_event(event, summary)
    assert event["context_cost"]["measured_through"] == "F5b"
    assert event["context_cost"]["calls"] == 5
    assert isinstance(event["context_cost"]["measured_at"], str) and event["context_cost"]["measured_at"]


def test_fold_into_event_carries_unpriced_models_when_present():
    # External-review finding: unpriced_models is diagnostic and additive --
    # this asserts it actually reaches the persisted event field, not just
    # the in-memory summary dict.
    event = {}
    summary = {"calls": 2, "context_tokens": 20, "cost_usd": 0.0, "unpriced_calls": 2,
               "unpriced_models": ["claude-unknown-a"], "cost_complete": False,
               "by_phase": {}, "skipped_malformed": 0}
    ccc.fold_into_event(event, summary)
    assert event["context_cost"]["unpriced_models"] == ["claude-unknown-a"]


def test_fold_into_event_defaults_unpriced_models_when_absent():
    # A summary dict missing the field entirely (defensive: must never be
    # the reason the whole fold is skipped) degrades to an empty list.
    event = {}
    summary = {"calls": 1, "context_tokens": 10, "cost_usd": 0.1, "unpriced_calls": 0,
               "cost_complete": True, "by_phase": {}, "skipped_malformed": 0}
    ccc.fold_into_event(event, summary)
    assert event["context_cost"]["unpriced_models"] == []


def test_fold_into_event_populated_case_from_a_real_computed_summary(tmp_path):
    # Regression guard for "the fold silently produces nothing": run the
    # actual Stop-hook computation end to end (real transcript -> real
    # compute_summary -> real fold), not just the graceful-absence path,
    # so a wiring break between the two can't hide behind a green suite
    # that only ever exercised the empty case.
    transcript = tmp_path / "session.jsonl"
    _write_transcript(
        transcript,
        [_assistant_record("req-1", _T0, "claude-sonnet-5", {"input_tokens": 1000})],
    )
    summary = ccc.compute_summary(transcript, tmp_path, run_id=None)
    event = {}
    ccc.fold_into_event(event, summary)
    assert event["context_cost"]["calls"] == 1
    assert event["context_cost"]["cost_usd"] > 0
    assert event["context_cost"]["measured_through"] == "F5b"


def test_resolve_active_project_root_prefers_the_pointed_worktree(
    git_origin_repo, make_worktree
):
    # Doubt-review finding: a Stop subprocess's cwd is the MAIN repo even
    # while an iterate runs in its linked worktree, and SHIPWRIGHT_PROJECT_
    # ROOT never reaches that process class -- the naive resolve_project_root()
    # therefore wrote into main while finalize_iterate.py's F5b fold reads
    # from the worktree, missing every write silently.
    from lib.worktree_isolation import write_run_pointer

    work, _origin = git_origin_repo
    wt = make_worktree(work, "context-cost-meter-doubt-check")
    write_run_pointer(
        work, run_id="iterate-doubt-check", slug="context-cost-meter-doubt-check",
        branch="iterate/context-cost-meter-doubt-check", worktree_path=wt,
        session_id="sess-active",
    )

    resolved = ccc.resolve_active_project_root(work, "sess-active")

    assert resolved == wt.resolve()


def test_resolve_active_project_root_falls_back_without_a_pointer(
    git_origin_repo, monkeypatch
):
    # No active iterate for this session -- must degrade to the normal
    # resolver (SHIPWRIGHT_PROJECT_ROOT env var) rather than raise or
    # silently pick an unrelated tree.
    work, _origin = git_origin_repo
    (work / ".shipwright" / "agent_docs").mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("SHIPWRIGHT_PROJECT_ROOT", str(work))

    resolved = ccc.resolve_active_project_root(work, "sess-with-no-pointer")

    assert resolved == work.resolve()
