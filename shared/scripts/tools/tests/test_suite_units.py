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
    for module in (mod, run_mod, report_mod, race_mod):
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
    """
    for module in (mod, run_mod, report_mod, race_mod):
        for i, line in enumerate(Path(module.__file__).read_text(encoding="utf-8").splitlines(), 1):
            if line.lstrip().startswith("#") or "UV_RUN = " in line:
                continue  # the definition itself, and prose about it
            assert not re.search(r"""['"]uvx?['"]""", line), (
                f"{module.__name__}:{i} spells a uv invocation by hand: {line.strip()!r}. "
                "Spread UV_RUN instead - a bare `uv run` resolves whatever interpreter the "
                "directory happens to offer, which is the bug this module was fixed for.")
