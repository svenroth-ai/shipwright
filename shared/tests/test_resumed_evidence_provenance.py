"""A RESUMED F0 run's reused results are distinguished from executed ones downstream.

``stage_f0_evidence`` writes ``resumed_local``; F11's ``fresh_evidence`` tags reused entries
``reused`` and ``check_resumed_evidence`` warns - without ever blocking (the speed-up stays).
"""

from __future__ import annotations

from pathlib import Path

from lib import evidence_drop
from tools.verifiers._layer_coverage_evidence import fresh_evidence
from tools.verifiers._layer_coverage_regen import _load_collector
from tools.verifiers.common import Severity
from tools.verifiers.resumed_evidence import check_resumed_evidence

_A = ('<testsuites><testsuite><testcase name="test_a" file="tests/a.py"/>'
      '<testcase name="test_b" file="tests/b.py"/></testsuite></testsuites>')
_B = '<testsuites><testsuite><testcase name="test_c" file="tests/c.py"/></testsuite></testsuites>'
_RESUMED = {"units": {
    "unit-a": {"mode": "failed-only", "base": "plugins/a", "rerun_tests": ["tests/b.py::test_b"]},
    "unit-b": {"mode": "reused-green", "base": "plugins/b", "rerun_tests": []}}}


def _stage(root: Path, extra: dict | None) -> None:
    for name, body in (("a.xml", _A), ("b.xml", _B)):
        (root / name).write_text(body, encoding="utf-8")
    evidence_drop.stage_reports(
        root, run_id="r", head_commit="abc",
        junit_reports=[("plugins/a", root / "a.xml"), ("plugins/b", root / "b.xml")],
        provenance_extra=extra)


def test_reused_results_are_tagged_and_executed_ones_are_not(tmp_path):
    _stage(tmp_path, {"resumed_local": _RESUMED})
    ev = fresh_evidence(tmp_path, "r", "", _load_collector()[2])
    assert ev["plugins/a/tests/a.py::test_a"].get("reused") is True      # failed-only unit, not re-run
    assert "reused" not in ev["plugins/a/tests/b.py::test_b"]            # the re-run red test
    assert ev["plugins/b/tests/c.py::test_c"].get("reused") is True      # reused-green unit
    assert ev["plugins/b/tests/c.py::test_c"]["executed"] == "pass"      # still credited: no new block


def test_a_full_run_tags_nothing(tmp_path):
    _stage(tmp_path, None)
    ev = fresh_evidence(tmp_path, "r", "", _load_collector()[2])
    assert ev and not any("reused" in e for e in ev.values())


def test_check_warns_on_a_resumed_run_but_never_blocks(tmp_path):
    _stage(tmp_path, {"resumed_local": _RESUMED})
    res = check_resumed_evidence(tmp_path, "r")
    assert res.ok is False and res.severity == Severity.WARNING.value and res.strict_exempt
    assert "unit-a" in res.detail and "unit-b" in res.detail


def test_check_is_quiet_for_a_full_run_and_for_no_evidence(tmp_path):
    assert check_resumed_evidence(tmp_path, "r").is_skipped
    _stage(tmp_path, None)
    res = check_resumed_evidence(tmp_path, "r")
    assert res.ok is True and not res.is_failure


def test_check_never_crashes_on_malformed_provenance(tmp_path):
    bad = {"resumed_local": {"units": {"u": {"mode": "failed-only", "base": "p", "rerun_tests": 5}}}}
    _stage(tmp_path, bad)
    res = check_resumed_evidence(tmp_path, "r")
    assert res.severity == Severity.WARNING.value and res.strict_exempt
    _stage(tmp_path, {"resumed_local": "garbage"})
    assert not check_resumed_evidence(tmp_path, "r").is_failure
