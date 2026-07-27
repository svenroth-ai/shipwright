"""End-to-end: the F0 runner records a race that outlives the run.

iterate-2026-07-27-f0-race-triage. Every other test for this feature stubs something
- the suite result, the triage API, or `run_suite` itself. This one stubs nothing: it
builds a throwaway project containing a genuinely unreliable test unit (fails on its
first run, passes on its second) and invokes the REAL
`shared/scripts/tools/run_test_suite.py` as a subprocess, so the whole production path
runs - discovery, `uv`, the parallel pass, the JUnit-proven classification, the
authoritative alone re-run, the triage append, the console block and the exit code.

It exists because the single design decision most likely to be wrong is invisible to a
unit test: the card must survive a LATER CLEAN RUN. A race is intermittent, so the
common case is a green parallel pass - a producer that auto-dismissed on that would
look correct in every unit test and still lose the record one iterate later, which is
the exact failure this feature closes.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]
_RUNNER = _REPO / "shared" / "scripts" / "tools" / "run_test_suite.py"

_FLAKY_UNIT = '''import pathlib

MARK = pathlib.Path(__file__).resolve().parents[3] / "ran_once.marker"


def test_unreliable_unit():
    if MARK.exists():
        return
    MARK.write_text("x", encoding="utf-8")
    raise AssertionError("first run fails, like a unit losing a race")
'''


def _uv_available() -> bool:
    return shutil.which("uv") is not None


@pytest.fixture
def project(tmp_path: Path) -> Path:
    unit = tmp_path / "plugins" / "shipwright-alpha"
    (unit / "tests").mkdir(parents=True)
    (tmp_path / "shipwright_test_config.json").write_text(
        json.dumps({"suite": {}}), encoding="utf-8")
    (unit / "pyproject.toml").write_text(
        '[project]\nname = "alpha"\nversion = "0.0.0"\n', encoding="utf-8")
    (unit / "tests" / "test_unreliable.py").write_text(_FLAKY_UNIT, encoding="utf-8")
    return tmp_path


def _run_f0(project_root: Path) -> subprocess.CompletedProcess:
    return subprocess.run(  # noqa: S603 - fixed argv, shell=False
        [sys.executable, str(_RUNNER), "--project-root", str(project_root),
         "--run-id", "iterate-e2e-race"],
        cwd=str(_REPO), capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=900, shell=False,
    )


def _cards(project_root: Path) -> list[dict]:
    store = project_root / ".shipwright" / "triage.jsonl"
    if not store.is_file():
        return []
    rows = [json.loads(x) for x in store.read_text(encoding="utf-8").splitlines() if x]
    return [r for r in rows if r.get("event") == "append"]


def test_the_runner_records_a_real_race_and_never_auto_closes_it(project: Path) -> None:
    if not _uv_available():
        if os.environ.get("CI", "").lower() in ("true", "1"):
            pytest.fail("uv is required in CI: https://docs.astral.sh/uv/getting-started/")
        pytest.skip("uv not installed; the F0 runner cannot spawn its units")

    # Run 1 - the unit is red in parallel, green when re-run alone.
    first = _run_f0(project)
    assert first.returncode == 0, f"a race must not stop the gate:\n{first.stdout}"

    card, = _cards(project)
    assert card["source"] == "f0-suite" and card["severity"] == "high"
    assert card["dedupKey"] == "f0-race:shipwright-alpha"
    assert card["runId"] == "iterate-e2e-race" and card["status"] == "triage"
    assert f"Tracked as {card['id']}" in first.stdout, \
        "the console must hand the operator the durable handle, not just a warning"

    # The published log carries the measured facts and NONE of the test output.
    raw = (project / ".shipwright" / "triage.jsonl").read_text(encoding="utf-8")
    assert "red in parallel" in raw
    assert "AssertionError" not in raw and "short test summary" not in raw

    # Run 2 - the unit now passes in parallel. The card MUST survive: one clean run
    # is not evidence the race is gone.
    second = _run_f0(project)
    assert second.returncode == 0
    still_open, = _cards(project)
    assert still_open["id"] == card["id"] and still_open["status"] == "triage"

    # Run 3 - it races again. Still exactly one card, and the same one.
    (project / "ran_once.marker").unlink()
    third = _run_f0(project)
    assert third.returncode == 0
    assert [c["id"] for c in _cards(project)] == [card["id"]]
    assert f"Tracked as {card['id']}" in third.stdout
