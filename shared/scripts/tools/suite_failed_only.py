#!/usr/bin/env python3
"""F0 failed-only retry primitives - re-run the red TESTS, not the whole unit.

Measured 2026-10-02 over 146 red unit-attempts: two thirds passed alone (a race) and
a third were real failures with <= 2 red tests, yet the retry re-ran the whole unit
(`shared/tests`: ~22 min). pytest already knows which tests failed: its cache plugin
writes `lastfailed`, and `--lf --lfnf=none` re-selects exactly those. Ids come from
that cache rather than the JUnit report because a JUnit classname maps back to a
node id only lossily (nested classes, parametrize ids, per-unit rootdir).

The one risk is acting on a cache that does not describe the attempt (a crashed
worker, an unreadable file, a collection error). So the retry is only used when the
cache's entry count equals the failed+errored testcases in the attempt's own JUnit
report; anything else falls back to the whole-unit retry the runner always had.

Pure functions plus two small file readers - no subprocess, no runner state.
ASCII-only operator strings (a cp1252 console raises on non-ASCII).
"""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET  # nosec B405 - our own pytest's JUnit file, never remote input
from pathlib import Path

#: the pytest cache's failed-test index, relative to the unit's `-o cache_dir`
LASTFAILED = Path("v") / "cache" / "lastfailed"
#: `--lfnf=none` makes "nothing was selected" a pytest rc 5 (the caller's fallback
#: signal) instead of a whole run
FAILED_ONLY_ARGS = ("--lf", "--lfnf=none")
_BAD = ("failure", "error")


def read_lastfailed(cache_dir: Path) -> set[str] | None:
    """The failed node ids pytest recorded, or None when absent/unreadable."""
    try:
        raw = json.loads((Path(cache_dir) / LASTFAILED).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return {k for k, v in raw.items() if v} if isinstance(raw, dict) else None


def _testcases(root: ET.Element) -> list[ET.Element]:
    return list(root.iter("testcase"))


def _is_bad(case: ET.Element) -> bool:
    return any(case.find(tag) is not None for tag in _BAD)


#: A report larger than this reads as unreadable (the whole-unit fallback), never as data.
_MAX_XML_BYTES = 8 * 1024 * 1024


def _parse(path: Path) -> ET.ElementTree | None:
    """The report as a tree, or None when absent/garbled/oversized/DTD-bearing.

    A DOCTYPE is refused outright (it is the only door to entity expansion and a
    pytest JUnit file never has one), so no XML-hardening dependency is needed.
    """
    try:
        data = Path(path).read_bytes()
        if len(data) > _MAX_XML_BYTES:
            return None
        # Strict UTF-8 text, so the DTD check and the parser see the same characters
        # (a BOM'd UTF-16 DOCTYPE would slip a byte-level substring test).
        text = data.decode("utf-8")
        if "<!DOCTYPE" in text or "<!ENTITY" in text:
            return None
        return ET.ElementTree(ET.fromstring(text))
    except (OSError, UnicodeDecodeError, ET.ParseError):
        return None


def junit_failure_count(report: Path) -> int | None:
    """Testcases carrying a failure/error child (a test failing twice counts once)."""
    tree = _parse(report)
    if tree is None:
        return None
    return sum(_is_bad(c) for c in _testcases(tree.getroot()))


def testcase_count(report: Path) -> int | None:
    """All testcases in a JUnit report, or None when unreadable."""
    tree = _parse(report)
    return None if tree is None else len(_testcases(tree.getroot()))


def junit_has_error(report: Path) -> bool:
    """True when any testcase carries an <error> (setup/teardown/collection), not a <failure>.

    pytest reports a module/session fixture's teardown error against whichever test ran
    LAST, which may not use the fixture: re-running that test alone never sets the fixture
    up, so a deterministic red would read green. Errors therefore never go narrow.
    """
    tree = _parse(report)
    return tree is None or any(c.find("error") is not None for c in _testcases(tree.getroot()))


def failed_only_count(cache_dir: Path, report: Path) -> int:
    """The red-test count when the cache and the JUnit report agree on it, else 0.

    0 means "do not trust the cache": absent/unreadable, a count mismatch, no failing
    testcase at all (a session-level red the narrow retry could not reproduce), or a
    COLLECTION error (an id without `::` names a module, not a test): collection aborts
    the run, so the unit's other modules never executed and re-running one proves nothing.
    """
    failed = read_lastfailed(cache_dir)
    if failed and any("::" not in node for node in failed):
        return 0
    if junit_has_error(report):
        return 0
    count = junit_failure_count(report)
    return len(failed) if failed and count is not None and len(failed) == count else 0


def failed_only_args(unit) -> tuple[str, ...]:
    """`--cov-append` only for an instrumented unit: pytest rejects it without pytest-cov."""
    return (*FAILED_ONLY_ARGS, "--cov-append") if unit.cov_args else FAILED_ONLY_ARGS


def _key(case: ET.Element) -> tuple[str, str]:
    return (case.get("classname", ""), case.get("name", ""))


def same_tests(saved: Path, rerun: Path) -> bool:
    """The re-run executed exactly the saved report's red testcases, by identity - an equal
    COUNT of different tests (renamed, parametrized differently) is not a resume."""
    old, new = _parse(saved), _parse(rerun)
    if old is None or new is None:
        return False
    red = {_key(c) for c in _testcases(old.getroot()) if _is_bad(c)}
    return bool(red) and red == {_key(c) for c in _testcases(new.getroot())}


def merge_junit(base: Path, rerun: Path, out: Path) -> bool:
    """Write `out` = base's testcases minus the re-run ones, plus the re-run ones.

    A failed-only retry re-ran every red test of the base report (the caller checks the
    re-run is at least that large), so every base failure is replaced; a collection-error
    entry has no counterpart by key once the module collects, which is why failures are
    dropped wholesale rather than matched. On a key collision the re-run wins.
    """
    base_tree, new_tree = _parse(base), _parse(rerun)
    if base_tree is None or new_tree is None:
        return False
    new_cases = _testcases(new_tree.getroot())
    replaced = {_key(c) for c in new_cases}
    suites = list(base_tree.getroot().iter("testsuite")) or [base_tree.getroot()]
    if len(suites) > 1:  # totals are recomputed on ONE suite: never guess for a multi-suite report
        return False
    suite = suites[0]
    for parent in suites:
        for case in _testcases(parent):
            if _key(case) in replaced or _is_bad(case):
                parent.remove(case)
    for case in new_cases:
        suite.append(case)
    cases = _testcases(base_tree.getroot())
    suite.set("tests", str(len(cases)))
    suite.set("failures", str(sum(c.find("failure") is not None for c in cases)))
    suite.set("errors", str(sum(c.find("error") is not None for c in cases)))
    suite.set("skipped", str(sum(c.find("skipped") is not None for c in cases)))
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        base_tree.write(out, encoding="utf-8", xml_declaration=True)
    except OSError:
        return False
    return True
