"""`suite_failed_only` - the primitives behind the failed-only retry.

The cache/JUnit cross-check is the whole safety argument: a retry on the red tests is
only taken when pytest's own failed-test index provably describes the attempt, so every
doubt below must come out False (= the whole-unit retry the runner always had).
"""

from __future__ import annotations

import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

import scripts.tools.suite_failed_only as fo
from scripts.tools.run_test_suite import build_command, discover_units


def _junit(path: Path, cases: list[tuple[str, str, str | None]]) -> Path:
    """cases: (classname, name, None | 'failure' | 'error' | 'both' | 'skipped')."""
    suite = ET.Element("testsuite", name="pytest")
    for cls, name, kind in cases:
        case = ET.SubElement(suite, "testcase", classname=cls, name=name)
        for tag in {"both": ("failure", "error")}.get(kind, (kind,) if kind else ()):
            ET.SubElement(case, tag, message="x")
    root = ET.Element("testsuites")
    root.append(suite)
    ET.ElementTree(root).write(path, encoding="utf-8")
    return path


def _cache(tmp_path: Path, ids: dict[str, bool] | str | None) -> Path:
    cache = tmp_path / "c"
    if ids is not None:
        target = cache / fo.LASTFAILED
        target.parent.mkdir(parents=True)
        target.write_text(ids if isinstance(ids, str) else json.dumps(ids), encoding="utf-8")
    return cache


def test_read_lastfailed_keeps_only_true_entries(tmp_path):
    cache = _cache(tmp_path, {"t.py::a": True, "t.py::b": False})
    assert fo.read_lastfailed(cache) == {"t.py::a"}


def test_read_lastfailed_is_none_when_absent_or_garbage(tmp_path):
    assert fo.read_lastfailed(_cache(tmp_path, None)) is None
    assert fo.read_lastfailed(_cache(tmp_path / "x", "{not json")) is None
    assert fo.read_lastfailed(_cache(tmp_path / "y", "[1, 2]")) is None


def test_junit_failure_count_counts_a_testcase_once_even_with_two_children(tmp_path):
    report = _junit(tmp_path / "r.xml", [("C", "a", "both"), ("C", "b", "error"),
                                          ("C", "c", "failure"), ("C", "d", None),
                                          ("C", "e", "skipped")])
    assert fo.junit_failure_count(report) == 3


def test_junit_failure_count_is_none_for_unreadable_report(tmp_path):
    bad = tmp_path / "r.xml"
    bad.write_text("<testsuite", encoding="utf-8")
    assert fo.junit_failure_count(bad) is None
    assert fo.junit_failure_count(tmp_path / "missing.xml") is None


def test_failed_only_count_requires_cache_and_report_to_agree(tmp_path):
    report = _junit(tmp_path / "r.xml", [("C", "a", "failure"), ("C", "b", "failure"),
                                          ("C", "c", None)])
    assert fo.failed_only_count(_cache(tmp_path, {"t::a": True, "t::b": True}), report) == 2
    # count mismatch either way, an empty index, a missing cache and a missing report
    assert fo.failed_only_count(_cache(tmp_path / "1", {"t::a": True}), report) == 0
    assert fo.failed_only_count(
        _cache(tmp_path / "2", {"a": True, "b": True, "c": True}), report) == 0
    assert fo.failed_only_count(_cache(tmp_path / "3", {}), report) == 0
    assert fo.failed_only_count(_cache(tmp_path / "4", None), report) == 0
    assert fo.failed_only_count(_cache(tmp_path / "5", {"a": True, "b": True}),
                                tmp_path / "gone.xml") == 0


def test_failed_only_count_is_zero_when_the_report_has_no_failures(tmp_path):
    """rc 1 with zero failing testcases = a session-level red (collection, plugin) - the
    narrow retry could not reproduce it, so it must not be taken."""
    report = _junit(tmp_path / "r.xml", [("C", "a", None)])
    assert fo.failed_only_count(_cache(tmp_path, {"t::a": True}), report) == 0


def test_failed_only_count_is_zero_for_a_collection_error(tmp_path):
    """A module id (no `::`) is a collection error: the unit's other modules never ran."""
    report = _junit(tmp_path / "r.xml", [("", "tests/test_m.py", "error"), ("C", "ok", None)])
    assert fo.failed_only_count(_cache(tmp_path, {"tests/test_m.py": True}), report) == 0


def test_failed_only_count_is_zero_when_any_red_testcase_is_an_error(tmp_path):
    """A teardown error is reported against the LAST test, which may not use the fixture."""
    report = _junit(tmp_path / "r.xml", [("C", "last", "error"), ("C", "ok", None)])
    assert fo.failed_only_count(_cache(tmp_path, {"t.py::last": True}), report) == 0


