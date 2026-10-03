"""``refresh_index`` / ``build_index`` tag reused results of a resumed F0 run (``reused: true``)."""

from __future__ import annotations

import json

from scripts.lib.collectors import _execution_evidence_io as io
from scripts.lib.collectors._evidence_resume import reuse_predicate
from scripts.lib.collectors.execution_evidence import build_index

_J = '<testsuites><testsuite><testcase name="test_a" file="tests/a.py"/></testsuite></testsuites>'
_MARK = {"units": {"u": {"mode": "reused-green", "base": "plugins/u", "rerun_tests": []}}}


def test_predicate_handles_modes_and_garbage():
    assert reuse_predicate(None) is None and reuse_predicate({"units": []}) is None
    assert reuse_predicate({"units": {"u": {"mode": "reused-green", "base": ""}}}) is None
    fo = reuse_predicate({"units": {"u": {"mode": "failed-only", "base": "p/u",
                                          "rerun_tests": ["tests/t.py::C::test_x[1]"]}}})
    assert fo("p/u/tests/t.py::test_y") and not fo("p/u/tests/t.py::test_x")
    assert not fo("other/tests/t.py::test_y")


def test_build_index_tags_and_still_validates():
    idx = build_index(junit_reports=[(_J, "plugins/u")], resumed_local=_MARK)
    ent = idx["results"]["plugins/u/tests/a.py::test_a"]
    assert ent["reused"] is True and ent["executed"] == "pass"
    assert "reused" not in build_index(junit_reports=[(_J, "plugins/u")])["results"][
        "plugins/u/tests/a.py::test_a"]


def test_refresh_index_reads_the_staged_marker(tmp_path):
    d = tmp_path / ".shipwright" / "compliance" / "evidence"
    d.mkdir(parents=True)
    (d / "junit-01.xml").write_text(_J, encoding="utf-8")
    prov = {"run_id": "r", "reports": {"junit": [{"name": "junit-01.xml", "base": "plugins/u"}]},
            "resumed_local": _MARK}
    (d / "_provenance.json").write_text(json.dumps(prov), encoding="utf-8")
    out = io.refresh_index(tmp_path)
    got = json.loads(out.read_text(encoding="utf-8"))["results"]
    assert got["plugins/u/tests/a.py::test_a"]["reused"] is True


def test_param_with_double_colon_and_non_pytest_runner():
    fo = reuse_predicate({"units": {"u": {"mode": "failed-only", "base": "p/u",
                                          "rerun_tests": ["tests/t.py::test_x[a::b]"]}}})
    assert not fo("p/u/tests/t.py::test_x")  # the re-run test is NOT reused
    pw = {"suites": []}
    idx = build_index(junit_reports=[(_J, "plugins/u")], playwright=pw, resumed_local=_MARK)
    assert all(e.get("runner") != "playwright" or "reused" not in e for e in idx["results"].values())


def test_param_containing_a_closing_bracket_still_reads_as_rerun():
    fo = reuse_predicate({"units": {"u": {"mode": "failed-only", "base": "p/u",
                                          "rerun_tests": ["tests/t.py::test_x[a]b]"]}}})
    assert not fo("p/u/tests/t.py::test_x[a]b]")  # id as read_junit leaves it
    assert not fo("p/u/tests/t.py::test_x")        # id as a stripping reader would give
    assert fo("p/u/tests/t.py::test_y")
