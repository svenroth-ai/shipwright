"""junit_xml — a HARDENED JUnit results parser (test-health tier 1).

CI JUnit XML is untrusted input (a hostile repo controls its own CI output), so
it is parsed with :mod:`defusedxml` and ``forbid_dtd=True`` — any ``DOCTYPE``/DTD
is rejected outright, which closes both the **XXE** (external-entity) and
**billion-laughs** (internal entity-expansion) classes at once; a legitimate
JUnit document never carries a DOCTYPE (plan §14 A / Gemini #2 / GPT).

Aggregation counts the tests that actually **ran**: ``total = tests - skipped``
(skipped tests are neither pass nor fail), ``passed = total - failures -
errors``. Leaf ``<testsuite>`` elements are summed so a ``<testsuites>`` wrapper
that also carries aggregate attributes cannot double-count.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from defusedxml.common import DefusedXmlException
from defusedxml.ElementTree import ParseError, fromstring

#: Bound a single (possibly hostile) results file.
_MAX_JUNIT_BYTES = 5_000_000
#: Bound how many results files we aggregate.
_MAX_JUNIT_FILES = 50


@dataclass(frozen=True)
class JUnitResult:
    """Passed / ran counts aggregated across one or more JUnit documents."""

    passed: int
    total: int  # tests that actually ran (excludes skipped)


def _int(value: str | None) -> int:
    if value is None:
        return 0
    try:
        return int(float(value))
    except (TypeError, ValueError, OverflowError):
        # OverflowError: a hostile ``tests="inf"`` / huge-digit attribute →
        # ``int(inf)``; must degrade to 0, never propagate and void the parse.
        return 0


def parse_junit(xml_text: str) -> JUnitResult | None:
    """Parse one JUnit document. ``None`` on empty/invalid/DTD-bearing input."""
    if not xml_text or not xml_text.strip():
        return None
    try:
        root = fromstring(
            xml_text, forbid_dtd=True, forbid_entities=True, forbid_external=True)
    except (ParseError, DefusedXmlException, ValueError, TypeError):
        return None

    suites = list(root.iter("testsuite"))
    if root.tag == "testsuite" and root not in suites:  # pragma: no cover
        suites.append(root)
    # Leaf suites only: a suite whose own ``iter`` yields just itself. This
    # avoids double-counting a wrapper suite that also aggregates its children.
    leaves = [s for s in suites if len(list(s.iter("testsuite"))) == 1]
    if not leaves:
        return None

    tests = failures = errors = skipped = 0
    for s in leaves:
        tests += _int(s.get("tests"))
        failures += _int(s.get("failures"))
        errors += _int(s.get("errors"))
        skipped += _int(s.get("skipped")) + _int(s.get("disabled"))

    total_run = tests - skipped
    if total_run <= 0:
        return None
    passed = max(0, total_run - failures - errors)
    return JUnitResult(passed=passed, total=total_run)


def parse_junit_files(paths: list[Path]) -> JUnitResult | None:
    """Aggregate every parseable JUnit file (bounded). ``None`` if none parse."""
    passed = total = 0
    parsed_any = False
    for path in sorted(paths)[:_MAX_JUNIT_FILES]:
        try:
            with path.open("r", encoding="utf-8", errors="replace") as fh:
                text = fh.read(_MAX_JUNIT_BYTES)
        except OSError:
            continue
        try:
            result = parse_junit(text)
        except Exception:
            continue  # one hostile file must never abort the whole aggregation
        if result is not None:
            passed += result.passed
            total += result.total
            parsed_any = True
    if not parsed_any or total <= 0:
        return None
    return JUnitResult(passed=passed, total=total)
