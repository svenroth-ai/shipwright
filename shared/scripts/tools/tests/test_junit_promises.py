"""junit_promises.py: a promise reads ``passing`` only when its test ran and passed in the run's own report.

Today ``test_promises_meta.py`` proves only that the named test exists, so a promise test skipped or deselected at
run time still reads ``passing``; each case below is one way that hole shows up, caught from the report.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # shared/scripts/tools

import junit_promises as jp  # noqa: E402

pytestmark = pytest.mark.covers("FR-01.09")  # the junit reader of the changelog pilot; no AC is claimed

NODE = "plugins/shipwright-changelog/tests/golden/test_promise_release.py::test_ac01"
SENTINEL = "plugins/shipwright-changelog/tests/golden/test_trace_freeze.py::test_the_real_tree_respects_the_freeze"
CLS = "tests.golden.test_promise_release"
PROMISES = [{"id": "AC01", "status": "passing", "check": {"kind": "test", "id": NODE}},
            {"id": "AC11", "status": "gap", "check": None},
            {"id": "J", "status": "not-run", "check": {"kind": "scenario", "id": "x"}}]


def write(tmp_path: Path, *cases: str) -> list[tuple[str, str, str]]:
    path = tmp_path / "r.xml"
    path.write_text(f"<testsuites><testsuite>{''.join(cases)}</testsuite></testsuites>", encoding="utf-8")
    return jp.load_cases(path)


def case(name: str, extra: str = "", cls: str = CLS) -> str:
    return f'<testcase classname="{cls}" name="{name}">{extra}</testcase>'


def test_a_passing_test_in_the_report_agrees(tmp_path):
    report1 = write(tmp_path, case("test_ac01"))
    assert jp.passing_problems(PROMISES, report1) == []


@pytest.mark.parametrize("cases, word", [
    ([case("test_ac01", "<skipped/>")], "skipped"),           # skipped at run time with the entry still `passing`
    ([case("test_ac01", "<failure/>")], "failed"),
    ([case("test_ac01", "<error/>")], "failed"),
    ([case("test_other")], "missing"),                         # deselected or never collected
    ([case("test_ac01", cls="tests.other.test_x")], "missing"),
    ([case("test_ac01[a]"), case("test_ac01[b]", "<skipped/>")], "skipped"),   # one parameter skipped
])
def test_a_promise_whose_test_did_not_pass_is_caught(tmp_path, cases, word):
    found = jp.passing_problems(PROMISES, write(tmp_path, *cases))
    assert len(found) == 1 and f"its test {word}" in found[0] and found[0].startswith("AC01")


def test_parametrized_variants_match_by_suffix(tmp_path):
    cases = write(tmp_path, case("test_ac01[a]", cls=CLS), case("test_ac01[b]", cls=CLS))
    assert jp.outcome_of(NODE, cases) == jp.PASSED
    assert jp.outcome_of(NODE.replace("test_ac01", "test_ac"), cases) == jp.MISSING  # a prefix of a name is not a match


def test_a_failing_entry_whose_test_passes_is_caught(tmp_path):
    promises = [{"id": "AC09", "status": "failing", "check": {"kind": "test", "id": NODE}}]
    report2 = write(tmp_path, case("test_ac01"))
    assert "reads failing, but its test passed" in jp.passing_problems(promises, report2)[0]


def test_the_freeze_sentinel_must_have_run_and_passed(tmp_path):
    other = case("test_x", cls="tests.golden.other")
    report3 = write(tmp_path, other)
    assert "did not run and pass" in jp.named_problems("sentinel", [SENTINEL], report3)[0]
    skipped = case("test_the_real_tree_respects_the_freeze", "<skipped/>", cls="tests.golden.test_trace_freeze")
    report4 = write(tmp_path, skipped)
    assert "skipped" in jp.named_problems("sentinel", [SENTINEL], report4)[0]
    passed = case("test_the_real_tree_respects_the_freeze", cls="tests.golden.test_trace_freeze")
    report5 = write(tmp_path, passed)
    assert jp.named_problems("sentinel", [SENTINEL], report5) == []


def test_a_report_that_is_not_junit_or_is_empty_is_refused(tmp_path):
    bad = tmp_path / "bad.xml"
    bad.write_text("not xml", encoding="utf-8")
    with pytest.raises(ValueError, match="not a readable JUnit report"):
        jp.load_cases(bad)
    with pytest.raises(ValueError, match="not a readable"):
        jp.load_cases(tmp_path / "gone.xml")
    empty = tmp_path / "empty.xml"
    empty.write_text("<testsuites/>", encoding="utf-8")
    with pytest.raises(ValueError, match="collected nothing"):
        jp.load_cases(empty)


@pytest.mark.parametrize("prolog", ['<!DOCTYPE t [<!ENTITY a "x">]>', '<!ENTITY a "x">'])
def test_a_report_carrying_a_dtd_is_refused_before_parsing(tmp_path, prolog):
    # a DTD is the only door to entity expansion ("billion laughs"); a pytest JUnit file never carries one
    bad = tmp_path / "dtd.xml"
    bad.write_text(f"{prolog}<testsuites><testsuite>{case('test_ac01')}</testsuite></testsuites>", encoding="utf-8")
    with pytest.raises(ValueError, match="DTD"):
        jp.load_cases(bad)


def test_a_report_shaped_like_real_pytest_output_still_parses(tmp_path):
    real = tmp_path / "real.xml"
    real.write_text('<?xml version="1.0" encoding="utf-8"?>'
                    f"<testsuites><testsuite>{case('test_ac01')}</testsuite></testsuites>", encoding="utf-8")
    assert jp.load_cases(real) == [(CLS, "test_ac01", jp.PASSED)]


def test_a_report_that_is_not_utf8_is_refused(tmp_path):
    bad = tmp_path / "latin.xml"
    bad.write_bytes(b"\xff<testsuites/>")
    with pytest.raises(ValueError, match="not a readable JUnit report"):
        jp.load_cases(bad)


def test_an_oversized_report_is_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(jp, "_MAX_XML_BYTES", 10)
    big = tmp_path / "big.xml"
    big.write_text(f"<testsuites><testsuite>{case('test_ac01')}</testsuite></testsuites>", encoding="utf-8")
    with pytest.raises(ValueError, match="larger than"):
        jp.load_cases(big)


def test_the_export_copies_the_list_unchanged():
    promise_list = {"subject": "s", "schema": 1, "promises": PROMISES}
    exported = jp.export_trace(promise_list)
    assert exported["promises"] == PROMISES and exported["promises"][0] is not PROMISES[0]
    assert jp.dump({"a": 1}).endswith("}\n")


MORE = [{"id": "AC03", "status": "passing", "check": {"kind": "test", "id": NODE},
         "more_checks": [{"kind": "test", "id": NODE.replace("test_ac01", "test_ac03b")}]}]


def test_a_passing_promise_needs_every_more_checks_test_to_pass(tmp_path):
    both = write(tmp_path, case("test_ac01"), case("test_ac03b"))
    assert jp.passing_problems(MORE, both) == []
    skipped = write(tmp_path, case("test_ac01"), case("test_ac03b", "<skipped/>"))
    found = jp.passing_problems(MORE, skipped)
    assert len(found) == 1 and "its test skipped" in found[0] and "test_ac03b" in found[0]
    report6 = write(tmp_path, case("test_ac01"))
    assert "missing" in jp.passing_problems(MORE, report6)[0]


def test_a_failing_promise_needs_one_test_not_to_pass(tmp_path):
    failing = [{**MORE[0], "status": "failing"}]
    report7 = write(tmp_path, case("test_ac01"), case("test_ac03b", "<failure/>"))
    assert jp.passing_problems(failing, report7) == []
    report8 = write(tmp_path, case("test_ac01"), case("test_ac03b"))
    assert "reads failing" in jp.passing_problems(failing, report8)[0]


@pytest.mark.parametrize("check", [None, {"kind": "test"}, {"kind": "test", "id": ""}, {"kind": "scenario", "id": "x"}])
def test_a_passing_promise_that_names_no_test_check_is_reported(tmp_path, check):
    found = jp.passing_problems([{"id": "AC05", "status": "passing", "check": check}], write(tmp_path, case("test_ac01")))
    assert found == ["AC05: reads passing, but names no test check"]


def test_two_modules_that_end_the_same_way_are_ambiguous_not_a_pass(tmp_path):
    cases = write(tmp_path, case("test_ac01"), case("test_ac01", cls="test_promise_release"))
    assert jp.outcome_of(NODE, cases) == jp.AMBIGUOUS
    assert "ambiguous" in jp.passing_problems(PROMISES, cases)[0]
