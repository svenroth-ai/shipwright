"""Read a pytest JUnit report and hold a converted plugin's promises against it (programme Tz, pilot unit P7).

``test_promises_meta.py`` proves only that the test a promise names *exists*. A promise test that is skipped,
deselected or never collected still reads ``passing`` there. This reader closes that hole from the run's own report:

* ``passing_problems``: a ``passing`` promise needs its main check AND every ``more_checks`` test to have run and
  passed, and must name a test check at all; a ``failing`` promise needs at least one of them not to pass;
* ``named_problems``: a list of test ids (the freeze sentinel, the seeded regressions) all ran and passed;
* ``export_trace``: the promise list in the shared AC shape of ``shipwright-skill-check``'s ``trace.json``.

A node id ``path/to/test_x.py::name`` matches a ``<testcase classname="tests.sub.test_x" name="name">`` (or
``name[param]``) when the module path ends with the class name; the report's rootdir decides how many leading
directories the class name carries, so the match is by suffix, and two different modules ending the same way read
``ambiguous``. Stdlib only, no Shipwright import.

Limits, on purpose: (1) a report is not bound to a commit, so a stale report passes: the operator produces it at the
tree under test; (2) ``Class::name`` node ids (a test inside a class) are not matched and read ``missing``: the
promise tests are module-level functions; (3) re-labelling a non-passing promise (``gap``, ``not-run``) is not
checked here: only a review of the promise list guards that.
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


def _test_ids(promise: dict) -> list[str]:
    """The ids of every test check of a promise: the main check first, then ``more_checks``."""
    checks = [promise.get("check"), *(promise.get("more_checks") or [])]
    return [c["id"] for c in checks if c and c.get("kind") == "test" and c.get("id")]


def passing_problems(promises: list[dict], cases: list[tuple[str, str, str]]) -> list[str]:
    problems = []
    for promise in promises:
        status = promise.get("status")
        if status not in ("passing", "failing"):
            continue
        nodes = _test_ids(promise)
        if status == "passing" and not nodes:
            problems.append(f"{promise['id']}: reads passing, but names no test check")
            continue
        outcomes = [(node, outcome_of(node, cases)) for node in nodes]
        if status == "passing":
            problems += [f"{promise['id']}: reads passing, but its test {outcome} in the report ({node})"
                         for node, outcome in outcomes if outcome != PASSED]
        elif outcomes and all(outcome == PASSED for _, outcome in outcomes):
            problems.append(f"{promise['id']}: reads failing, but its test passed in the report ({outcomes[0][0]})")
    return problems


def named_problems(label: str, node_ids: list[str], cases: list[tuple[str, str, str]]) -> list[str]:
    return [f"{label}: {node} did not run and pass in the report ({outcome_of(node, cases)})"
            for node in node_ids if outcome_of(node, cases) != PASSED]


def export_trace(promise_list: dict) -> dict:
    """The promise list as ``trace.json``: the same promises, the same statuses."""
    return {"subject": promise_list["subject"], "schema": promise_list["schema"],
            "promises": [dict(promise) for promise in promise_list["promises"]]}


def dump(trace: dict) -> str:
    return json.dumps(trace, indent=2, ensure_ascii=False) + "\n"
