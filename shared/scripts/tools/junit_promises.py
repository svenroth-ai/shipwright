"""Read a pytest JUnit report and hold a converted plugin's promises against it (programme Tz, pilot unit P7).

``test_promises_meta.py`` proves only that the test a promise names *exists*. A promise test that is skipped,
deselected or never collected still reads ``passing`` there. This reader closes that hole from the run's own report:

* ``passing_problems``: every promise whose status is ``passing`` has a test that ran and passed in the report, and a
  promise marked ``failing`` has one that did not;
* ``named_problems``: a list of test ids (the freeze sentinel, the seeded regressions) all ran and passed;
* ``export_trace``: the promise list in the shared AC shape of ``shipwright-skill-check``'s ``trace.json``, statuses
  re-read from the report when one is given.

A node id ``path/to/test_x.py::name`` matches a ``<testcase classname="tests.sub.test_x" name="name">`` (or
``name[param]``) when the module path ends with the class name; the report's rootdir decides how many leading
directories the class name carries, so the match is by suffix. Stdlib only, no Shipwright import.
"""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path

PASSED, FAILED, SKIPPED, MISSING, AMBIGUOUS = "passed", "failed", "skipped", "missing", "ambiguous"


def load_cases(junit_path: Path) -> list[tuple[str, str, str]]:
    """``(classname, name, outcome)`` of every testcase; ``ValueError`` when the file is not a JUnit report."""
    try:
        root = ET.parse(junit_path).getroot()
    except (ET.ParseError, OSError) as exc:
        raise ValueError(f"{junit_path}: not a readable JUnit report ({exc})") from exc
    cases = []
    for case in root.iter("testcase"):
        tags = {child.tag for child in case}
        outcome = FAILED if tags & {"failure", "error"} else SKIPPED if "skipped" in tags else PASSED
        cases.append((case.get("classname", ""), case.get("name", ""), outcome))
    if not cases:
        raise ValueError(f"{junit_path}: the report holds no testcase (a root that collected nothing is not a pass)")
    return cases


def outcome_of(node_id: str, cases: list[tuple[str, str, str]]) -> str:
    """``passed`` only when at least one case matches and every match passed."""
    path, _, name = node_id.partition("::")
    module = path.removesuffix(".py").replace("\\", "/").replace("/", ".")
    hits = [(cls, outcome) for cls, case, outcome in cases
            if cls and (module == cls or module.endswith("." + cls)) and (case == name or case.startswith(name + "["))]
    if not hits:
        return MISSING
    if len({cls for cls, _ in hits}) > 1:
        return AMBIGUOUS  # two different modules end the same way: one could mask the other
    found = [outcome for _, outcome in hits]
    if FAILED in found:
        return FAILED
    return SKIPPED if SKIPPED in found else PASSED


def _test_id(promise: dict) -> str:
    check = promise.get("check") or {}
    return check.get("id", "") if check.get("kind") == "test" else ""


def passing_problems(promises: list[dict], cases: list[tuple[str, str, str]]) -> list[str]:
    problems = []
    for promise in promises:
        node, status = _test_id(promise), promise.get("status")
        if not node or status not in ("passing", "failing"):
            continue
        outcome = outcome_of(node, cases)
        if status == "passing" and outcome != PASSED:
            problems.append(f"{promise['id']}: reads passing, but its test {outcome} in the report ({node})")
        if status == "failing" and outcome == PASSED:
            problems.append(f"{promise['id']}: reads failing, but its test passed in the report ({node})")
    return problems


def named_problems(label: str, node_ids: list[str], cases: list[tuple[str, str, str]]) -> list[str]:
    return [f"{label}: {node} did not run and pass in the report ({outcome_of(node, cases)})"
            for node in node_ids if outcome_of(node, cases) != PASSED]


def export_trace(promise_list: dict, cases: list[tuple[str, str, str]] | None = None) -> dict:
    """The promise list as ``trace.json``; with a report, a ``passing`` or ``failing`` status is the report's verdict."""
    out = {"subject": promise_list["subject"], "schema": promise_list["schema"], "promises": []}
    for promise in promise_list["promises"]:
        item = dict(promise)
        node = _test_id(promise)
        if cases is not None and node and promise.get("status") in ("passing", "failing"):
            item["status"] = {PASSED: "passing", FAILED: "failing"}.get(outcome_of(node, cases), "not-run")
        out["promises"].append(item)
    return out


def dump(trace: dict) -> str:
    return json.dumps(trace, indent=2, ensure_ascii=False) + "\n"
