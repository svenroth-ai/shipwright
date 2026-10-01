"""F0 pins pytest's tmp root short - the MAX_PATH root cause of the 20-minute retry.

Measured 2026-10-01 from `shipwright_events.jsonl`: since 2026-09-06 `shared/tests`
failed its PARALLEL attempt in 99 of 100 F0 runs (`retry_shape == "serial"`, median
1235 s against 215 s before) with `FileNotFoundError` on fixture trees deeper than
Windows' 260 characters. The parallel attempt alone carries pytest's default
`pytest-of-<user>/pytest-N/` plus xdist's `popen-gwN/` under the unit's already-deep
TEMP; the serial retry has neither, so it passed - after re-running the whole unit.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

import scripts.tools.run_test_suite as mod
from scripts.tools.run_test_suite import build_command, discover_units
from scripts.tools.suite_process import ProcessResult


def _unit(tmp_path: Path):
    plugin = tmp_path / "plugins" / "shipwright-alpha"
    (plugin / "tests").mkdir(parents=True)
    (plugin / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    return discover_units(tmp_path)[0]


def test_basetemp_is_passed_only_when_given(tmp_path):
    unit = _unit(tmp_path)
    assert "--basetemp" not in build_command(unit, None)
    cmd = build_command(unit, None, basetemp=tmp_path / "t")
    assert cmd[cmd.index("--basetemp") + 1] == str(tmp_path / "t")


def test_exec_pins_basetemp_to_a_subdir_of_the_units_temp(monkeypatch, tmp_path):
    """A SUBdir, never the unit temp itself: pytest wipes its basetemp at start, and the
    attempt log + JUnit report (the proof pytest ran) live directly in that temp."""
    seen = {}

    def fake_run_process(argv, **kwargs):
        seen["argv"] = argv
        return ProcessResult(returncode=0, tail="", seconds=0.0, truncated=False)

    monkeypatch.setattr(mod, "_run_process", fake_run_process)
    unit_tmp = tmp_path / "u0"
    mod._exec(_unit(tmp_path), tmp_path, 8, unit_tmp)

    argv = seen["argv"]
    basetemp = Path(argv[argv.index("--basetemp") + 1])
    assert basetemp.parent == unit_tmp
    # the report path the runner reads back is NOT inside the wiped directory
    assert Path(argv[argv.index("--junit-xml") + 1]).parent == unit_tmp


def test_the_recorded_retry_command_carries_a_short_basetemp(monkeypatch, tmp_path):
    """The `reproduce me` a race card shows must keep the path-length workaround, or a
    human re-running it on Windows can hit the very MAX_PATH failure this fixes."""
    (tmp_path / "shared" / "tests").mkdir(parents=True)
    plugin = tmp_path / "plugins" / "shipwright-alpha"
    (plugin / "tests").mkdir(parents=True)
    (plugin / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    for d in ("shared/scripts/tests", "shared/scripts/tools/tests", "integration-tests"):
        (tmp_path / d).mkdir(parents=True)
    attempts = {}

    def fake_exec(unit, project_root, xdist_workers, tmp_dir, timeout=None,
                  cancel_event=None):
        attempts[unit.id] = attempts.get(unit.id, 0) + 1
        red = unit.id == "shared/tests" and attempts[unit.id] == 1
        return (1 if red else 0), "out", 0.01, True, False, False

    monkeypatch.setattr(mod, "_exec", fake_exec)
    result = mod.run_suite(tmp_path, mod.SuiteConfig(), preflight=False)

    retried = next(r for r in result.results if r.unit_id == "shared/tests")
    assert retried.race and "--basetemp" in (retried.retry_cmd or "")
