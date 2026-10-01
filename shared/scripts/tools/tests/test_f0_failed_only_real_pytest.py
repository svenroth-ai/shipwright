"""F0 failed-only retry against REAL pytest (xdist first attempt, `--lf` retry).

The unit tests fake `_exec`; this one proves the assumptions they bake in about pytest
itself: the first attempt's `lastfailed` index is written under xdist, `--lf --lfnf=none`
re-selects exactly those tests, `--cov-append` unions the coverage, and the merged JUnit
report keeps the unit's full test count. A temp project with one plugin unit is driven
through the runner's own `run_suite` (real `uv run`), so a drift in how the runner builds
its command or reads the cache fails here rather than on a developer's 20-minute retry.

The tests are deterministic "races": a test that fails the FIRST time it runs (a marker
file in `F0_PROBE_DIR`) and passes afterwards, while every executed test id is appended
as a file - so "only the red tests ran again" is read off the log, not inferred.
"""

from __future__ import annotations

import os
import shutil
import sqlite3
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from scripts.tools import run_test_suite as runner  # noqa: E402
from scripts.tools.suite_units import SuiteConfig  # noqa: E402

if shutil.which("uv") is None:
    if os.environ.get("CI", "").lower() in ("true", "1"):
        pytest.fail("uv is required for the F0 real-pytest probe (install uv: "
                    "https://docs.astral.sh/uv/)", pytrace=False)
    pytest.skip("uv not on PATH - install uv to run the F0 real-pytest probe",
                allow_module_level=True)

UNIT = "shipwright-alpha"
_HEADER = '''
import os, pathlib
D = pathlib.Path(os.environ["F0_PROBE_DIR"])

def log(name):
    # one file per execution: concurrent xdist workers appending to ONE file lose lines
    (D / ("exec-" + name + "-" + os.urandom(4).hex())).write_text("x", encoding="utf-8")

def first_time(name):
    try:
        open(D / ("seen-" + name), "x").close()  # atomic: exactly one caller wins
    except FileExistsError:
        return False
    return True
'''
_OK_TESTS = '''
import only_ok

def test_ok1():
    log("ok1"); assert only_ok.value() == 1

def test_ok2():
    log("ok2")
'''


def _project(tmp_path: Path, tests: dict[str, str]) -> Path:
    root = tmp_path / "proj"
    plugin = root / "plugins" / UNIT
    (plugin / "tests").mkdir(parents=True)
    (plugin / "scripts").mkdir()
    (root / "pyproject.toml").write_text(
        "[tool.coverage.run]\nrelative_files = true\n", encoding="utf-8")
    (plugin / "pyproject.toml").write_text(
        '[project]\nname = "alpha"\nversion = "0"\n'
        '[tool.pytest.ini_options]\npythonpath = ["scripts"]\n', encoding="utf-8")
    (plugin / "scripts" / "only_ok.py").write_text("def value():\n    return 1\n", encoding="utf-8")
    (plugin / "scripts" / "only_flaky.py").write_text("def value():\n    return 2\n", encoding="utf-8")
    for name, body in tests.items():
        (plugin / "tests" / name).write_text(_HEADER + body, encoding="utf-8")
    return root


def _run(root: Path, tmp_path: Path, monkeypatch) -> runner.SuiteResult:
    probe = tmp_path / "probe"
    probe.mkdir()
    monkeypatch.setenv("F0_PROBE_DIR", str(probe))
    config = SuiteConfig(xdist={UNIT: 2}, max_workers=2, timeout_seconds=600)
    return runner.run_suite(root, config, budget_total=2, preflight=False,
                            heartbeat_seconds=60.0, run_id="it-failed-only")


def _executed(tmp_path: Path) -> list[str]:
    probe = tmp_path / "probe"
    return sorted(p.name.split("-")[1] for p in probe.glob("exec-*"))


def _covered_lines(cov_file: Path) -> dict[str, set[int]]:
    """{file basename: executed line numbers} from a coverage data file (numbits blobs)."""
    data = sqlite3.connect(cov_file)
    try:
        rows = data.execute(
            "select f.path, l.numbits from line_bits l join file f on f.id = l.file_id").fetchall()
    finally:
        data.close()
    out: dict[str, set[int]] = {}
    for path, bits in rows:
        lines = {8 * i + j for i, byte in enumerate(bits) for j in range(8) if byte >> j & 1}
        out.setdefault(path.replace("\\", "/").rsplit("/", 1)[-1], set()).update(lines)
    return out


