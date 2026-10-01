"""`suite_retry.retry_red_units` - failed-only retry vs the whole-unit fallback.

The runner's seams are injected, so these tests drive the retry with a fake `_exec` and
real files (the attempt's JUnit report + pytest cache) in a temp tree.
"""

from __future__ import annotations

import json
import sys
import threading
import xml.etree.ElementTree as ET
from contextlib import contextmanager
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

import scripts.tools.run_test_suite as mod
import scripts.tools.suite_retry as retry
from scripts.tools.suite_failed_only import FAILED_ONLY_ARGS, LASTFAILED, junit_failure_count
from scripts.tools.suite_units import INFRA, PASS, TEST_FAILURE, Unit

UNIT = Unit(id="plugin-a", cwd="plugins/a", target="tests", cov_args=("--cov=scripts",))
NARROW = (*FAILED_ONLY_ARGS, "--cov-append")


def _write_junit(path: Path, cases: list[tuple[str, bool]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    suite = ET.Element("testsuite")
    for name, bad in cases:
        case = ET.SubElement(suite, "testcase", classname="t", name=name)
        if bad:
            ET.SubElement(case, "failure", message="x")
    ET.ElementTree(suite).write(path, encoding="utf-8")


def _attempt(tmp_path: Path, failing: list[str], passing: list[str], *, cache: bool = True):
    attempt = tmp_path / "p" / "u0"
    _write_junit(attempt / "r.xml", [(n, True) for n in failing] + [(n, False) for n in passing])
    if cache:
        target = attempt / "c" / LASTFAILED
        target.parent.mkdir(parents=True)
        target.write_text(json.dumps({f"t.py::{n}": True for n in failing}), encoding="utf-8")


@contextmanager
def _heartbeat(active: list, **_kw):
    active.append(1)
    try:
        yield
    finally:
        active.pop()


class _Harness:
    def __init__(self, tmp_path: Path, script: list, cancel_on: int | None = None,
                 unit: Unit = UNIT):
        self.tmp_path, self.script, self.cancel_on, self.unit = tmp_path, list(script), cancel_on, unit
        self.exec_calls: list[dict] = []
        self.cleared = 0
        self.recorded: list[tuple[Path, str]] = []
        self.events: list[tuple[str, str]] = []
        self.retained: list[str] = []
        self.heartbeat: list[int] = []

    def _exec(self, unit, root, workers, tmp_dir, timeout, cancel, cache_dir=None, extra_args=()):
        self.exec_calls.append({"workers": workers, "cache_dir": cache_dir,
                                "extra_args": tuple(extra_args), "tmp_dir": tmp_dir,
                                "stale_report": (tmp_dir / "r.xml").exists(),
                                "heartbeat": bool(self.heartbeat)})
        rc, cases = self.script.pop(0)
        if cases is not None:
            _write_junit(tmp_dir / "r.xml", cases)
        cancelled = self.cancel_on == len(self.exec_calls)
        return rc, f"retry out rc={rc}", 0.5, cases is not None, False, cancelled

    def run(self, results):
        recorded = self.recorded

        class _Retention:
            def record(self, unit, report, outcome):
                recorded.append((report, outcome))

        def retain(*_a, **kw):
            self.retained.append(kw["phase"])
            return (None, None)

        ops = retry.RetryOps(
            exec_fn=self._exec, retain_fn=retain, clear_cov_fn=lambda unit: self._clear(),
            build_fn=mod.build_command, repro_fn=mod.reproduce_command,
            emit_fn=lambda stream, **kw: self.events.append((kw["event"], kw.get("retry_kind", "-"))),
            heartbeat_fn=lambda **kw: _heartbeat(self.heartbeat, **kw),
            classify_fn=mod.classify, workers_fn=lambda unit_id: 8)
        retry.retry_red_units(
            results, {self.unit.id: self.unit}, ops, project_root=self.tmp_path,
            tmp_root=self.tmp_path, timeout=60, cancel_event=threading.Event(),
            stream=None, heartbeat_seconds=1.0, run_id="r", retention=_Retention())

    def _clear(self):
        self.cleared += 1


def _red(outcome=TEST_FAILURE):
    return mod.UnitResult(UNIT.id, outcome, 1, 3.0, "first attempt out")


def test_failed_only_retry_runs_just_the_red_tests_and_appends_coverage(tmp_path):
    _attempt(tmp_path, ["bad1", "bad2"], ["ok1", "ok2"])
    h = _Harness(tmp_path, [(0, [("bad1", False), ("bad2", False)])])
    res = _red()
    h.run([res])
    call = h.exec_calls[0]
    assert call["extra_args"] == NARROW and call["workers"] is None
    assert call["cache_dir"] == tmp_path / "p" / "u0" / "c"  # the FIRST attempt's cache
    assert h.cleared == 0, "coverage must be appended to, never erased, on a narrow retry"
    assert (res.outcome, res.race, res.retry_kind) == (PASS, True, retry.RETRY_FAILED_ONLY)
    report, outcome = h.recorded[0]
    assert outcome == PASS and report == tmp_path / "m" / "u0" / "r.xml"
    assert junit_failure_count(report) == 0
    assert len(list(ET.parse(report).getroot().iter("testcase"))) == 4  # the WHOLE unit
    assert res in mod.unrecorded_races(mod.SuiteResult([res], 0, 1.0))  # still a recorded race


def test_still_red_after_the_narrow_retry_is_red_with_the_retrys_output(tmp_path):
    _attempt(tmp_path, ["bad"], ["ok"])
    h = _Harness(tmp_path, [(1, [("bad", True)])])
    res = _red()
    h.run([res])
    assert (res.outcome, res.race, res.output) == (TEST_FAILURE, False, "retry out rc=1")
    assert res.retry_kind == retry.RETRY_FAILED_ONLY and h.cleared == 0
    assert junit_failure_count(h.recorded[0][0]) == 1


def test_without_a_cache_the_whole_unit_is_retried_as_before(tmp_path):
    _attempt(tmp_path, ["bad"], ["ok"], cache=False)
    h = _Harness(tmp_path, [(0, [("bad", False), ("ok", False)])])
    res = _red()
    h.run([res])
    assert h.exec_calls[0]["extra_args"] == () and h.exec_calls[0]["cache_dir"] is None
    assert h.cleared == 1 and (res.retry_kind, res.race) == (retry.RETRY_SERIAL, True)
    assert h.recorded[0][0] == tmp_path / "s" / "u0" / "r.xml"


def test_a_count_mismatch_between_cache_and_report_falls_back_whole(tmp_path):
    _attempt(tmp_path, ["bad"], ["ok"])
    extra = tmp_path / "p" / "u0" / "c" / LASTFAILED
    extra.write_text(json.dumps({"t.py::bad": True, "t.py::ghost": True}), encoding="utf-8")
    h = _Harness(tmp_path, [(0, [("bad", False), ("ok", False)])])
    h.run([_red()])
    assert h.exec_calls[0]["extra_args"] == () and h.cleared == 1


def test_wide_failure_is_treated_as_pollution_and_retried_whole(tmp_path):
    names = [f"bad{i}" for i in range(retry.FAILED_ONLY_MAX_TESTS + 1)]
    _attempt(tmp_path, names, ["ok"])
    h = _Harness(tmp_path, [(0, [(n, False) for n in names] + [("ok", False)])])
    res = _red()
    h.run([res])
    assert h.exec_calls[0]["extra_args"] == () and res.retry_kind == retry.RETRY_SERIAL


def test_rc5_nothing_selected_falls_back_to_the_whole_unit(tmp_path):
    _attempt(tmp_path, ["bad"], ["ok"])
    h = _Harness(tmp_path, [(5, None), (0, [("bad", False), ("ok", False)])])
    res = _red()
    h.run([res])
    assert [c["extra_args"] for c in h.exec_calls] == [NARROW, ()]
    assert h.cleared == 1, "the whole-unit path erases the failed attempt's coverage"
    assert (res.outcome, res.retry_kind, res.seconds) == (PASS, retry.RETRY_SERIAL, 3.0 + 0.5 + 0.5)


def test_an_unmergeable_retry_report_falls_back_to_the_whole_unit(tmp_path):
    _attempt(tmp_path, ["bad"], ["ok"])
    h = _Harness(tmp_path, [(0, None), (0, [("bad", False), ("ok", False)])])  # no r.xml written
    h.run([_red()])
    assert len(h.exec_calls) == 2 and h.exec_calls[1]["extra_args"] == () and h.cleared == 1


def test_the_whole_unit_fallback_starts_without_the_narrow_attempts_report(tmp_path):
    """A leftover r.xml would read as proof pytest ran in the fallback (and be retained)."""
    _attempt(tmp_path, ["bad"], ["ok"])
    h = _Harness(tmp_path, [(5, [("bad", True)]), (5, None)])  # narrow leaves a report, rc 5
    h.run([_red()])
    assert h.exec_calls[1]["stale_report"] is False


def test_the_fallback_runs_under_the_heartbeat_and_announces_itself(tmp_path):
    _attempt(tmp_path, ["bad"], ["ok"])
    h = _Harness(tmp_path, [(5, None), (0, [("bad", False), ("ok", False)])])
    h.run([_red()])
    assert all(c["heartbeat"] for c in h.exec_calls)
    assert h.events == [("start", "failed-only"), ("start", "authoritative-serial"),
                        ("complete", "authoritative-serial")]


def test_a_short_rerun_that_lost_a_red_test_falls_back_to_the_whole_unit(tmp_path):
    """`--lf` skips ids it can no longer collect and exits 0: 1 of 2 red tests re-ran."""
    _attempt(tmp_path, ["bad1", "bad2"], ["ok"])
    whole = [("bad1", False), ("bad2", False), ("ok", False)]
    h = _Harness(tmp_path, [(0, [("bad1", False)]), (0, whole)])
    res = _red()
    h.run([res])
    assert [c["extra_args"] == () for c in h.exec_calls] == [False, True]
    assert (res.retry_kind, h.cleared) == (retry.RETRY_SERIAL, 1)
    assert len(list(ET.parse(h.recorded[0][0]).getroot().iter("testcase"))) == 3


@pytest.mark.parametrize("marker", ["!!! stopping after 1 failures !!!", "Worker GW0 CRASHED while running", "node down: x"])
def test_an_incomplete_first_attempt_is_retried_whole(tmp_path, marker):
    _attempt(tmp_path, ["bad"], ["ok"])
    h = _Harness(tmp_path, [(0, [("bad", False), ("ok", False)])])
    res = _red()
    res.output = marker
    h.run([res])
    assert h.exec_calls[0]["extra_args"] == () and h.cleared == 1


def test_a_truncated_first_attempt_is_retried_whole(tmp_path):
    """The output is only a tail: an incomplete run cannot be ruled out, so never narrow."""
    _attempt(tmp_path, ["bad"], ["ok"])
    h = _Harness(tmp_path, [(0, [("bad", False), ("ok", False)])])
    res = _red()
    res.truncated = True
    h.run([res])
    assert h.exec_calls[0]["extra_args"] == () and h.cleared == 1


def test_a_rerun_that_ran_more_than_the_red_tests_falls_back(tmp_path):
    """No `lastfailed` id matched: pytest runs EVERYTHING, so its coverage must not append."""
    _attempt(tmp_path, ["bad"], ["ok"])
    whole = [("bad", False), ("ok", False)]
    h = _Harness(tmp_path, [(0, whole), (0, whole)])
    res = _red()
    h.run([res])
    assert len(h.exec_calls) == 2 and h.cleared == 1 and res.retry_kind == retry.RETRY_SERIAL


def test_an_uninstrumented_unit_gets_no_cov_append(tmp_path):
    _attempt(tmp_path, ["bad"], ["ok"])
    plain = Unit(id=UNIT.id, cwd=UNIT.cwd, target=UNIT.target)
    h = _Harness(tmp_path, [(0, [("bad", False)])], unit=plain)
    h.run([_red()])
    assert h.exec_calls[0]["extra_args"] == FAILED_ONLY_ARGS


@pytest.mark.parametrize("cancel_on", [1, 2])
def test_cancellation_propagates_without_recording_a_result(tmp_path, cancel_on):
    """1 = cancelled during the narrow try, 2 = during the whole-unit fallback."""
    _attempt(tmp_path, ["bad"], ["ok"])
    script = [(130, None)] if cancel_on == 1 else [(5, None), (130, None)]
    h = _Harness(tmp_path, script, cancel_on=cancel_on)
    with pytest.raises(KeyboardInterrupt):
        h.run([_red()])
    assert h.recorded == [] and h.retained == ["cancelled-retry"]


def test_an_infra_fault_never_takes_the_failed_only_path(tmp_path):
    _attempt(tmp_path, ["bad"], ["ok"])
    h = _Harness(tmp_path, [(0, [("bad", False), ("ok", False)])])
    res = _red(INFRA)
    h.run([res])
    call = h.exec_calls[0]
    assert call["extra_args"] == () and call["workers"] == 8  # identical shape, xdist kept
    assert res.retry_kind == retry.RETRY_INFRA


def test_a_passing_unit_is_left_alone(tmp_path):
    h = _Harness(tmp_path, [])
    res = mod.UnitResult(UNIT.id, PASS, 0, 1.0)
    h.run([res])
    assert not h.exec_calls and not h.recorded


def test_the_console_names_a_failed_only_retry(tmp_path):
    res = mod.UnitResult(UNIT.id, PASS, 1, 3.0, "out", race=True,
                         retry_kind=retry.RETRY_FAILED_ONLY)
    lines = mod.render_run_report(mod.SuiteResult([res], 0, 1.0))
    assert "failed-only retry" in lines[0] and all(ord(ch) < 128 for ch in lines[0])
    block = next(line for line in lines if "RETRY-GREEN" in line)
    assert "failed-only retry" in block.splitlines()[2]
