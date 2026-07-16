"""TT-EV execution-evidence READER tests — Spec §11 R1 (closes G5).

RED before TT-EV (``execution_evidence`` / ``_execution_evidence_io`` did not
exist); green after. AC1 the reader maps JUnit/Playwright/Vitest evidence to
per-test status/executed over the P1 fixtures (a skipped tagged test is
skipped/not_run). AC4 the status/executed vocab is a validated frozen boundary —
an out-of-vocab value is coerced fail-closed and cannot drift from the schema.
The manifest-join + waiver + finalization-wiring half lives in
``test_execution_evidence_join.py``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import jsonschema
import pytest

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))

from scripts.lib.collectors.execution_evidence import (  # noqa: E402
    EXECUTED_VOCAB,
    STATUS_VOCAB,
    build_index,
    normalize_index,
    read_junit,
    read_playwright,
    read_vitest,
    validate_index,
)

_LIB = _HERE.parent / "scripts" / "lib"
_EV = _HERE / "fixtures" / "traceability" / "evidence"
_SCHEMA_PATH = _LIB / "evidence_index_schema.json"

_SKIPPED_E2E = "e2e/auth.spec.ts::signs in and lands on dashboard"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def raw_index() -> dict:
    """The index the reader produces from the three raw P1 runner reports."""
    return build_index(
        junit=(_EV / "junit.xml").read_text(encoding="utf-8"),
        playwright=_load(_EV / "playwright.json"),
        vitest=_load(_EV / "vitest.json"),
    )


# --- AC1: three-runner reader reproduces the normalized answer key ----------

def test_reader_reproduces_evidence_index_answer_key(raw_index):
    # For every entry in the hand-authored normalized index, the reader derives
    # the SAME (status, executed, runner) from the raw runner reports — so the
    # answer key can never silently diverge from the raw reporter output (R1).
    golden = _load(_EV / "evidence_index.json")["results"]
    got = raw_index["results"]
    for tid, want in golden.items():
        assert tid in got, tid
        assert got[tid]["status"] == want["status"], tid
        assert got[tid]["executed"] == want["executed"], tid
        assert got[tid]["runner"] == want["runner"], tid


def test_reader_keys_are_collector_path_name_ids(raw_index):
    # Keys must be the collector's stable `path::name` id (posix path, no backslash).
    for tid in raw_index["results"]:
        assert "::" in tid and "\\" not in tid


def test_skipped_tagged_test_is_skipped_not_run(raw_index):
    # AC1 the R1 primitive: a skipped tagged e2e is status=skipped, executed=not_run.
    entry = raw_index["results"][_SKIPPED_E2E]
    assert (entry["status"], entry["executed"]) == ("skipped", "not_run")


def test_junit_maps_pass_and_key_from_file_attr():
    out = read_junit((_EV / "junit.xml").read_text(encoding="utf-8"))
    entry = out["tests/test_auth.py::test_sign_in_rejects_bad_password"]
    assert entry == {"status": "enabled", "executed": "pass", "runner": "pytest"}


def test_junit_failure_and_skipped_children_map_fail_closed():
    xml = (
        "<testsuites><testsuite>"
        '<testcase file="t.py" name="a"><failure/></testcase>'
        '<testcase file="t.py" name="b"><skipped/></testcase>'
        '<testcase file="t.py" name="c"><error/></testcase>'
        "</testsuite></testsuites>"
    )
    out = read_junit(xml)
    assert (out["t.py::a"]["status"], out["t.py::a"]["executed"]) == ("enabled", "fail")
    assert (out["t.py::b"]["status"], out["t.py::b"]["executed"]) == ("skipped", "not_run")
    assert (out["t.py::c"]["status"], out["t.py::c"]["executed"]) == ("enabled", "fail")


def test_playwright_and_vitest_pass_mapping():
    pw = read_playwright(_load(_EV / "playwright.json"))
    assert pw["e2e/dashboard.spec.ts::dashboard shows live orders"]["executed"] == "pass"
    vt = read_vitest(_load(_EV / "vitest.json"))
    assert vt["unit/orders.test.ts::writes the order row"]["executed"] == "pass"


def test_read_vitest_failed_and_skipped_branches():
    data = {"testResults": [{"name": "unit/x.test.ts", "assertionResults": [
        {"title": "f", "status": "failed"},
        {"title": "s", "status": "skipped"},
        {"title": "t", "status": "todo"},
    ]}]}
    out = read_vitest(data)
    assert (out["unit/x.test.ts::f"]["status"], out["unit/x.test.ts::f"]["executed"]) == ("enabled", "fail")
    assert out["unit/x.test.ts::s"] == {"status": "skipped", "executed": "not_run", "runner": "vitest"}
    assert (out["unit/x.test.ts::t"]["status"], out["unit/x.test.ts::t"]["executed"]) == ("skipped", "not_run")


def test_reader_output_validates_against_schema(raw_index):
    validate_index(raw_index)  # raises on invalid
    assert raw_index["schema_version"] == 2


# --- fail-closed reduction when a test id repeats (retries/shards/projects) --

def test_duplicate_test_id_failure_is_not_hidden_by_a_later_pass():
    xml = (
        "<testsuites><testsuite>"
        '<testcase file="t.py" name="a"><failure/></testcase>'
        '<testcase file="t.py" name="a"/>'   # a later passing record for the same id
        "</testsuite></testsuites>"
    )
    assert read_junit(xml)["t.py::a"]["executed"] == "fail"


def test_playwright_retry_reduces_to_pass_only_failure_is_fail():
    retried = {"suites": [{"file": "e2e/x.spec.ts", "specs": [
        {"title": "flaky", "tests": [{"status": "flaky", "results": [
            {"status": "failed"}, {"status": "passed"}]}]},
        {"title": "broken", "tests": [{"status": "unexpected", "results": [
            {"status": "failed"}, {"status": "failed"}]}]},
    ]}]}
    out = read_playwright(retried)
    assert out["e2e/x.spec.ts::flaky"]["executed"] == "pass"      # a retry passed
    assert out["e2e/x.spec.ts::broken"]["executed"] == "fail"     # never passed


def test_oversized_junit_report_fails_closed_empty():
    huge = "<testsuites>" + '<testcase file="t.py" name="x"/>' * 400_000 + "</testsuites>"
    assert read_junit(huge) == {}   # over the byte cap -> empty parse, never a pass


# --- AC4: the status/executed vocab is a validated frozen boundary ----------

def test_out_of_vocab_evidence_is_coerced_fail_closed():
    # A forged/typo'd index value (executed:"passed", status:"active") must NEVER
    # be trusted as a real pass at ingestion.
    raw = {"schema_version": 2, "results": {
        "a::b": {"status": "active", "executed": "passed", "runner": "x"},
        "c::d": {"status": "enabled", "executed": "pass"},
    }}
    norm = normalize_index(raw)
    assert norm["results"]["a::b"]["executed"] == "not_run"     # forged pass rejected
    assert norm["results"]["a::b"]["status"] == "quarantined"   # forged status held-out
    assert norm["results"]["c::d"] == {"status": "enabled", "executed": "pass"}
    validate_index(norm)                                        # normalized output is schema-valid


@pytest.fixture(scope="module")
def schema_validator() -> jsonschema.Draft202012Validator:
    schema = _load(_SCHEMA_PATH)
    jsonschema.Draft202012Validator.check_schema(schema)
    return jsonschema.Draft202012Validator(schema)


def test_schema_validates_the_fixture_index(schema_validator):
    assert not list(schema_validator.iter_errors(_load(_EV / "evidence_index.json")))


def test_schema_rejects_out_of_vocab_and_extra_keys(schema_validator):
    good = {"schema_version": 2, "results": {
        "a::b": {"status": "enabled", "executed": "pass", "runner": "pytest"},
    }}
    assert not list(schema_validator.iter_errors(good))

    bad_exec = json.loads(json.dumps(good))
    bad_exec["results"]["a::b"]["executed"] = "passed"
    assert list(schema_validator.iter_errors(bad_exec))

    bad_status = json.loads(json.dumps(good))
    bad_status["results"]["a::b"]["status"] = "active"
    assert list(schema_validator.iter_errors(bad_status))

    extra = json.loads(json.dumps(good))
    extra["results"]["a::b"]["unexpected"] = True
    assert list(schema_validator.iter_errors(extra))


def test_schema_waiver_requires_full_accountability(schema_validator):
    base = {"schema_version": 2, "results": {}, "waivers": [{
        "layer": "e2e", "reason": "r", "owner": "o", "ticket": "T-1", "expires": "2026-12-31",
    }]}
    assert not list(schema_validator.iter_errors(base))
    incomplete = json.loads(json.dumps(base))
    del incomplete["waivers"][0]["owner"]                       # missing accountability field
    assert list(schema_validator.iter_errors(incomplete))


def test_code_vocab_cannot_drift_from_schema_enums():
    # The reader's frozen vocab and the schema's closed enums are one contract; a
    # future edit to one without the other must break here (review finding).
    schema = _load(_SCHEMA_PATH)["$defs"]["evidence"]["properties"]
    assert set(schema["status"]["enum"]) == set(STATUS_VOCAB)
    assert set(schema["executed"]["enum"]) == set(EXECUTED_VOCAB)
