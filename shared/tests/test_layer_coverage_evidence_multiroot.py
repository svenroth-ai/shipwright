"""``_layer_coverage_evidence.fresh_evidence`` multi-root JUnit join (R1a, E-C).

Split out of ``test_layer_coverage_core.py`` (300-LOC guideline) rather than grown
there. Pins the closure of the A6 "per-runner bases not threaded here" deferral:
each staged pytest-root report (``evidence_drop`` E-B) must join with its OWN
recorded base, and a malformed/missing base must be rejected fail-closed, never
silently defaulted to the project root.
"""

from __future__ import annotations

import json
from pathlib import Path

_JUNIT_SHARED = (
    '<testsuites><testsuite name="pytest" tests="1" failures="0">'
    '<testcase classname="tests.x" name="test_a" file="tests/x.py"/>'
    "</testsuite></testsuites>"
)
_JUNIT_PLUGIN = (
    '<testsuites><testsuite name="pytest" tests="1" failures="0">'
    '<testcase name="test_b" file="tests/b.py"/>'
    "</testsuite></testsuites>"
)


def _evio():
    from tools.verifiers._layer_coverage_regen import _load_collector  # noqa: PLC0415

    return _load_collector()[2]


def _stage_single(root: Path, run_id: str, body: str) -> None:
    from lib import evidence_drop  # noqa: PLC0415

    junit = root / "junit.xml"
    junit.write_text(body, encoding="utf-8")
    evidence_drop.stage_reports(root, run_id=run_id, head_commit="deadbeef", junit=junit)


def test_fresh_evidence_joins_multi_root_reports_each_with_its_own_base(tmp_path):
    # R1a / E-C: a run staging N pytest-root reports (ADR-044: one process per root)
    # must have EACH one join with its OWN base, not just the first/only one.
    from lib import evidence_drop  # noqa: PLC0415
    from tools.verifiers._layer_coverage_evidence import fresh_evidence  # noqa: PLC0415

    shared_report = tmp_path / "shared.xml"
    shared_report.write_text(_JUNIT_SHARED, encoding="utf-8")
    plugin_report = tmp_path / "plugin.xml"
    plugin_report.write_text(_JUNIT_PLUGIN, encoding="utf-8")
    evidence_drop.stage_reports(
        tmp_path, run_id="r", head_commit="deadbeef",
        junit_reports=[("", shared_report), ("plugins/shipwright-compliance", plugin_report)],
    )
    ev = fresh_evidence(tmp_path, "r", "", _evio())
    assert "tests/x.py::test_a" in ev
    assert "plugins/shipwright-compliance/tests/b.py::test_b" in ev


def test_fresh_evidence_rejects_a_staged_report_with_no_base_recorded(tmp_path):
    # Fail-closed (AC): if a provenance entry is missing its base, that report is
    # skipped rather than silently read at base="" (which could join the wrong id).
    from lib import evidence_drop  # noqa: PLC0415
    from tools.verifiers._layer_coverage_evidence import fresh_evidence  # noqa: PLC0415

    _stage_single(tmp_path, "r", _JUNIT_SHARED)
    prov_path = evidence_drop.evidence_dir(tmp_path) / "_provenance.json"
    prov = json.loads(prov_path.read_text(encoding="utf-8"))
    del prov["reports"]["junit"][0]["base"]  # simulate a malformed sidecar entry
    prov_path.write_text(json.dumps(prov), encoding="utf-8")
    assert fresh_evidence(tmp_path, "r", "", _evio()) == {}


def test_fresh_evidence_rejects_a_provenance_name_that_escapes_the_evidence_dir(tmp_path):
    # External-review finding: a malformed/tampered _provenance.json ``name`` with a
    # path separator (or an absolute path) must never be read outside evidence/ — only
    # a bare junit-NN.xml basename is trusted, everything else is rejected fail-closed.
    from lib import evidence_drop  # noqa: PLC0415
    from tools.verifiers._layer_coverage_evidence import fresh_evidence  # noqa: PLC0415

    _stage_single(tmp_path, "r", _JUNIT_SHARED)
    outside = tmp_path / "outside-secret.xml"
    outside.write_text(
        '<testsuites><testsuite name="pytest" tests="1" failures="0">'
        '<testcase classname="tests.evil" name="test_evil" file="tests/evil.py"/>'
        "</testsuite></testsuites>",
        encoding="utf-8",
    )
    prov_path = evidence_drop.evidence_dir(tmp_path) / "_provenance.json"
    prov = json.loads(prov_path.read_text(encoding="utf-8"))
    prov["reports"]["junit"][0]["name"] = "../outside-secret.xml"
    prov_path.write_text(json.dumps(prov), encoding="utf-8")
    ev = fresh_evidence(tmp_path, "r", "", _evio())
    assert ev == {}  # rejected — never reads the escaped path, not even as MISSING evidence
    assert "tests/evil.py::test_evil" not in ev


def test_fresh_evidence_single_report_form_still_joins_at_base_empty(tmp_path):
    # Backward compat: the pre-R1a single-report call shape (``junit=``) keeps
    # working end to end through the gate, not just through evidence_drop directly.
    from tools.verifiers._layer_coverage_evidence import fresh_evidence  # noqa: PLC0415

    _stage_single(tmp_path, "r", _JUNIT_SHARED)
    ev = fresh_evidence(tmp_path, "r", "", _evio())
    assert "tests/x.py::test_a" in ev
