"""F0 suite runner — unit discovery + the `suite` config boundary.

Covers iterate-2026-07-14-f0-parallel-suite AC2 (units are DISCOVERED, never a
hardcoded list — a new plugin must not be silently left untested), AC7 (the config is
validated in full BEFORE any subprocess starts) and the ASCII-only rule that keeps the
refusal/RACE paths from crashing a cp1252 console.

Execution, the exit-code classes and the serial re-verify safety net live in
`test_run_test_suite.py`.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

import scripts.tools.run_test_suite as run_mod
import scripts.tools.suite_coverage as cov_mod
import scripts.tools.suite_race_triage as race_mod
import scripts.tools.suite_report as report_mod
import scripts.tools.suite_units as mod
from scripts.tools.suite_units import (
    SuiteConfigError,
    discover_units,
    load_suite_config,
)


def _project(tmp_path: Path, plugins=("shipwright-alpha", "shipwright-beta")) -> Path:
    for name in plugins:
        p = tmp_path / "plugins" / name
        (p / "tests").mkdir(parents=True)
        (p / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    for d in ("shared/tests", "shared/scripts/tests", "shared/scripts/tools/tests",
              "integration-tests"):
        (tmp_path / d).mkdir(parents=True)
    return tmp_path


def _write_cfg(root: Path, suite) -> None:
    payload = {"coverage": {"min": 70}}
    if suite is not None:
        payload["suite"] = suite
    (root / "shipwright_test_config.json").write_text(json.dumps(payload), encoding="utf-8")


# --- AC2: discovery (never a hardcoded list) ---
def test_discovers_plugins_shared_dirs_and_integration(tmp_path):
    ids = [u.id for u in discover_units(_project(tmp_path))]
    assert ids == [
        "shipwright-alpha", "shipwright-beta",
        "shared/tests", "shared/scripts/tests", "shared/scripts/tools/tests",
        "integration-tests",
    ]


def test_a_new_plugin_is_picked_up_automatically(tmp_path):
    root = _project(tmp_path)
    newp = root / "plugins" / "shipwright-zulu"
    (newp / "tests").mkdir(parents=True)
    (newp / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    assert "shipwright-zulu" in [u.id for u in discover_units(root)]


def test_plugin_without_pyproject_or_tests_is_not_a_unit(tmp_path):
    root = _project(tmp_path)
    (root / "plugins" / "no-pyproject" / "tests").mkdir(parents=True)
    (root / "plugins" / "no-tests").mkdir(parents=True)
    (root / "plugins" / "no-tests" / "pyproject.toml").write_text("", encoding="utf-8")
    ids = [u.id for u in discover_units(root)]
    assert "no-pyproject" not in ids and "no-tests" not in ids


# --- AC7: the config boundary (round-trip / probe) ---
def test_missing_suite_block_is_an_actionable_refusal(tmp_path):
    root = _project(tmp_path)
    _write_cfg(root, None)
    with pytest.raises(SuiteConfigError, match="suite"):
        load_suite_config(root, ["shared/tests"])


def test_missing_config_file_is_an_actionable_refusal(tmp_path):
    with pytest.raises(SuiteConfigError):
        load_suite_config(_project(tmp_path), ["shared/tests"])


def test_unknown_unit_in_xdist_allowlist_is_a_hard_error(tmp_path):
    root = _project(tmp_path)
    _write_cfg(root, {"xdist": {"shared/testz": 8}})  # typo
    with pytest.raises(SuiteConfigError, match="shared/testz"):
        load_suite_config(root, [u.id for u in discover_units(root)])


@pytest.mark.parametrize("suite", [
    {"xdist": {"shared/tests": 0}},
    {"xdist": {"shared/tests": -1}},
    {"xdist": {"shared/tests": True}},
    {"xdist": {"shared/tests": "8"}},
    {"max_workers": 0},
    {"max_workers": True},
    {"xdist": []},
    {"unknown_key": 1},
])
def test_malformed_suite_config_is_rejected(tmp_path, suite):
    root = _project(tmp_path)
    _write_cfg(root, suite)
    with pytest.raises(SuiteConfigError):
        load_suite_config(root, [u.id for u in discover_units(root)])


def test_unparseable_config_is_reported_not_swallowed(tmp_path):
    root = _project(tmp_path)
    (root / "shipwright_test_config.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(SuiteConfigError, match="JSON"):
        load_suite_config(root, ["shared/tests"])


def test_valid_config_round_trips(tmp_path):
    root = _project(tmp_path)
    _write_cfg(root, {"max_workers": 8, "xdist": {"shared/tests": 8}, "_comment": "ok"})
    cfg = load_suite_config(root, [u.id for u in discover_units(root)])
    assert cfg.xdist == {"shared/tests": 8} and cfg.max_workers == 8


def test_operator_facing_strings_are_ascii_only():
    """A cp1252 console raises UnicodeEncodeError on non-ASCII output — which on the
    RACE path would abort the very gate the race handling exists to keep green (#244)."""
    for module in (mod, run_mod, report_mod, race_mod, cov_mod):
        src = Path(module.__file__).read_text(encoding="utf-8")
        offenders = [ln for ln in src.splitlines() if not ln.isascii()]
        assert not offenders, f"non-ASCII in {module.__name__}: {offenders[:3]}"


def test_no_uv_invocation_escapes_the_interpreter_pin():
    """Guards the CLASS, not the three call sites that happen to exist today.

    `build_command` shipped without `--python` and no test noticed, because every test
    pinned the sites that were written rather than the rule they must follow. The three
    argv tests would stay green if a FOURTH `uv run`/`uvx` were added unpinned — which
    is exactly how this defect arrived. So: inside the F0 runner, `uv` is spelled
    `UV_RUN` and nowhere else. `uvx` is refused outright; it takes no interpreter from
    UV_RUN and would resolve an ambient one.

    Quote-agnostic on purpose: an earlier cut matched only the double-quoted spelling,
    so the ordinary `subprocess.run(['uv', 'run', ...])` slipped straight through while
    every per-site test stayed green (external review). A guard for a recurrence mode
    must not itself be defeated by choosing the other quote character.

    Scoped to the same FOUR modules as the ASCII guard above, not the two that happened
    to pass: narrowing a class guard to its known-good set is how the class stops being
    guarded. Broadening it caught `suite_report.suite_command`, which composed a bare
    `uv run` for the "reproduce the whole suite" line published in the tracked triage
    card — the one place an unpinned command is actively misleading.

    `suite_coverage` joins the scan rather than being left out of it, with ONE stated
    exemption: a `uvx <tool>@<version>` line. That runs a pinned THIRD-PARTY tool whose
    own interpreter never executes this repo's code, so `--python` would pin the wrong
    thing — the same exemption `test_f0_ci_parity` states for the composite action that
    this call mirrors. The exemption is deliberately narrow: it requires the `@<version>`
    pin, so a bare `uvx diff-cover` is still caught. Stating an exemption beats omitting
    the module, because an omitted module is a guard that goes quiet.
    """
    for module in (mod, run_mod, report_mod, race_mod, cov_mod):
        for i, line in enumerate(Path(module.__file__).read_text(encoding="utf-8").splitlines(), 1):
            if line.lstrip().startswith("#") or "UV_RUN = " in line:
                continue  # the definition itself, and prose about it
            if re.search(r"""["']uvx["']\s*,\s*f?["'][\w.-]+@""", line):
                continue  # a pinned third-party tool — see the docstring
            assert not re.search(r"""['"]uvx?['"]""", line), (
                f"{module.__name__}:{i} spells a uv invocation by hand: {line.strip()!r}. "
                "Spread UV_RUN instead - a bare `uv run` resolves whatever interpreter the "
                "directory happens to offer, which is the bug this module was fixed for.")


# --------------------------------------------------------------------------- #
# Per-unit coverage instrumentation (iterate-2026-08-01-f0-diff-coverage-gate)
# --------------------------------------------------------------------------- #
def _instrumented(root: Path):
    from scripts.tools.suite_units import instrument_for_coverage
    return {u.id: u for u in
            instrument_for_coverage(discover_units(root), root, root / ".cov-data")}


def _with_pyproject(tmp_path: Path, **kw) -> Path:
    root = _project(tmp_path, **kw)
    (root / "pyproject.toml").write_text("[tool.coverage.run]\n", encoding="utf-8")
    return root


def test_a_plugin_with_scripts_is_measured_from_its_own_cwd(tmp_path):
    root = _with_pyproject(tmp_path)
    (root / "plugins/shipwright-alpha/scripts").mkdir()
    unit = _instrumented(root)["shipwright-alpha"]
    # `cd plugins/<name>` is the unit's cwd, so the source root is CWD-relative;
    # combine_coverage.py remaps it back to plugins/<name>/scripts/ afterwards.
    assert "--cov=scripts" in unit.cov_args
    assert "--cov-report=" in unit.cov_args
    assert "pytest-cov" in unit.extra_deps


def test_a_plugin_without_scripts_is_not_instrumented(tmp_path):
    """Mirrors ci.yml's `if [ -d "$plugin/scripts" ]` branch (shipwright-preview)."""
    root = _with_pyproject(tmp_path)
    unit = _instrumented(root)["shipwright-beta"]
    assert unit.cov_args == ()
    assert unit.cov_file is None
    assert "pytest-cov" not in unit.extra_deps


def test_shared_and_integration_tiers_measure_shared(tmp_path):
    units = _instrumented(_with_pyproject(tmp_path))
    for uid in ("shared/tests", "shared/scripts/tests", "integration-tests"):
        assert "--cov=shared" in units[uid].cov_args, uid


def test_the_cov_config_is_the_absolute_root_pyproject(tmp_path):
    """A plugin unit runs from another CWD, and coverage does NOT search parent
    dirs for config — a relative path here silently drops `relative_files`, and
    diff-cover then matches nothing."""
    root = _with_pyproject(tmp_path)
    (root / "plugins/shipwright-alpha/scripts").mkdir()
    unit = _instrumented(root)["shipwright-alpha"]
    cfg = next(a for a in unit.cov_args if a.startswith("--cov-config="))
    assert Path(cfg.split("=", 1)[1]).is_absolute()
    assert Path(cfg.split("=", 1)[1]) == root / "pyproject.toml"


def test_each_shared_unit_writes_its_OWN_data_file(tmp_path):
    """ci.yml runs the three shared dirs SERIALLY and can `--cov-append` onto one
    file; F0 runs them CONCURRENTLY, so one target would be three writers racing."""
    units = _instrumented(_with_pyproject(tmp_path))
    shared = [units[d].cov_file for d in
              ("shared/tests", "shared/scripts/tests", "shared/scripts/tools/tests")]
    assert len(set(shared)) == 3
    assert all(Path(f).is_absolute() for f in shared)
    assert all("--cov-append" not in a for u in units.values() for a in u.cov_args)


def test_colliding_labels_fail_before_any_process_starts(tmp_path):
    """Two writers on one data file would silently merge. Fail closed instead."""
    from scripts.tools.suite_units import Unit, instrument_for_coverage
    root = _with_pyproject(tmp_path)
    (root / "plugins/shipwright-alpha/scripts").mkdir()
    twin = Unit(id="shipwright/alpha", cwd="plugins/shipwright-alpha", target="tests")
    units = [*discover_units(root), twin]
    with pytest.raises(SuiteConfigError, match="same coverage data file"):
        instrument_for_coverage(units, root, root / ".cov-data")


def test_no_root_pyproject_means_no_instrumentation(tmp_path):
    """Without the root config `relative_files` is not honoured, so the XML would
    carry absolute paths and diff-cover would report "no lines with coverage
    information" — a measurement that looks green and proves nothing."""
    root = _project(tmp_path)
    assert all(u.cov_args == () for u in _instrumented(root).values())
