"""Retry / flaky reporting in the browser-test result reader.

A test that only passed on retry used to be indistinguishable from one that
passed first time: Playwright's per-test verdict (``expected`` / ``unexpected``
/ ``flaky`` / ``skipped``) was never read, and every ATTEMPT was counted as its
own test — so a retried-and-passed test inflated ``total`` AND landed in
``failed``, turning a green run red.

Split out of ``test_playwright_runner.py`` to keep both files under the
300-line guideline. iterate-2026-07-27-test-phase-record-honesty, FR-01.06.
"""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "lib"))
from playwright_runner import classify_test, parse_playwright_json, run_playwright


def _results_file(tmp_path, suites, stats=None):
    path = tmp_path / "e2e-results.json"
    path.write_text(json.dumps({"suites": suites, "stats": stats or {"duration": 1000}}))
    return path


def _suite(specs, title="s.spec.ts", file="e2e/s.spec.ts"):
    return [{"title": title, "file": file, "specs": specs, "suites": []}]


def _spec(title, tests, file="e2e/s.spec.ts"):
    return {"title": title, "file": file, "tests": tests}


class TestClassifyDecisionTable:
    """The normative status/retry table. Unknown shapes never become passes."""

    @pytest.mark.covers("FR-01.06")
    @pytest.mark.parametrize(
        ("test_obj", "outcome", "retries"),
        [
            # Playwright's own per-test verdict wins whenever it is present.
            ({"status": "expected", "results": [{"status": "passed", "retry": 0}]},
             "passed", 0),
            ({"status": "flaky", "results": [{"status": "failed", "retry": 0},
                                             {"status": "passed", "retry": 1}]},
             "flaky", 1),
            ({"status": "unexpected", "results": [{"status": "failed", "retry": 0},
                                                  {"status": "failed", "retry": 1}]},
             "failed", 1),
            ({"status": "skipped", "results": [{"status": "skipped"}]}, "skipped", 0),
            # Verdict absent — derive from the attempts.
            ({"results": [{"status": "passed"}]}, "passed", 0),
            ({"results": [{"status": "failed"}, {"status": "passed"}]}, "flaky", 1),
            # More than one attempt IS the retry signal, whatever the older
            # reporter called the earlier one — the table says so, and the code
            # used to disagree (external code review on the delivered head).
            ({"results": [{"status": "passed"}, {"status": "passed"}]}, "flaky", 1),
            ({"results": [{"status": "timedOut"}, {"status": "passed"}]}, "flaky", 1),
            ({"results": [{"status": "failed"}, {"status": "failed"}]}, "failed", 1),
            ({"results": [{"status": "timedOut"}]}, "failed", 0),
            ({"results": [{"status": "interrupted"}]}, "failed", 0),
            ({"results": [{"status": "skipped"}, {"status": "skipped"}]}, "skipped", 0),
        ],
    )
    def test_each_row_of_the_table(self, test_obj, outcome, retries):
        assert classify_test(test_obj) == (outcome, retries)

    @pytest.mark.covers("FR-01.06")
    def test_no_results_at_all_is_a_failure_not_a_pass(self):
        # The conservative row: an incomplete record must never be promoted
        # into a passing one.
        assert classify_test({"results": []}) == ("failed", 0)

    @pytest.mark.covers("FR-01.06")
    def test_an_unrecognised_status_is_a_failure_not_a_pass(self):
        assert classify_test({"results": [{"status": "wat"}]}) == ("failed", 0)

    @pytest.mark.covers("FR-01.06")
    def test_an_unrecognised_test_level_verdict_falls_back_to_the_attempts(self):
        assert classify_test(
            {"status": "sideways", "results": [{"status": "passed"}]}
        ) == ("passed", 0)

    @pytest.mark.covers("FR-01.06")
    def test_a_skip_after_a_failure_is_not_reported_as_skipped(self):
        # Mixed attempts ending in a skip: conservative, because "skipped"
        # would erase a real failure from the record.
        assert classify_test(
            {"results": [{"status": "failed"}, {"status": "skipped"}]}
        ) == ("failed", 1)

    @pytest.mark.covers("FR-01.06")
    def test_a_garbage_test_object_does_not_crash_the_reader(self):
        assert classify_test({}) == ("failed", 0)
        assert classify_test({"results": "nope"}) == ("failed", 0)


