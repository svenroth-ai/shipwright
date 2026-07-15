"""TT-EV real-world-join + robustness tests (review must-fixes).

Third test module (ADR-099 300-LOC cap) covering the fixes the delegated cascade +
CI bot surfaced: the Playwright multi-project false-green (MUST-FIX 1), path/id
normalization so real Vitest/pytest evidence actually joins (MUST-FIX 2), the CLI
path-traversal guard (MUST-FIX 3), pytest parametrization folding (SHOULD-FIX 4), and
the corrupt-report fail-closed skip (SHOULD-FIX 5). All fail-CLOSED.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))

from scripts.lib.collectors._execution_evidence_io import _confined, refresh_index  # noqa: E402
from scripts.lib.collectors.execution_evidence import build_index, read_playwright  # noqa: E402
from scripts.lib.collectors.test_links import build_manifest  # noqa: E402

_EV = _HERE / "fixtures" / "traceability" / "evidence"
_MULTIPROJECT_KEY = "e2e/checkout.spec.ts::completes checkout @FR-03.02"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


# --- MUST-FIX 1: Playwright multi-project pass must NOT mask a per-project fail ---

def test_multiproject_pass_does_not_mask_a_project_fail():
    out = read_playwright(_load(_EV / "playwright_multiproject.json"))
    # chromium passed + firefox failed -> the spec is FAIL (fail-closed), never pass.
    assert out[_MULTIPROJECT_KEY]["executed"] == "fail"


def test_multiproject_fail_yields_coverage_missing(tmp_path):
    # End-to-end: the failing multi-project spec -> coverage.e2e = MISSING.
    (tmp_path / "spec.md").write_text(
        "# Spec\n## Functional Requirements\n| FR | Description | Priority | Layers |\n"
        "|----|-------------|----------|--------|\n| FR-03.02 | Checkout | Must | e2e |\n",
        encoding="utf-8",
    )
    e2e = tmp_path / "e2e"
    e2e.mkdir()
    (e2e / "checkout.spec.ts").write_text(
        "test('completes checkout @FR-03.02', () => {});\n", encoding="utf-8",
    )
    evidence = read_playwright(_load(_EV / "playwright_multiproject.json"))
    manifest = build_manifest(
        tmp_path, spec_files=[tmp_path / "spec.md"], test_roots=[tmp_path],
        evidence=evidence, enumerate_untagged=True,
    )
    fr = next(r for r in manifest["requirements"].values() if r["id"] == "FR-03.02")
    assert fr["coverage"]["e2e"] == "MISSING"
    assert fr["tests"]["e2e"][0]["executed"] == "fail"


# --- MUST-FIX 2: normalize runner-emitted paths to project-root-relative ids -----

def test_absolute_vitest_name_is_rebased_and_joins(tmp_path):
    # Vitest/Jest emit an ABSOLUTE testResults[].name; it must strip to a
    # project_root-relative id so it joins the collector's id (else silent all-MISSING).
    abs_file = (tmp_path / "unit" / "orders.test.ts").as_posix()
    data = {"testResults": [{"name": abs_file, "assertionResults": [
        {"title": "writes the order row", "status": "passed"},
    ]}]}
    index = build_index(vitest=data, root=tmp_path)
    assert "unit/orders.test.ts::writes the order row" in index["results"]


def test_pytest_junit_base_rebases_a_per_plugin_file(tmp_path):
    # A per-plugin pytest JUnit emits file="tests/test_x.py" relative to the plugin
    # dir; the caller-supplied base rebases it to the project-root-relative id.
    xml = '<testsuites><testsuite><testcase file="tests/test_x.py" name="test_x"/></testsuite></testsuites>'
    index = build_index(junit=xml, bases={"junit": "plugins/shipwright-compliance"})
    assert "plugins/shipwright-compliance/tests/test_x.py::test_x" in index["results"]


# --- SHOULD-FIX 4: pytest parametrization folds fail-closed to the function id ---

def test_parametrized_junit_folds_to_function_id_fail_closed():
    xml = (
        "<testsuites><testsuite>"
        '<testcase file="tests/t.py" name="test_p[case0]"/>'
        '<testcase file="tests/t.py" name="test_p[case1]"><failure/></testcase>'
        "</testsuite></testsuites>"
    )
    index = build_index(junit=xml)
    # both params bind to path::test_p; one failed -> fail (a passing param can't mask it).
    assert index["results"]["tests/t.py::test_p"]["executed"] == "fail"


# --- MUST-FIX 3 + SHOULD-FIX 5: CLI path confinement + corrupt-report skip -------

def test_confined_rejects_paths_outside_project_root(tmp_path):
    with pytest.raises(SystemExit):
        _confined("../escape.xml", tmp_path)                 # ..-traversal
    with pytest.raises(SystemExit):
        _confined(str(tmp_path.parent / "escape.xml"), tmp_path)  # absolute outside root
    (tmp_path / "ok.xml").write_text("x", encoding="utf-8")
    assert _confined("ok.xml", tmp_path).name == "ok.xml"    # in-root path still works


def test_corrupt_report_is_skipped_fail_closed(tmp_path):
    drop = tmp_path / ".shipwright" / "compliance" / "evidence"
    drop.mkdir(parents=True)
    (drop / "junit.xml").write_text(
        '<testsuites><testsuite><testcase file="t.py" name="a"/></testsuite></testsuites>',
        encoding="utf-8",
    )
    (drop / "playwright.json").write_text('{ "suites": [ TRUNCATED', encoding="utf-8")  # invalid JSON
    out = refresh_index(tmp_path)                            # must NOT crash the regen
    index = _load(out)
    assert index["results"]["t.py::a"]["executed"] == "pass"  # junit still ingested
    assert not any(k.startswith("e2e/") for k in index["results"])  # corrupt playwright skipped