def _retained_report(root: Path) -> ET.Element:
    reports = list((root / ".shipwright" / "runs" / "f0-evidence" / "published").glob("*/reports/*.xml"))
    assert len(reports) == 1, reports
    return ET.parse(reports[0]).getroot()


_TWO_FLAKY = _OK_TESTS + '''
import only_flaky

def test_flaky1():
    log("flaky1"); assert only_flaky.value() == 2
    assert not first_time("flaky1")

def test_flaky2():
    log("flaky2"); assert not first_time("flaky2")
'''


def test_two_red_of_four_rerun_only_the_red_and_the_report_and_coverage_hold(tmp_path, monkeypatch):
    root = _project(tmp_path, {"test_probe.py": _TWO_FLAKY})
    result = _run(root, tmp_path, monkeypatch)
    unit = result.results[0]

    assert (unit.outcome, unit.race, unit.retry_kind) == ("pass", True, "failed-only")
    assert result.exit_code == 0
    executed = _executed(tmp_path)
    assert executed.count("ok1") == executed.count("ok2") == 1, executed   # NOT re-run
    assert executed.count("flaky1") == executed.count("flaky2") == 2, executed

    report = _retained_report(root)
    suite = report.find("testsuite")
    assert suite.get("tests") == "4" and suite.get("failures") == "0"
    assert {c.get("name") for c in report.iter("testcase")} == {
        "test_ok1", "test_ok2", "test_flaky1", "test_flaky2"}

    # `only_ok.py` is imported by tests that did NOT run in the retry: it is in the data
    # file only if the retry APPENDED to the first attempt's coverage instead of erasing it.
    covered = _covered_lines(result.cov_files[0])
    # `only_ok.value()`'s body (line 2) is executed ONLY by the first attempt's green
    # test; it survives the retry only if the retry appended instead of overwriting.
    assert 2 in covered["only_ok.py"], covered
    assert 2 in covered["only_flaky.py"], covered


def test_a_test_still_red_after_the_narrow_retry_keeps_the_unit_red(tmp_path, monkeypatch):
    body = _OK_TESTS + '''
def test_really_broken():
    log("broken"); assert False, "deterministic failure"
'''
    root = _project(tmp_path, {"test_probe.py": body})
    result = _run(root, tmp_path, monkeypatch)
    unit = result.results[0]

    assert (unit.outcome, unit.race, unit.retry_kind) == ("test_failure", False, "failed-only")
    assert result.exit_code == 1
    executed = _executed(tmp_path)
    assert executed.count("ok1") == 1 and executed.count("broken") == 2, executed
    assert "deterministic failure" in unit.output
    suite = _retained_report(root).find("testsuite")
    assert suite.get("tests") == "3" and suite.get("failures") == "1"


def test_failure_in_call_plus_a_teardown_error_is_safe_either_way(tmp_path, monkeypatch):
    """pytest may report this as one testcase or two; the cross-check must either accept
    the narrow retry (counts agree) or fall back whole - never a wrong verdict."""
    body = _OK_TESTS + '''
import pytest

@pytest.fixture
def noisy():
    yield
    if first_time("teardown"):
        raise RuntimeError("teardown boom")

def test_call_and_teardown(noisy):
    log("both")
    assert not first_time("call")
'''
    root = _project(tmp_path, {"test_probe.py": body})
    result = _run(root, tmp_path, monkeypatch)
    unit = result.results[0]

    assert unit.outcome == "pass" and unit.race and result.exit_code == 0
    assert unit.retry_kind in ("failed-only", "serial"), unit.retry_kind
    suite = _retained_report(root).find("testsuite")
    assert suite.get("failures") == "0" and suite.get("errors") == "0"
    assert suite.get("tests") == "3"


def test_a_collection_error_never_leaves_a_stale_error_in_the_retained_report(tmp_path, monkeypatch):
    """Under xdist a collection error is rc 1 with the MODULE as the failed id (probed:
    the narrow retry re-runs that whole module); without xdist it is rc 2 (infra). Either
    shape must end green with the stale error entry gone from the evidence report."""
    body = _OK_TESTS + '''
if first_time("collect"):
    raise ImportError("module not importable on the first attempt")

def test_after_collect():
    log("after")
'''
    root = _project(tmp_path, {"test_probe.py": body})
    result = _run(root, tmp_path, monkeypatch)
    unit = result.results[0]

    assert unit.outcome == "pass" and unit.race and result.exit_code == 0
    assert unit.retry_kind in ("serial", "infra"), unit.retry_kind  # never narrow
    suite = _retained_report(root).find("testsuite")
    assert (suite.get("tests"), suite.get("failures"), suite.get("errors")) == ("3", "0", "0")
