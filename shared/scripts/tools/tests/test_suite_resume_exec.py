"""`suite_resume` execution + persistence - the narrow attempt, reuse, and the saved state.

A fake pytest (`_ops`) stands in for `_exec`; the real one is `test_f0_resume_real_pytest`.
"""

from __future__ import annotations

import json
import sys
import threading
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

import scripts.tools.run_test_suite as runner  # noqa: E402
import scripts.tools.suite_resume as rs  # noqa: E402
import scripts.tools.suite_resume_state as st  # noqa: E402
from scripts.tools.tests._resume_fixtures import (  # noqa: E402,F401  (fixtures are injected by name)
    RED, _git, _junit, _prepare, _saved,
)
from scripts.tools.suite_failed_only import LASTFAILED  # noqa: E402
from scripts.tools.suite_units import PASS, TEST_FAILURE, Unit  # noqa: E402


# --------------------------------------------------------------- execution

def _ctx(repo, unit, tmp_path, **kw):
    _saved(repo, unit, tmp_path, **kw)
    return _prepare(repo, unit)

pytest_plugins = ("scripts.tools.tests._resume_fixtures",)  # the `repo` / `unit` fixtures


def _ops(rc=1, rerun=("test_a", "test_b"), still_red=False, cancelled=False, calls=None):
    def exec_fn(u, root, workers, tmp_dir, timeout, cancel_event, cache_dir=None, extra_args=()):
        if calls is not None:
            calls.append({"workers": workers, "extra": extra_args, "cache": cache_dir,
                          "lf": json.loads((cache_dir / LASTFAILED).read_text())})
        _junit(tmp_dir / "r.xml", [(n, still_red) for n in rerun])
        return rc, "pytest out", 1.5, True, False, cancelled
    cleared: list = []
    return rs.ResumeOps(exec_fn, cleared.append, runner.classify), cleared


def test_a_trusted_narrow_attempt_leaves_the_whole_units_report(repo, unit, tmp_path):
    ctx = _ctx(repo, unit, tmp_path)
    calls: list = []
    ops, cleared = _ops(rc=0, calls=calls)

    got = rs.try_resume(ctx, unit, repo, tmp_path / "a", ops, timeout=9,
                        cancel_event=threading.Event())

    assert got[0] == 0 and cleared == []
    assert calls[0]["workers"] is None and "--lf" in calls[0]["extra"]
    assert "--cov-append" in calls[0]["extra"] and sorted(calls[0]["lf"]) == sorted(RED)
    report = (tmp_path / "a" / "r.xml").read_text()
    assert report.count("<testcase") == 3 and "<failure" not in report  # test_ok kept, reds replaced
    assert ctx.used == {"p"} and ctx.reran["p"] == list(RED) and ctx.label("p") == "failed-only"


def test_a_still_red_narrow_attempt_is_honest_and_still_used(repo, unit, tmp_path):
    ctx = _ctx(repo, unit, tmp_path)
    ops, _ = _ops(rc=1, still_red=True)
    got = rs.try_resume(ctx, unit, repo, tmp_path / "a", ops, timeout=9,
                        cancel_event=threading.Event())
    assert got[0] == 1 and "p" in ctx.used
    assert (tmp_path / "a" / "r.xml").read_text().count("<failure") == 2


@pytest.mark.parametrize("rc, rerun", [(5, ()), (0, ("test_a",)), (0, ("test_a", "test_b", "test_c")),
                                    (0, ("test_a", "test_z"))])  # equal COUNT, other identity
def test_an_untrusted_narrow_attempt_falls_back_to_a_full_run(repo, unit, tmp_path, rc, rerun):
    ctx = _ctx(repo, unit, tmp_path)
    ops, cleared = _ops(rc=rc, rerun=rerun)
    attempt = tmp_path / "a"

    assert rs.try_resume(ctx, unit, repo, attempt, ops, timeout=9,
                         cancel_event=threading.Event()) is None

    assert cleared == [unit] and not (attempt / "r.xml").exists() and not (attempt / "c").exists()
    assert "p" not in ctx.used and "did not describe the unit" in ctx.notes["p"]


def test_an_unmergeable_report_falls_back(repo, unit, tmp_path, monkeypatch):
    ctx = _ctx(repo, unit, tmp_path)
    monkeypatch.setattr(rs, "merge_junit", lambda *a: False)
    ops, cleared = _ops(rc=0)
    assert rs.try_resume(ctx, unit, repo, tmp_path / "a", ops, timeout=9,
                         cancel_event=threading.Event()) is None and cleared


def test_cancellation_returns_the_attempt_without_claiming_a_resume(repo, unit, tmp_path):
    ctx = _ctx(repo, unit, tmp_path)
    ops, cleared = _ops(rc=130, cancelled=True)
    got = rs.try_resume(ctx, unit, repo, tmp_path / "a", ops, timeout=9,
                        cancel_event=threading.Event())
    assert got[5] is True and not ctx.used and cleared == []


def test_a_green_unit_is_reused_without_running_anything(repo, unit, tmp_path):
    ctx = _ctx(repo, unit, tmp_path, outcome=PASS, lastfailed=None)
    ops, _ = _ops()
    ops = rs.ResumeOps(lambda *a, **k: pytest.fail("a reused unit must not run"),
                       ops.clear_cov_fn, ops.classify_fn)
    got = rs.try_resume(ctx, unit, repo, tmp_path / "a", ops, timeout=9,
                        cancel_event=threading.Event())
    assert got[0] == 0 and (tmp_path / "a" / "r.xml").is_file() and ctx.used == {"p"}