class TestFlakyCounting:
    @pytest.mark.covers("FR-01.06")
    def test_a_retried_and_passed_test_is_a_pass_and_is_counted_as_flaky(self, tmp_path):
        path = _results_file(tmp_path, _suite([
            _spec("checkout works", [{
                "status": "flaky",
                "results": [{"status": "failed", "retry": 0,
                             "error": {"message": "timeout"}},
                            {"status": "passed", "retry": 1}],
            }]),
        ]))
        r = parse_playwright_json(path)

        assert r["passed"] == 1
        assert r["failed"] == 0
        assert r["flaky"] == 1
        assert r["failures"] == []
        # flaky is a SUBSET of passed, not a fourth bucket
        assert r["passed"] + r["failed"] + r["skipped"] == r["total"] == 1
        assert r["flaky"] <= r["passed"]

    @pytest.mark.covers("FR-01.06")
    def test_the_flaky_test_is_named_with_its_retry_count(self, tmp_path):
        path = _results_file(tmp_path, _suite([
            _spec("checkout works", [{
                "status": "flaky",
                "results": [{"status": "failed", "retry": 0},
                            {"status": "failed", "retry": 1},
                            {"status": "passed", "retry": 2}],
            }]),
        ]))
        r = parse_playwright_json(path)

        assert r["flaky_tests"] == [{
            "title": "checkout works", "file": "e2e/s.spec.ts", "retries": 2,
        }]

    @pytest.mark.covers("FR-01.06")
    def test_a_flaky_test_does_not_make_the_run_fail(self, tmp_path):
        _results_file(tmp_path, _suite([
            _spec("flaky one", [{"status": "flaky", "results": [
                {"status": "failed", "retry": 0}, {"status": "passed", "retry": 1}]}]),
        ]))
        with patch("playwright_runner.subprocess.run") as mock_run:
            data = json.loads((tmp_path / "e2e-results.json").read_text())

            def rerun(*a, **k):
                (tmp_path / "e2e-results.json").write_text(json.dumps(data))
                return MagicMock(returncode=0, stdout="", stderr="")

            mock_run.side_effect = rerun
            result = run_playwright(tmp_path)

        assert result["success"] is True
        assert result["flaky"] == 1

    @pytest.mark.covers("FR-01.06")
    def test_retries_no_longer_inflate_the_total(self, tmp_path):
        # Two tests, four attempts between them. The old reader reported
        # total=4, passed=2, failed=2 — wrong in both directions.
        path = _results_file(tmp_path, _suite([
            _spec("a", [{"status": "flaky", "results": [
                {"status": "failed", "retry": 0}, {"status": "passed", "retry": 1}]}]),
            _spec("b", [{"status": "unexpected", "results": [
                {"status": "failed", "retry": 0},
                {"status": "failed", "retry": 1, "error": {"message": "still broken"}}]}]),
        ]))
        r = parse_playwright_json(path)

        assert r["total"] == 2
        assert r["passed"] == 1
        assert r["failed"] == 1
        assert r["flaky"] == 1

    @pytest.mark.covers("FR-01.06")
    def test_a_genuine_failure_carries_its_retry_count_and_last_error(self, tmp_path):
        path = _results_file(tmp_path, _suite([
            _spec("b", [{"status": "unexpected", "results": [
                {"status": "failed", "retry": 0, "error": {"message": "first"}},
                {"status": "failed", "retry": 1, "error": {"message": "last"}}]}]),
        ]))
        r = parse_playwright_json(path)

        assert len(r["failures"]) == 1
        assert r["failures"][0]["retries"] == 1
        assert r["failures"][0]["error"] == "last"

    @pytest.mark.covers("FR-01.06")
    def test_a_run_with_no_retries_reports_zero_flaky(self, tmp_path):
        path = _results_file(tmp_path, _suite([
            _spec("a", [{"status": "expected", "results": [{"status": "passed"}]}]),
        ]))
        r = parse_playwright_json(path)
        assert r["flaky"] == 0
        assert r["flaky_tests"] == []

    @pytest.mark.covers("FR-01.06")
    def test_skipped_tests_are_counted_once_and_do_not_fail_the_run(self, tmp_path):
        path = _results_file(tmp_path, _suite([
            _spec("a", [{"status": "skipped", "results": [{"status": "skipped"}]}]),
            _spec("b", [{"status": "expected", "results": [{"status": "passed"}]}]),
        ]))
        r = parse_playwright_json(path)

        assert (r["total"], r["passed"], r["failed"], r["skipped"]) == (2, 1, 0, 1)

    @pytest.mark.covers("FR-01.06")
    def test_nested_suites_are_walked(self, tmp_path):
        path = _results_file(tmp_path, [{
            "title": "outer", "file": "e2e/o.spec.ts", "specs": [],
            "suites": _suite([
                _spec("inner", [{"status": "flaky", "results": [
                    {"status": "failed", "retry": 0}, {"status": "passed", "retry": 1}]}]),
            ]),
        }])
        r = parse_playwright_json(path)
        assert (r["total"], r["flaky"]) == (1, 1)


@pytest.mark.covers("FR-01.06")
def test_a_legacy_multi_attempt_pass_is_not_silently_a_first_time_pass(tmp_path):
    """Losing the retry here would lose exactly the signal AC6 asks for."""
    path = _results_file(tmp_path, _suite([
        _spec("checkout", [{"results": [{"status": "passed"}, {"status": "passed"}]}]),
    ]))
    r = parse_playwright_json(path)

    assert (r["passed"], r["failed"], r["flaky"], r["total"]) == (1, 0, 1, 1)
    assert r["flaky_tests"][0]["retries"] == 1
