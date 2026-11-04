"""Fixtures for the ``surface=native`` tests (#989): native/web package manifests, Jest and JUnit reports.

Real git repos (``_cascade_trigger_fixtures``) and the production staging path
(``evidence_drop.stage_reports``); nothing here fakes the verifier.
"""

from __future__ import annotations

import json
from pathlib import Path

from _cascade_trigger_fixtures import git, make_repo
from _surface_check_fixtures import RUN, cli_block, write_entry
from lib import evidence_drop

NATIVE_PKG = json.dumps({"name": "mobile", "dependencies": {"expo": "~52.0.0", "react-native": "0.76.0"}})
WEB_PKG = json.dumps({"name": "web", "dependencies": {"react": "19", "react-dom": "19", "next": "15"}})
UNIVERSAL_PKG = json.dumps({"name": "uni", "dependencies": {"expo": "~52", "react-native": "0.76", "react-dom": "19"}})
# the stock create-expo-app template: react-dom comes WITH react-native-web
STOCK_EXPO_PKG = json.dumps({"name": "stock", "dependencies": {
    "expo": "~52", "react": "18.3.1", "react-dom": "18.3.1", "react-native": "0.76", "react-native-web": "~0.19"}})
APP = "apps/mobile"
FILES = {f"{APP}/package.json": NATIVE_PKG, f"{APP}/src/Photo.tsx": "x\n", f"{APP}/src/Photo.test.tsx": "x\n"}


def native_block(tests_run: int = 2, runner: str = "npx jest apps/mobile") -> dict:
    return {**cli_block(tests_run=tests_run, runner=runner), "surface": "native"}


def jest_json(root: Path, results: dict[str, list[str]]) -> dict:
    """Jest ``--json`` shape: ABSOLUTE ``name`` per test file, one ``assertionResults`` entry per case."""
    return {"testResults": [
        {"name": str(root / rel), "assertionResults": [{"title": t, "status": "passed"} for t in titles]}
        for rel, titles in results.items()]}


def junit_xml(cases: list[tuple[str, str, str]]) -> str:
    """JUnit with the ``file`` attribute jest-junit emits under ``addFileAttribute``: ``(file, name, outcome)``."""
    body = []
    for file, name, outcome in cases:
        child = {"fail": "<failure message='x'/>"}.get(outcome, "")
        body.append(f'<testcase classname="c" name="{name}" file="{file}">{child}</testcase>')
    return f'<testsuites><testsuite name="jest">{"".join(body)}</testsuite></testsuites>'


def stage_native(root: Path, *, jest: dict | None = None, junit: list[tuple[str, list[tuple[str, str, str]]]] = (),
                 head: str | None = None) -> None:
    """Stage a Jest JSON report and/or JUnit reports (``[(base, cases)]``) through the production emit-side."""
    reports = root.parent / "reports"
    reports.mkdir(exist_ok=True)
    junit_reports = []
    for i, (base, cases) in enumerate(junit):
        path = reports / f"junit-{i}.xml"
        path.write_text(junit_xml(cases), encoding="utf-8")
        junit_reports.append((base, path))
    jest_path = None
    if jest is not None:
        jest_path = reports / "jest.json"
        jest_path.write_text(json.dumps(jest), encoding="utf-8")
    evidence_drop.stage_reports(root, run_id=RUN, head_commit=head or git(root, "rev-parse", "main"),
                                junit_reports=junit_reports, vitest=jest_path)


def native_repo(tmp_path: Path, extra: dict[str, str] | None = None) -> tuple[Path, str]:
    root, sha = make_repo(tmp_path, {**FILES, **(extra or {})})
    write_entry(root, native_block())
    return root, sha
