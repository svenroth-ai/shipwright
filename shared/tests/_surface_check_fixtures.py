"""Real-git + real-staging fixtures for the ``check_surface_verification`` tests.

The gate re-derives the branch diff itself and reads the evidence a real
``evidence_drop.stage_reports`` call staged, so neither is faked here: the repo
comes from ``_cascade_trigger_fixtures.make_repo`` (trunk ``main`` +
``origin/main``, one branch commit) and the evidence is staged through the
production emit-side, provenance sidecar included.
"""

from __future__ import annotations

import json
from pathlib import Path

from _cascade_trigger_fixtures import git
from lib import evidence_drop
from tools.verifiers.surface_check import check_surface_verification

RUN = "iterate-2026-10-08-surface-probe"
NONE_BLOCK = {"surface": "none", "runner": "", "exit_code": 0, "tests_run": 0,
              "evidence_path": "", "timestamp": "now", "reason_code": "docs-only",
              "justification": "prose-only change, nothing to start"}


def cli_block(tests_run: int = 2, runner: str = "uv run pytest tests/test_a.py -q") -> dict:
    return {"surface": "cli", "runner": runner, "exit_code": 0, "tests_run": tests_run,
            "evidence_path": "log.txt", "timestamp": "now"}


def write_entry(root: Path, block: dict | None, complexity: str = "medium") -> None:
    """The run's F5c entry, carrying its F0.5 block (untracked, as at F11)."""
    iterates = root / ".shipwright" / "agent_docs" / "iterates"
    iterates.mkdir(parents=True, exist_ok=True)
    entry: dict = {"run_id": RUN, "complexity": complexity}
    if block is not None:
        entry["surface_verification"] = block
    (iterates / f"{RUN}.json").write_text(json.dumps(entry), encoding="utf-8")


def junit(cases: dict[str, str]) -> str:
    """A pytest-shaped JUnit report: ``{"tests.test_a::test_x": "pass"|"fail"|"skip"}``."""
    body = []
    for case, outcome in cases.items():
        classname, name = case.split("::")
        child = {"fail": "<failure message='x'/>", "skip": "<skipped/>"}.get(outcome, "")
        body.append(f'<testcase classname="{classname}" name="{name}">{child}</testcase>')
    return f'<testsuites><testsuite name="pytest">{"".join(body)}</testsuite></testsuites>'


def playwright(titles: list[str], file: str = "e2e/board.spec.ts") -> dict:
    specs = [{"title": t, "tests": [{"status": "expected", "results": [{"status": "passed"}]}]}
             for t in titles]
    return {"suites": [{"file": file, "specs": specs}]}


def stage(root: Path, *, run_id: str = RUN, head: str | None = None,
          cases: dict[str, str] | None = None, pw: dict | None = None) -> None:
    """Stage reports through the production emit-side; ``head`` defaults to the trunk tip."""
    reports = root.parent / "reports"
    reports.mkdir(exist_ok=True)
    junit_path = reports / "junit.xml"
    junit_path.write_text(junit(cases if cases is not None else
                                {"tests.test_a::test_x": "pass", "tests.test_a::test_y": "pass"}),
                          encoding="utf-8")
    pw_path = None
    if pw is not None:
        pw_path = reports / "playwright.json"
        pw_path.write_text(json.dumps(pw), encoding="utf-8")
    evidence_drop.stage_reports(root, run_id=run_id,
                                head_commit=head if head is not None else git(root, "rev-parse", "main"),
                                junit_reports=[("", junit_path)], playwright=pw_path)


def check(root: Path, commit: str = ""):
    return check_surface_verification(root, RUN, commit)
