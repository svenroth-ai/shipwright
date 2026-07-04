"""Tests for junit_xml — the hardened JUnit parser (test-health tier 1).

Covers aggregation semantics AND the untrusted-input hardening: a DTD-bearing
document (the XXE and billion-laughs attack surface) must be rejected to ``None``
without a crash and without expanding anything.
"""

from __future__ import annotations

from junit_xml import JUnitResult, parse_junit, parse_junit_files

_FLAT = (
    '<testsuite name="s" tests="10" failures="2" errors="1" skipped="1">'
    "</testsuite>"
)
_WRAPPED = (
    '<testsuites>'
    '<testsuite name="a" tests="4" failures="0" errors="0" skipped="0"/>'
    '<testsuite name="b" tests="6" failures="3" errors="0" skipped="1"/>'
    '</testsuites>'
)
# A wrapper testsuite that also nests child suites carrying the real counts.
_NESTED = (
    '<testsuite name="root" tests="10" failures="5">'
    '<testsuite name="child" tests="10" failures="1" skipped="0"/>'
    '</testsuite>'
)


def test_flat_suite_counts_runs_excluding_skipped():
    r = parse_junit(_FLAT)
    # total = 10 - 1 skipped = 9; passed = 9 - 2 failures - 1 error = 6.
    assert (r.passed, r.total) == (6, 9)


def test_wrapped_suites_summed():
    r = parse_junit(_WRAPPED)
    # a: 4 run, 4 pass; b: 5 run (6-1 skip), 2 pass (5-3) -> 6 pass / 9 run.
    assert (r.passed, r.total) == (6, 9)


def test_nested_suites_not_double_counted():
    r = parse_junit(_NESTED)
    # Only the leaf child (tests=10, failures=1) is summed, not the wrapper.
    assert (r.passed, r.total) == (9, 10)


def test_all_skipped_is_none():
    assert parse_junit('<testsuite tests="3" skipped="3"/>') is None


def test_empty_and_invalid_are_none():
    assert parse_junit("") is None
    assert parse_junit("   ") is None
    assert parse_junit("not xml <<<") is None
    assert parse_junit("<other/>") is None


def test_xxe_external_entity_rejected(tmp_path):
    secret = tmp_path / "secret.txt"
    secret.write_text("TOP-SECRET", encoding="utf-8")
    payload = (
        '<?xml version="1.0"?>'
        f'<!DOCTYPE t [<!ENTITY xxe SYSTEM "file://{secret.as_posix()}">]>'
        '<testsuite name="&xxe;" tests="1" failures="0"/>'
    )
    # Rejected to None (DTD forbidden) — no crash, and the secret is never read.
    assert parse_junit(payload) is None


def test_entity_expansion_bomb_rejected():
    # The classic "billion-laughs" internal-entity-expansion DoS.
    payload = (
        '<?xml version="1.0"?>'
        '<!DOCTYPE lolz [<!ENTITY lol "lol">'
        '<!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;">'
        '<!ENTITY lol3 "&lol2;&lol2;&lol2;&lol2;&lol2;">]>'
        '<testsuite tests="1">&lol3;</testsuite>'
    )
    assert parse_junit(payload) is None


def test_parse_files_aggregates_and_skips_invalid(tmp_path):
    good = tmp_path / "a.xml"
    good.write_text('<testsuite tests="5" failures="1"/>', encoding="utf-8")
    bad = tmp_path / "b.xml"
    bad.write_text("garbage", encoding="utf-8")
    other = tmp_path / "c.xml"
    other.write_text('<testsuite tests="3" failures="0"/>', encoding="utf-8")
    r = parse_junit_files([good, bad, other])
    assert (r.passed, r.total) == (4 + 3, 5 + 3)


def test_parse_files_all_invalid_is_none(tmp_path):
    bad = tmp_path / "b.xml"
    bad.write_text("nope", encoding="utf-8")
    assert parse_junit_files([bad]) is None


def test_infinity_attribute_degrades_to_zero_not_crash():
    # A hostile ``tests="inf"`` must not raise OverflowError (reviewer finding #2):
    # the suite degrades to 0 tests -> None, never propagating up to void parsing.
    assert parse_junit('<testsuite tests="inf" failures="0"/>') is None
    assert parse_junit('<testsuite tests="' + "9" * 400 + '" failures="0"/>') is None


def test_poisoned_file_does_not_abort_aggregation(tmp_path):
    good = tmp_path / "a.xml"
    good.write_text('<testsuite tests="5" failures="1"/>', encoding="utf-8")
    poison = tmp_path / "z.xml"
    poison.write_text('<testsuite tests="inf" failures="0"/>', encoding="utf-8")
    # The good file's real ratio must survive one poisoned sibling.
    assert parse_junit_files([good, poison]) == JUnitResult(passed=4, total=5)
