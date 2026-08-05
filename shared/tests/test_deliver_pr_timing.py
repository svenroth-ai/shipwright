"""``deliver()``'s opt-in timing instrumentation (record_timing=True).

Default (record_timing=False, every existing caller) touches no filesystem —
pinned by the untouched existing test suite. This file pins the OPT-IN path:
when a real CLI invocation enables it, delivery_wait/ci_wait spans land in
the run's own sidecar under project_root, using a real tmp_path (never a
hardcoded host path).
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))
sys.path.append(str(Path(__file__).resolve().parent))

import tools.deliver_pr as deliver_pr_mod  # noqa: E402
from tools.deliver_pr import deliver  # noqa: E402
from lib import iterate_timings as it  # noqa: E402
from lib import iterate_timings_normalize as itn  # noqa: E402

from _pr_delivery_fakes import (  # noqa: E402
    BASE, HEAD, PROTECTED_REFUSAL, REPO, SHA, _Host, _Proc, _open_pr, _ready, _watcher,
)

PR = "https://github.com/o/r/pull/7"
RUN = "iterate-2026-08-04-iterate-timing-attribution"


def test_record_timing_off_by_default_writes_nothing(tmp_path):
    host = _Host(arm=_Proc(0))
    deliver(PR, project_root=tmp_path, run_id=RUN, head_branch=HEAD, base_branch=BASE,
           repo=REPO, env={}, host=host, watch=_watcher({"status": "merged"}))
    assert not (tmp_path / ".shipwright").exists()


def test_record_timing_on_records_delivery_wait_and_ci_wait(tmp_path):
    # deliver() self-records its own "delivery" top-level span too — no
    # agent mark needed beforehand; this call is fully self-sufficient.
    host = _Host(arm=_Proc(0))
    result = deliver(PR, project_root=tmp_path, run_id=RUN, head_branch=HEAD,
                     base_branch=BASE, repo=REPO, env={}, host=host,
                     watch=_watcher({"status": "merged", "checks_observed": 3}),
                     record_timing=True)
    assert result["status"] == "merged"

    raw = itn.read_raw_events(tmp_path, RUN)
    names = {r["name"] for r in raw}
    assert names == {"delivery", "delivery_wait", "ci_wait"}
    valid, rejected = itn.normalize_iterate_timings(raw)
    assert not rejected
    ci_wait = next(v for v in valid if v["name"] == "ci_wait")
    assert ci_wait["extra"]["rung"] == "host_watch"
    assert ci_wait["extra"]["checks_observed"] == 3
    delivery_wait = next(v for v in valid if v["name"] == "delivery_wait")
    assert delivery_wait["parent"] == "delivery"
    delivery = next(v for v in valid if v["name"] == "delivery")
    assert delivery["source"] == "producer"


def test_bool_checks_observed_does_not_break_the_whole_ci_wait_span(tmp_path):
    """External code review: bool is an int subclass in Python, so an
    unguarded isinstance(x, int) check let checks_observed=True through into
    extra — the closed-vocabulary validator then rejects bool for an
    int-only field, and (before this fix) that exception, caught by span()'s
    broad guard, silently dropped the ENTIRE ci_wait span, not just the one
    field."""
    host = _Host(arm=_Proc(0))
    result = deliver(PR, project_root=tmp_path, run_id=RUN, head_branch=HEAD,
                     base_branch=BASE, repo=REPO, env={}, host=host,
                     watch=_watcher({"status": "merged", "checks_observed": True}),
                     record_timing=True)
    assert result["status"] == "merged"

    raw = itn.read_raw_events(tmp_path, RUN)
    names = {r["name"] for r in raw}
    assert "ci_wait" in names  # the span itself must still be recorded
    valid, rejected = itn.normalize_iterate_timings(raw)
    assert not rejected
    ci_wait = next(v for v in valid if v["name"] == "ci_wait")
    assert "checks_observed" not in ci_wait["extra"]  # the bad field is dropped, not the span


def test_a_redundant_agent_delivery_mark_does_not_break_self_recording(tmp_path):
    """If the SKILL marks "delivery" anyway (belt-and-suspenders), the two
    top-level instances must not conflict — deliver()'s own children still
    attach correctly to the tightest-fitting (its own, producer-recorded) one."""
    it.record_start(tmp_path, RUN, name="delivery", parent=None)
    host = _Host(arm=_Proc(0))
    deliver(PR, project_root=tmp_path, run_id=RUN, head_branch=HEAD, base_branch=BASE,
           repo=REPO, env={}, host=host, watch=_watcher({"status": "merged"}),
           record_timing=True)
    valid, rejected = itn.normalize_iterate_timings(itn.read_raw_events(tmp_path, RUN))
    assert not rejected
    delivery_wait = next(v for v in valid if v["name"] == "delivery_wait")
    assert delivery_wait["parent"] == "delivery"


def test_main_always_passes_record_timing_true(tmp_path, monkeypatch):
    """The real CLI path (what the SKILL actually invokes at F11) must opt
    in — a caller cannot forget this wiring since it isn't a flag at all."""
    captured = {}

    def _fake_deliver(*args, **kwargs):
        captured.update(kwargs)
        return {"status": "merged", "exit_code": 0}

    monkeypatch.setattr(deliver_pr_mod, "deliver", _fake_deliver)
    rc = deliver_pr_mod.main([
        "--pr", PR, "--repo", REPO, "--project-root", str(tmp_path), "--run-id", RUN,
        "--head-branch", HEAD, "--base-branch", BASE,
    ])
    assert rc == 0
    assert captured["record_timing"] is True


def test_self_merge_with_multiple_internal_polls_records_exactly_one_ci_wait(tmp_path):
    """Code review finding: `watch` used to be wrapped BEFORE the ladder chose
    a rung, so self_merge()'s own internal retry loop (rung 3) each recorded
    its own ci_wait AND the outer self-merge call recorded another — up to 4
    overlapping, mislabeled spans for one delivery. The fix: `watch` reaches
    self_merge() unwrapped; only the single outer span (rung="self_merge")
    is recorded, regardless of how many times self_merge() polls internally."""
    host = _Host(arm=_Proc(1, stderr=PROTECTED_REFUSAL),
                capability={"allow_auto_merge": True, "base_protected": False},
                pr_views=[_open_pr(oid="z" * 40), _open_pr(oid=SHA), {"state": "MERGED"}],
                sha=SHA)
    result = deliver(PR, project_root=tmp_path, run_id=RUN, head_branch=HEAD,
                     base_branch=BASE, repo=REPO, env={}, host=host,
                     # two internal polls: head moved once, then matched (mirrors
                     # test_a_head_that_moved_restarts_the_wait_instead_of_merging).
                     watch=_watcher(_ready(), _ready()),
                     record_timing=True)
    assert result["status"] == "merged" and result["merged_by"] == "shipwright"

    valid, rejected = itn.normalize_iterate_timings(itn.read_raw_events(tmp_path, RUN))
    assert not rejected
    ci_waits = [v for v in valid if v["name"] == "ci_wait"]
    assert len(ci_waits) == 1
    assert ci_waits[0]["extra"]["rung"] == "self_merge"
