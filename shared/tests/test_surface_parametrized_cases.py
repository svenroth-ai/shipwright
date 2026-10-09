"""F0.5 ``tests_run`` is the runner's per-CASE count; the evidence index folds parametrized cases.

A smoke unit recorded ``tests_run=18`` (pytest "18 passed") while the index showed 10 ids,
so F11's surface check went red on any unit with parametrized tests. The check now counts
passing cases in the runner's unit, still fail-closed on an overstated count or a failure.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.append(str(Path(__file__).resolve().parent))

import pytest  # noqa: E402

from _cascade_trigger_fixtures import make_repo, hermetic_git  # noqa: E402, F401 - autouse fixture
from _surface_check_fixtures import check, cli_block, stage, write_entry  # noqa: E402

TEST_FILE = {"tests/test_a.py": "def test_x():\n    pass\n"}
PARAMETRIZED = {
    "tests.test_a::test_x[a]": "pass", "tests.test_a::test_x[b]": "pass",
    "tests.test_a::test_x[c]": "pass", "tests.test_a::test_y": "pass",
}


@pytest.mark.covers("FR-01.11/AC07")
def test_a_runner_case_count_above_the_folded_id_count_is_accepted(tmp_path):
    root, sha = make_repo(tmp_path, {**TEST_FILE})
    write_entry(root, cli_block(tests_run=4))  # 4 cases, 2 folded ids
    stage(root, cases=PARAMETRIZED)
    result = check(root, sha)
    assert result.ok, result.detail
    assert "4 passing case(s) in 2 test(s)" in result.detail


@pytest.mark.covers("FR-01.11/AC07")
def test_an_overstated_case_count_is_still_refused(tmp_path):
    root, sha = make_repo(tmp_path, {**TEST_FILE})
    write_entry(root, cli_block(tests_run=5))  # one more than the 4 cases staged
    stage(root, cases=PARAMETRIZED)
    result = check(root, sha)
    assert result.is_failure and "tests_run=5" in result.detail


@pytest.mark.covers("FR-01.11/AC07")
def test_a_failing_case_hides_its_whole_folded_id(tmp_path):
    root, sha = make_repo(tmp_path, {**TEST_FILE})
    write_entry(root, cli_block(tests_run=4))
    stage(root, cases={**PARAMETRIZED, "tests.test_a::test_x[b]": "fail"})
    assert check(root, sha).is_failure


@pytest.mark.covers("FR-01.11/AC07")
def test_a_whole_suite_runner_counts_cases_too(tmp_path):
    root, sha = make_repo(tmp_path, {**TEST_FILE})
    write_entry(root, cli_block(tests_run=4, runner="uv run pytest -q"))  # names no path
    stage(root, cases=PARAMETRIZED)
    result = check(root, sha)
    assert result.ok, result.detail


@pytest.mark.covers("FR-01.11/AC07")
def test_a_partial_retry_replaces_the_count_and_stays_fail_closed(tmp_path):
    root, sha = make_repo(tmp_path, {**TEST_FILE})
    write_entry(root, cli_block(tests_run=4))
    stage(root, cases={**PARAMETRIZED, "tests.test_a::test_x[c]": "fail"},
          retry={"tests.test_a::test_x[c]": "pass"})
    # the retry report holds only [c]: latest-wins credits 1 case for test_x, so 4 is refused
    assert check(root, sha).is_failure
