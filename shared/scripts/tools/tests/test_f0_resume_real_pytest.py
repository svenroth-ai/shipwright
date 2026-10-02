"""F0 cross-invocation resume against REAL pytest and a REAL git checkout.

The unit tests fake `_exec`; this one proves the assumptions they bake in: a red run
leaves state, the NEXT `run_suite` (after the "fix") re-runs only the red test via `--lf`
against the restored `lastfailed`, a green unit is not re-run at all, the consolidated
report keeps the whole unit's testcase total, coverage of an UNCHANGED file survives the
restore while an edited file's is rebuilt, and the retained manifest says `resumed`.

"Only the red test ran" is read off per-execution marker files, never inferred. The temp
project is a git repo with an `origin/main` ref: the resume keys its lineage on the merge
base with it, exactly as it does in a real worktree.
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from scripts.tools import run_test_suite as runner  # noqa: E402
from scripts.tools.suite_resume import ENV_OFF  # noqa: E402
from scripts.tools.suite_resume_state import NO_STATE, load_state  # noqa: E402
from scripts.tools.suite_units import SuiteConfig  # noqa: E402

if shutil.which("uv") is None or shutil.which("git") is None:
    if os.environ.get("CI", "").lower() in ("true", "1"):
        pytest.fail("uv and git are required for the F0 resume probe", pytrace=False)
    pytest.skip("uv or git not on PATH", allow_module_level=True)

_HEADER = '''
import os, pathlib
D = pathlib.Path(os.environ["F0_PROBE_DIR"])

def log(name):
    (D / ("exec-" + name + "-" + os.urandom(4).hex())).write_text("x", encoding="utf-8")
'''
_GREEN = '''
import lib_a

def test_green1():
    log("green1"); assert lib_a.value() == 1

def test_green2():
    log("green2")
'''
_NEEDS_FIX = '''
import lib_b

def test_needs_fix():
    log("needs_fix"); assert lib_b.value() == 3

def test_ok_b():
    log("ok_b")
'''
_GIT_ENV = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
            "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=str(root), env=_GIT_ENV, capture_output=True,
                   text=True, check=True)


def _plugin(root: Path, name: str, tests: dict[str, str], libs: dict[str, str]) -> None:
    plugin = root / "plugins" / name
    (plugin / "tests").mkdir(parents=True)
    (plugin / "scripts").mkdir()
    (plugin / "pyproject.toml").write_text(
        f'[project]\nname = "{name}"\nversion = "0"\n'
        '[tool.pytest.ini_options]\npythonpath = ["scripts"]\n', encoding="utf-8")
    for fname, body in libs.items():
        (plugin / "scripts" / fname).write_text(body, encoding="utf-8")
    for fname, body in tests.items():
        (plugin / "tests" / fname).write_text(_HEADER + body, encoding="utf-8")


def _project(tmp_path: Path) -> Path:
    """`shipwright-alpha` is green, `shipwright-beta` is red until `lib_b` is fixed."""
    root = tmp_path / "proj"
    root.mkdir()
    (root / "pyproject.toml").write_text(
        "[tool.coverage.run]\nrelative_files = true\n", encoding="utf-8")
    (root / ".gitignore").write_text(
        ".shipwright/\n.cov-data/\n.coverage*\ncoverage.xml\n__pycache__/\n.venv/\n"
        "uv.lock\n.pytest_cache/\n", encoding="utf-8")
    _plugin(root, "shipwright-alpha", {"test_a.py": _GREEN},
            {"lib_a.py": "def value():\n    return 1\n"})
    _plugin(root, "shipwright-beta", {"test_b.py": _NEEDS_FIX},
            {"lib_b.py": "def value():\n    unused = 1\n    return 2\n"})
    _git(root, "init", "-q")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "base")
    _git(root, "update-ref", "refs/remotes/origin/main", "HEAD")
    return root


def _fix(root: Path) -> None:
    (root / "plugins" / "shipwright-beta" / "scripts" / "lib_b.py").write_text(
        "def value():\n    return 3\n", encoding="utf-8")


def _run(root: Path, tmp_path: Path, monkeypatch, **kw) -> runner.SuiteResult:
    probe = tmp_path / "probe"
    probe.mkdir(exist_ok=True)
    monkeypatch.setenv("F0_PROBE_DIR", str(probe))
    monkeypatch.delenv(ENV_OFF, raising=False)
    return runner.run_suite(root, SuiteConfig(max_workers=2, timeout_seconds=600),
                            budget_total=2, preflight=False, heartbeat_seconds=60.0,
                            run_id="it-resume", **kw)


def _executed(tmp_path: Path) -> list[str]:
    return sorted(p.name.split("-")[1] for p in (tmp_path / "probe").glob("exec-*"))


def _by_unit(result: runner.SuiteResult) -> dict[str, runner.UnitResult]:
    return {r.unit_id: r for r in result.results}


def _covered(cov_file: str) -> dict[str, set[int]]:
    data = sqlite3.connect(cov_file)
    try:
        rows = data.execute("select f.path, l.numbits from line_bits l "
                            "join file f on f.id = l.file_id").fetchall()
    finally:
        data.close()
    out: dict[str, set[int]] = {}
    for path, bits in rows:
        lines = {8 * i + j for i, byte in enumerate(bits) for j in range(8) if byte >> j & 1}
        out.setdefault(path.replace("\\", "/").rsplit("/", 1)[-1], set()).update(lines)
    return out


def _latest_manifest(root: Path) -> tuple[dict, Path]:
    runs = sorted((root / ".shipwright" / "runs" / "f0-evidence" / "published").iterdir(),
                  key=lambda p: p.stat().st_mtime)
    return json.loads((runs[-1] / "manifest.json").read_text(encoding="utf-8")), runs[-1]


def test_a_fix_round_reruns_only_the_red_test_and_reuses_the_green_unit(tmp_path, monkeypatch):
    root = _project(tmp_path)
    first = _run(root, tmp_path, monkeypatch)
    assert first.exit_code == 1
    assert _by_unit(first)["shipwright-beta"].outcome == "test_failure"
    assert load_state(root)[0] is not None, "a red run must leave a resume token"
    before = _executed(tmp_path)

    _fix(root)
    second = _run(root, tmp_path, monkeypatch)

    assert second.exit_code == 0
    units = _by_unit(second)
    assert units["shipwright-alpha"].resume == "reused-green"
    assert units["shipwright-beta"].resume == "failed-only"
    assert (units["shipwright-beta"].outcome, units["shipwright-beta"].race) == ("pass", False)
    after = _executed(tmp_path)
    assert after.count("green1") == before.count("green1") == 1, after   # NOT re-run
    assert after.count("needs_fix") == before.count("needs_fix") + 1, (before, after)

    manifest, run_dir = _latest_manifest(root)
    resumed = manifest["resumed"]["units"]
    assert resumed["shipwright-alpha"] == {"mode": "reused-green", "rerun_tests": []}
    assert resumed["shipwright-beta"]["mode"] == "failed-only"
    assert [t.rsplit("::", 1)[-1] for t in resumed["shipwright-beta"]["rerun_tests"]] == [
        "test_needs_fix"]
    assert len(manifest["resumed"]["prior_invocations"]) == 1
    suite = ET.parse(run_dir / "reports" / "shipwright-beta.xml").getroot().find("testsuite")
    assert (suite.get("tests"), suite.get("failures")) == ("2", "0")  # the WHOLE unit, merged
    assert after.count("ok_b") == before.count("ok_b") == 1, after   # the green sibling stood in
    alpha = ET.parse(run_dir / "reports" / "shipwright-alpha.xml").getroot().find("testsuite")
    assert (alpha.get("tests"), alpha.get("failures")) == ("2", "0")
    assert {u["outcome"] for u in manifest["units"]} == {"pass"}

    # coverage: lib_a was untouched, so the first run's data for it survives the restore;
    # lib_b was EDITED, so its rows are rebuilt from the re-run (line 2 = `return 3`).
    covered = {Path(f).name: _covered(f) for f in second.cov_files}
    assert 2 in covered[".coverage.shipwright-alpha"]["lib_a.py"], covered
    assert covered[".coverage.shipwright-beta"]["lib_b.py"] == {1, 2}, covered  # stale line 3 gone
    assert load_state(root)[1] == NO_STATE, "a green run spends the resume token"


def test_an_added_test_file_runs_that_unit_in_full(tmp_path, monkeypatch):
    root = _project(tmp_path)
    assert _run(root, tmp_path, monkeypatch).exit_code == 1
    _fix(root)
    (root / "plugins" / "shipwright-beta" / "tests" / "test_new.py").write_text(
        _HEADER + "def test_new():\n    log('new')\n", encoding="utf-8")

    second = _run(root, tmp_path, monkeypatch)

    units = _by_unit(second)
    assert second.exit_code == 0
    assert units["shipwright-beta"].resume.startswith("full run (test files were added")
    assert units["shipwright-alpha"].resume == "reused-green"   # unaffected unit still reused
    suite = ET.parse(_latest_manifest(root)[1] / "reports" / "shipwright-beta.xml"
                     ).getroot().find("testsuite")
    assert suite.get("tests") == "3"  # the WHOLE unit ran, new test included


def test_the_kill_switch_forces_a_full_run(tmp_path, monkeypatch):
    root = _project(tmp_path)
    assert _run(root, tmp_path, monkeypatch).exit_code == 1
    _fix(root)
    monkeypatch.setenv(ENV_OFF, "0")
    probe = tmp_path / "probe"
    monkeypatch.setenv("F0_PROBE_DIR", str(probe))

    second = runner.run_suite(root, SuiteConfig(max_workers=2, timeout_seconds=600),
                              budget_total=2, preflight=False, heartbeat_seconds=60.0,
                              run_id="it-resume")

    assert second.exit_code == 0 and not second.resume.active
    assert _executed(tmp_path).count("green1") == 2   # alpha re-ran in full
    assert "resumed" not in _latest_manifest(root)[0]