def test_a_unit_without_a_plan_is_not_touched(repo, unit):
    ctx = _prepare(repo, unit)
    assert rs.try_resume(ctx, unit, repo, repo / "a", _ops()[0], timeout=1,
                         cancel_event=threading.Event()) is None


# --------------------------------------------------------------- persistence

class _Retention:
    def __init__(self, report): self.report = report
    def pending_report(self, _unit_id): return self.report


def _res(outcome, cache_dir=None, unit_id="p"):
    return types.SimpleNamespace(unit_id=unit_id, outcome=outcome, cache_dir=cache_dir,
                                 evidence_error=None)


def test_a_green_run_spends_the_token(repo, unit, tmp_path):
    ctx = _ctx(repo, unit, tmp_path)
    rs.persist(ctx, repo, "run", [unit], [_res(PASS)], _Retention(None))
    assert st.load_state(repo) == (None, st.NO_STATE)


def test_a_green_run_spends_the_token_even_without_a_snapshot(repo, unit, tmp_path):
    _saved(repo, unit, tmp_path)
    assert st.load_state(repo)[0] is not None
    rs.persist(rs.ResumeContext(), repo, "run", [unit], [_res(PASS)], None)
    assert st.load_state(repo) == (None, st.NO_STATE)


def test_a_green_run_with_an_evidence_error_keeps_the_token(repo, unit, tmp_path):
    ctx = _ctx(repo, unit, tmp_path)
    res = _res(PASS)
    res.evidence_error = "retention failed"
    rs.persist(ctx, repo, "run", [unit], [res], _Retention(None))
    assert st.load_state(repo)[0] is not None


def test_a_red_run_saves_the_ids_its_cache_and_report_agree_on(repo, unit, tmp_path):
    ctx = _prepare(repo, unit)  # nothing saved yet: a plain first run
    cache = tmp_path / "c"
    (cache / LASTFAILED).parent.mkdir(parents=True)
    (cache / LASTFAILED).write_text(json.dumps({"a.py::test_a": True}))
    report = tmp_path / "final.xml"
    _junit(report, [("test_a", True), ("test_ok", False)])
    (repo / ".cov-data").mkdir(exist_ok=True)
    Path(unit.cov_file).write_bytes(b"cov")

    rs.persist(ctx, repo, "run", [unit], [_res(TEST_FAILURE, str(cache))], _Retention(report))

    state, why = st.load_state(repo)
    rec = state.manifest["units"]["p"]
    assert why == "" and rec["lastfailed"] == ["a.py::test_a"] and rec["outcome"] == TEST_FAILURE
    assert rec["reuses"] == 0 and rec["cov"] and state.manifest["chain"] == []


def test_ids_that_disagree_with_the_report_are_not_saved(repo, unit, tmp_path):
    ctx = _prepare(repo, unit)
    cache = tmp_path / "c"
    (cache / LASTFAILED).parent.mkdir(parents=True)
    (cache / LASTFAILED).write_text(json.dumps({"a::t1": True, "a::t2": True}))
    report = tmp_path / "final.xml"
    _junit(report, [("t1", True), ("ok", False)])  # 1 red testcase vs 2 cached ids
    rs.persist(ctx, repo, "run", [unit], [_res(TEST_FAILURE, str(cache))], _Retention(report))
    assert st.load_state(repo)[0].manifest["units"]["p"]["lastfailed"] is None


def test_the_chain_and_reuse_count_advance_on_a_resumed_run(repo, unit, tmp_path):
    ctx = _ctx(repo, unit, tmp_path, outcome=PASS, lastfailed=None, reuses=1)
    ctx.used.add("p")
    other = Unit(id="q", cwd="plugins/p", target="tests")
    rs.persist(ctx, repo, "run", [unit, other], [_res(PASS), _res(TEST_FAILURE, None, "q")],
               _Retention(None))
    state, _ = st.load_state(repo)
    assert state.manifest["chain"] == ["r@0", "r@1"]
    assert state.manifest["units"]["p"]["reuses"] == 2
    assert state.manifest["units"]["q"]["lastfailed"] is None


def test_persistence_never_raises_and_skips_without_a_snapshot(repo, unit, monkeypatch, tmp_path):
    ctx = rs.ResumeContext()  # no snapshot
    rs.persist(ctx, repo, "run", [unit], [_res(TEST_FAILURE)], _Retention(None))
    ctx = _prepare(repo, unit)
    monkeypatch.setattr(rs, "save_state", lambda *a, **k: 1 / 0)
    rs.persist(ctx, repo, "run", [unit], [_res(TEST_FAILURE)], _Retention(None))
    assert st.load_state(repo) == (None, st.NO_STATE)
    rs.persist(ctx, repo, "run", [unit], [_res(TEST_FAILURE)], None)


def test_a_red_run_that_cannot_save_spends_the_superseded_token(repo, unit, tmp_path, monkeypatch):
    ctx = _ctx(repo, unit, tmp_path)
    assert st.load_state(repo)[0] is not None
    monkeypatch.setattr(rs, "save_state", lambda *a, **k: False)
    rs.persist(ctx, repo, "r", [unit], [_res(TEST_FAILURE)], _Retention(None))
    assert st.load_state(repo) == (None, st.NO_STATE)
