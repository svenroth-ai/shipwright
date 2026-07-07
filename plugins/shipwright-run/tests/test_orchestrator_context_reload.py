"""Unit tests for the single-session orchestrator CONTEXT reload + guard (SS4).

Pins the SS4 AC3 contract — the master reloads pipeline state from
``shipwright_run_config.json`` + the compact ``phase_tasks[].result`` summaries,
NEVER from a transcript — and the on-disk PERSISTENCE GUARD (AC1/AC4):

  * reload returns None when there is no config;
  * phase_summaries carries the compact fields and NEVER a transcript;
  * the context budget is O(N x MAX_SUMMARY_CHARS) and transcript-blind;
  * verify_artifacts_exist catches a claimed-but-unwritten artifact.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "lib"))

from single_session.orchestrator_context import (  # noqa: E402
    MAX_SUMMARY_CHARS,
    context_budget_chars,
    phase_summaries,
    reload_orchestrator_context,
    verify_artifacts_exist,
)
from single_session.result_contract import (  # noqa: E402
    ResultContractError,
    build_phase_runner_result,
)


def _config_with(tasks: list[dict], **top) -> dict:
    base = {"schemaVersion": 2, "runId": "run-x", "status": "in_progress",
            "mode": "single_session", "phase_tasks": tasks}
    base.update(top)
    return base


def _done_task(phase: str, *, summary: str, artifacts: list[str], transcript: str = "") -> dict:
    """A completed phase_tasks[] entry — with a spurious huge 'transcript' field
    to prove the reload never copies it through."""
    task = {
        "phaseTaskId": f"pt-{phase}",
        "phase": phase,
        "splitId": None,
        "status": "done",
        "result": {"ok": True, "phase": phase, "summary": summary, "artifacts": artifacts},
    }
    if transcript:
        task["transcript"] = transcript  # never a real field — guard bait
    return task


# --------------------------------------------------------------------------- #
# reload — read-only, None when absent
# --------------------------------------------------------------------------- #

def test_reload_none_when_no_config(tmp_project):
    assert reload_orchestrator_context(tmp_project) is None


def test_reload_none_on_corrupt_config(tmp_project):
    # A half-written / hand-corrupted config must not crash a resuming master.
    (tmp_project / "shipwright_run_config.json").write_text("{not json", encoding="utf-8")
    assert reload_orchestrator_context(tmp_project) is None


def test_reload_none_on_non_v2_schema(tmp_project):
    cfg = {"schemaVersion": 1, "runId": "legacy", "phase_tasks": []}
    (tmp_project / "shipwright_run_config.json").write_text(json.dumps(cfg), encoding="utf-8")
    assert reload_orchestrator_context(tmp_project) is None


def test_reload_returns_compact_context(tmp_project):
    cfg = _config_with(
        [_done_task("project", summary="seed done", artifacts=["artifacts/project.md"])],
        splits_frozen=["01-core"],
    )
    (tmp_project / "shipwright_run_config.json").write_text(json.dumps(cfg), encoding="utf-8")

    ctx = reload_orchestrator_context(tmp_project)
    assert ctx is not None
    assert ctx["runId"] == "run-x"
    assert ctx["status"] == "in_progress"
    assert ctx["mode"] == "single_session"
    assert ctx["splitsFrozen"] == ["01-core"]
    assert ctx["summaryCharCeiling"] == MAX_SUMMARY_CHARS
    assert [s["phase"] for s in ctx["phaseSummaries"]] == ["project"]
    assert ctx["phaseSummaries"][0]["summary"] == "seed done"
    assert ctx["phaseSummaries"][0]["artifacts"] == ["artifacts/project.md"]


def test_reload_does_not_mutate_config(tmp_project):
    cfg = _config_with([_done_task("project", summary="s", artifacts=[])])
    rc = tmp_project / "shipwright_run_config.json"
    rc.write_text(json.dumps(cfg), encoding="utf-8")
    before = rc.read_bytes()
    reload_orchestrator_context(tmp_project)
    assert rc.read_bytes() == before


# --------------------------------------------------------------------------- #
# phase_summaries — compact, transcript-blind
# --------------------------------------------------------------------------- #

def test_phase_summaries_never_carry_transcript():
    huge = "x" * 500_000
    cfg = _config_with([
        _done_task("project", summary="p", artifacts=["a.md"], transcript=huge),
    ])
    recs = phase_summaries(cfg)
    assert recs[0]["summary"] == "p"
    assert "transcript" not in recs[0]
    # Nothing transcript-sized leaks into any field of the compact record.
    assert all(len(str(v)) < 1000 for v in recs[0].values())


def test_phase_summaries_pending_task_has_null_summary():
    cfg = _config_with([{"phaseTaskId": "pt1", "phase": "design", "splitId": None,
                         "status": "awaiting_launch", "result": None}])
    rec = phase_summaries(cfg)[0]
    assert rec["summary"] is None
    assert rec["artifacts"] == []
    assert rec["ok"] is None


def test_phase_summaries_carries_failure_reason():
    cfg = _config_with([{"phaseTaskId": "pt1", "phase": "plan", "splitId": None,
                         "status": "failed",
                         "result": {"ok": False, "phase": "plan", "summary": "boom",
                                    "artifacts": [], "reason": "blew up"}}])
    rec = phase_summaries(cfg)[0]
    assert rec["ok"] is False
    assert rec["reason"] == "blew up"


# --------------------------------------------------------------------------- #
# context-budget guard — O(N x MAX_SUMMARY_CHARS), transcript-blind
# --------------------------------------------------------------------------- #

def test_context_budget_is_bounded_by_summary_ceiling(tmp_project):
    at_ceiling = "y" * MAX_SUMMARY_CHARS
    huge = "z" * 1_000_000
    tasks = [
        _done_task(p, summary=at_ceiling, artifacts=[f"artifacts/{p}.md"], transcript=huge)
        for p in ("project", "design", "plan")
    ]
    (tmp_project / "shipwright_run_config.json").write_text(
        json.dumps(_config_with(tasks)), encoding="utf-8",
    )
    ctx = reload_orchestrator_context(tmp_project)
    # Budget counts ONLY summaries and is bounded even though a 1MB transcript
    # sits next to each result on disk — the reload never reads it.
    assert ctx["summaryCharBudget"] == 3 * MAX_SUMMARY_CHARS
    assert ctx["summaryCharBudget"] <= len(tasks) * MAX_SUMMARY_CHARS


def test_context_budget_chars_empty():
    assert context_budget_chars([]) == 0


def test_context_budget_ceiling_enforced_at_write_time():
    """AC3 guard: the summary ceiling is enforced when the result is BUILT (the
    contract raises), not at reload — that is WHERE the context-budget guard
    lives, so an overlong summary can never be persisted in the first place."""
    over = "q" * (MAX_SUMMARY_CHARS + 1)
    with pytest.raises(ResultContractError):
        build_phase_runner_result(ok=True, phase="plan", summary=over, artifacts=[])


def test_reload_is_read_only_and_surfaces_overlong_summary(tmp_project):
    """Defense-in-depth: if a broken writer bypassed the contract and persisted an
    overlong summary, reload reports it verbatim (read-only, never silently caps)
    and the budget exceeds the ceiling — surfacing the upstream bypass, not hiding it."""
    over = "q" * (MAX_SUMMARY_CHARS + 10)
    cfg = _config_with([_done_task("plan", summary=over, artifacts=[])])
    (tmp_project / "shipwright_run_config.json").write_text(json.dumps(cfg), encoding="utf-8")
    ctx = reload_orchestrator_context(tmp_project)
    assert ctx["summaryCharBudget"] == len(over)
    assert ctx["summaryCharBudget"] > MAX_SUMMARY_CHARS


# --------------------------------------------------------------------------- #
# on-disk persistence guard — verify_artifacts_exist
# --------------------------------------------------------------------------- #

def test_verify_artifacts_all_present(tmp_project):
    (tmp_project / "artifacts").mkdir()
    (tmp_project / "artifacts" / "plan.md").write_text("x", encoding="utf-8")
    assert verify_artifacts_exist(tmp_project, ["artifacts/plan.md"]) == []


def test_verify_artifacts_reports_missing(tmp_project):
    (tmp_project / "artifacts").mkdir()
    (tmp_project / "artifacts" / "present.md").write_text("x", encoding="utf-8")
    missing = verify_artifacts_exist(
        tmp_project, ["artifacts/present.md", "artifacts/ghost.md"],
    )
    assert missing == ["artifacts/ghost.md"]


def test_verify_artifacts_empty_list_is_ok(tmp_project):
    assert verify_artifacts_exist(tmp_project, []) == []


def test_verify_artifacts_rejects_non_string_or_blank_entry(tmp_project):
    # A malformed artifacts entry (non-str / blank) is reported missing, never
    # silently skipped — it cannot correspond to a persisted file.
    assert verify_artifacts_exist(tmp_project, [123, "   "]) == ["123", "   "]
