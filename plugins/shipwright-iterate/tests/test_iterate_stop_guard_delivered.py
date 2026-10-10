"""Stop-guard: a run whose PR is already MERGED is released although its pointer is still live."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "shared" / "scripts"))

from _stop_guard_helpers import RUN  # noqa: E402
from lib import iterate_stop_guard as guard  # noqa: E402

pytestmark = pytest.mark.covers("FR-01.11/AC43")

STARTED = "2026-10-09T10:00:00Z"
AFTER = "2026-10-09T11:00:00Z"
BEFORE = "2026-10-01T11:00:00Z"


def _decide(tmp_path: Path, branch: str = "iterate/demo", started: str = STARTED) -> str | None:
    return guard.decide(main_root=tmp_path, run_id=RUN, worktree=tmp_path, branch=branch,
                        autonomous=True, tool_count=5, run_started=started)


def _prs(monkeypatch, prs: list[dict], calls: list | None = None) -> None:
    monkeypatch.setattr(guard, "_gh_prs", lambda wt, br: (calls.append(br) if calls is not None else 0) or prs)


def test_a_merged_pr_releases_the_guard_and_stays_released(tmp_path: Path, monkeypatch) -> None:
    calls: list[str] = []
    _prs(monkeypatch, [{"state": "MERGED", "mergedAt": AFTER}], calls)
    assert _decide(tmp_path) is None
    assert guard.read_state(tmp_path, RUN)["delivered"] is True
    assert _decide(tmp_path) is None  # no second gh call once recorded as delivered
    assert calls == ["iterate/demo"]


@pytest.mark.parametrize("prs", [
    [{"state": "OPEN", "mergedAt": None}],
    [{"state": "MERGED", "mergedAt": AFTER}, {"state": "OPEN", "mergedAt": None}],
    [{"state": "CLOSED", "mergedAt": None}],
    [{"state": "MERGED", "mergedAt": BEFORE}],  # an earlier run's PR on a reused branch name
    [],                                          # gh failed, or this run has no PR yet
])
def test_only_this_runs_merged_pr_releases(tmp_path: Path, monkeypatch, prs) -> None:
    _prs(monkeypatch, prs)
    assert _decide(tmp_path)
    assert not guard.read_state(tmp_path, RUN).get("delivered")


def test_an_unknown_start_or_branch_never_asks_gh(tmp_path: Path, monkeypatch) -> None:
    calls: list[str] = []
    _prs(monkeypatch, [{"state": "MERGED", "mergedAt": AFTER}], calls)
    assert _decide(tmp_path, started="")
    assert _decide(tmp_path, branch="")
    assert calls == []


def test_gh_is_asked_at_most_once_per_recheck_window(tmp_path: Path, monkeypatch) -> None:
    calls: list[str] = []
    _prs(monkeypatch, [], calls)  # no PR yet: every Stop blocks, gh is still asked rarely
    assert _decide(tmp_path) and _decide(tmp_path)
    assert len(calls) == 1
    guard.write_state(tmp_path, RUN, {**guard.read_state(tmp_path, RUN), "merged_checked_at": 0})
    assert _decide(tmp_path)
    assert len(calls) == 2


def test_a_blocker_recorded_during_the_gh_call_survives_the_release(tmp_path: Path, monkeypatch) -> None:
    def gh(wt, br):
        guard.record_hard_blocker(tmp_path, RUN, "external-outage", "arrived during gh")
        return [{"state": "MERGED", "mergedAt": AFTER}]

    monkeypatch.setattr(guard, "_gh_prs", gh)
    assert _decide(tmp_path) is None
    assert guard.read_state(tmp_path, RUN)["blocker"]["reason_code"] == "external-outage"


@pytest.mark.parametrize("outcome", ["missing", "timeout", "failed", "garbage"])
def test_gh_failure_modes_never_raise_and_never_release(tmp_path: Path, monkeypatch, outcome: str) -> None:
    monkeypatch.delenv("SHIPWRIGHT_ITERATE_STOP_GUARD_GH", raising=False)

    def run(*a, **k):
        if outcome == "missing":
            raise FileNotFoundError("gh")
        if outcome == "timeout":
            raise subprocess.TimeoutExpired("gh", 8)
        stdout = "not json" if outcome == "garbage" else '[{"state":"MERGED","mergedAt":"%s"}]' % AFTER
        return subprocess.CompletedProcess(a, 1 if outcome == "failed" else 0, stdout, "")

    monkeypatch.setattr(guard.subprocess, "run", run)
    assert guard._gh_prs(tmp_path, "iterate/demo") == []
    assert _decide(tmp_path)  # still blocked


def test_the_env_switch_skips_gh_entirely(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SHIPWRIGHT_ITERATE_STOP_GUARD_GH", "0")

    def boom(*a, **k):
        raise AssertionError("gh must not run")

    monkeypatch.setattr(guard.subprocess, "run", boom)
    assert guard._gh_prs(tmp_path, "iterate/demo") == []