def test_testcase_count_counts_all_cases_and_is_none_when_unreadable(tmp_path):
    report = _junit(tmp_path / "r.xml", [("C", "a", "failure"), ("C", "b", None)])
    assert fo.testcase_count(report) == 2
    assert fo.testcase_count(tmp_path / "missing.xml") is None


def test_failed_only_args_append_coverage_only_for_an_instrumented_unit():
    from types import SimpleNamespace
    assert fo.failed_only_args(SimpleNamespace(cov_args=("--cov=x",))) == (
        *fo.FAILED_ONLY_ARGS, "--cov-append")
    assert fo.failed_only_args(SimpleNamespace(cov_args=())) == fo.FAILED_ONLY_ARGS


def test_merge_replaces_failures_and_recomputes_the_suite_totals(tmp_path):
    base = _junit(tmp_path / "base.xml", [("C", "ok", None), ("C", "bad", "failure"),
                                           ("C", "skip", "skipped"), ("C", "bad2", "error")])
    rerun = _junit(tmp_path / "rerun.xml", [("C", "bad", None), ("C", "bad2", None)])
    out = tmp_path / "m" / "merged.xml"
    assert fo.merge_junit(base, rerun, out)
    suite = ET.parse(out).getroot().find("testsuite")
    names = sorted(c.get("name") for c in suite.iter("testcase"))
    assert names == ["bad", "bad2", "ok", "skip"]
    assert (suite.get("tests"), suite.get("failures"), suite.get("errors"),
            suite.get("skipped")) == ("4", "0", "0", "1")
    assert fo.junit_failure_count(out) == 0


def test_merge_keeps_a_still_red_retest_red(tmp_path):
    base = _junit(tmp_path / "base.xml", [("C", "ok", None), ("C", "bad", "failure")])
    rerun = _junit(tmp_path / "rerun.xml", [("C", "bad", "failure")])
    out = tmp_path / "merged.xml"
    assert fo.merge_junit(base, rerun, out)
    assert fo.junit_failure_count(out) == 1
    assert ET.parse(out).getroot().find("testsuite").get("tests") == "2"


def test_merge_drops_a_collection_error_entry_that_has_no_counterpart_by_key(tmp_path):
    """The module failed to collect (error entry named by path); after the fix its real
    tests appear under real names - the stale error must not survive the merge."""
    base = _junit(tmp_path / "base.xml", [("", "tests/test_m.py", "error"), ("C", "ok", None)])
    rerun = _junit(tmp_path / "rerun.xml", [("tests.test_m", "t1", None), ("tests.test_m", "t2", None)])
    out = tmp_path / "merged.xml"
    assert fo.merge_junit(base, rerun, out)
    assert fo.junit_failure_count(out) == 0
    assert ET.parse(out).getroot().find("testsuite").get("tests") == "3"


def test_merge_on_key_collision_the_retry_wins_and_totals_do_not_double_count(tmp_path):
    base = _junit(tmp_path / "base.xml", [("C", "dup", None), ("C", "bad", "failure")])
    rerun = _junit(tmp_path / "rerun.xml", [("C", "dup", "failure")])
    out = tmp_path / "merged.xml"
    assert fo.merge_junit(base, rerun, out)
    cases = list(ET.parse(out).getroot().iter("testcase"))
    assert [(c.get("name"), c.find("failure") is not None) for c in cases] == [("dup", True)]


def test_merge_refuses_unreadable_input_and_unwritable_output(tmp_path):
    good = _junit(tmp_path / "g.xml", [("C", "a", None)])
    bad = tmp_path / "bad.xml"
    bad.write_text("nope", encoding="utf-8")
    assert not fo.merge_junit(good, bad, tmp_path / "o.xml")
    assert not fo.merge_junit(bad, good, tmp_path / "o.xml")
    assert not fo.merge_junit(good, tmp_path / "missing.xml", tmp_path / "o.xml")
    blocker = tmp_path / "blocker"
    blocker.write_text("file, not a dir", encoding="utf-8")
    assert not fo.merge_junit(good, good, blocker / "o.xml")


def test_build_command_default_is_unchanged_and_cache_dir_replaces_the_disable_flag(tmp_path):
    root = tmp_path
    (root / "plugins" / "p" / "tests").mkdir(parents=True)
    (root / "plugins" / "p" / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    unit = discover_units(root)[0]
    plain = build_command(unit, None)
    assert plain[plain.index("-q") + 1:plain.index("-q") + 3] == ["-p", "no:cacheprovider"]
    assert "cache_dir" not in " ".join(plain)
    cached = build_command(unit, None, cache_dir=tmp_path / "c",
                           extra_args=(*fo.FAILED_ONLY_ARGS, "--cov-append"))
    assert "no:cacheprovider" not in cached
    assert cached[cached.index("-o") + 1] == f"cache_dir={tmp_path / 'c'}"
    assert cached[-3:] == ["--lf", "--lfnf=none", "--cov-append"]
