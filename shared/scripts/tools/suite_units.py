#!/usr/bin/env python3
"""F0 suite runner - unit discovery + the `suite` config boundary.

Extracted from `run_test_suite.py` (iterate-2026-07-14-f0-parallel-suite) to keep both
modules inside the 300-line budget. This half owns everything that answers "WHICH units
exist and HOW may they be run"; `run_test_suite.py` owns the execution + verdict.

Every operator-facing string here is ASCII on purpose: a cp1252 console raises
UnicodeEncodeError on non-ASCII output, and these messages sit on the refusal paths.
"""

from __future__ import annotations

import json
import subprocess  # nosec B404 - fixed argv, shell=False; no user-supplied strings
from dataclasses import dataclass, field
from pathlib import Path

SHARED_TEST_DIRS = ("shared/tests", "shared/scripts/tests", "shared/scripts/tools/tests")
INTEGRATION_DIR = "integration-tests"
#: A CLI ``-m`` REPLACES the pyproject default, so ``not slow`` must be restated.
SHARED_MARKERS = ("-m", "not slow and not cross_plugin")
#: One shared/scripts/tools test drives the real diff-cover gate (parity with ci.yml).
SHARED_EXTRA_DEPS = ("diff-cover==10.3.0",)
CONFIG_NAME = "shipwright_test_config.json"
_ALLOWED_SUITE_KEYS = {"max_workers", "xdist", "timeout_seconds", "_comment"}
#: A hung unit holds its budget slot and would otherwise block F0 forever with no
#: output (capture_output). Generous by default: this is a hang guard, not a perf gate.
DEFAULT_TIMEOUT_SECONDS = 1800

_OPT_IN = ("this runner is opt-in; F0 falls back to the project's own test command "
           "(references/F0.md).")


class SuiteConfigError(RuntimeError):
    """The ``suite`` config is absent, malformed, or not runnable - never swallowed."""


@dataclass(frozen=True)
class Unit:
    id: str
    cwd: str
    target: str
    markers: tuple[str, ...] = ()
    extra_deps: tuple[str, ...] = ()


@dataclass(frozen=True)
class SuiteConfig:
    xdist: dict[str, int] = field(default_factory=dict)
    max_workers: int | None = None
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS


def discover_units(project_root: Path) -> list[Unit]:
    """Same selection rule as ci.yml (see tests/test_f0_ci_parity.py).

    Discovered, never hardcoded: a newly added plugin is picked up automatically
    instead of being silently left untested.
    """
    units: list[Unit] = []
    plugins = project_root / "plugins"
    if plugins.is_dir():
        for p in sorted(plugins.iterdir()):
            if (p / "pyproject.toml").is_file() and (p / "tests").is_dir():
                units.append(Unit(id=p.name, cwd=f"plugins/{p.name}", target="tests"))
    for d in SHARED_TEST_DIRS:
        if (project_root / d).is_dir():
            units.append(Unit(id=d, cwd=".", target=d, markers=SHARED_MARKERS,
                              extra_deps=SHARED_EXTRA_DEPS))
    if (project_root / INTEGRATION_DIR).is_dir():
        units.append(Unit(id=INTEGRATION_DIR, cwd=".", target=INTEGRATION_DIR))
    return units


def _positive_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise SuiteConfigError(f"{label} must be a positive integer, got {value!r}")
    return value


def load_suite_config(project_root: Path, unit_ids) -> SuiteConfig:
    """Validate the whole config BEFORE a single subprocess starts (AC7)."""
    path = project_root / CONFIG_NAME
    if not path.is_file():
        raise SuiteConfigError(f"{CONFIG_NAME} not found in {project_root} - {_OPT_IN}")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SuiteConfigError(f"{path} is not valid JSON: {exc}") from exc
    if not isinstance(raw, dict):
        raise SuiteConfigError(f"{path} must contain a JSON object.")

    suite = raw.get("suite")
    if suite is None:
        raise SuiteConfigError(f"no 'suite' block in {CONFIG_NAME} - {_OPT_IN}")
    if not isinstance(suite, dict):
        raise SuiteConfigError("'suite' must be a JSON object.")
    unknown = sorted(set(suite) - _ALLOWED_SUITE_KEYS)
    if unknown:
        raise SuiteConfigError(
            f"unknown key(s) in 'suite': {unknown}; allowed: {sorted(_ALLOWED_SUITE_KEYS)}")

    max_workers = suite.get("max_workers")
    if max_workers is not None:
        max_workers = _positive_int(max_workers, "suite.max_workers")

    timeout_seconds = suite.get("timeout_seconds", DEFAULT_TIMEOUT_SECONDS)
    timeout_seconds = _positive_int(timeout_seconds, "suite.timeout_seconds")

    raw_xdist = suite.get("xdist", {})
    if not isinstance(raw_xdist, dict):
        raise SuiteConfigError("'suite.xdist' must be a JSON object {unit-id: workers}.")
    known = set(unit_ids)
    xdist: dict[str, int] = {}
    for unit_id, workers in raw_xdist.items():
        if unit_id not in known:
            raise SuiteConfigError(
                f"suite.xdist names unknown unit {unit_id!r} (a typo would silently "
                f"disable the speed-up). Discovered units: {sorted(known)}")
        xdist[unit_id] = _positive_int(workers, f"suite.xdist[{unit_id!r}]")
    return SuiteConfig(xdist=xdist, max_workers=max_workers,
                       timeout_seconds=timeout_seconds)


def ensure_xdist_available(config: SuiteConfig, project_root: Path) -> None:
    """AC12: fail LOUD and early when an allowlisted unit cannot get pytest-xdist.

    Without this pre-flight, `uv` failing to provision xdist exits 1, which looks like a
    test failure: the unit would be re-run serially WITHOUT xdist, pass, and green the
    gate as a "RACE" - having never actually run the way the config demands.
    """
    if not config.xdist:
        return
    proc = subprocess.run(  # nosec B603 - fixed argv, shell=False
        ["uv", "run", "--with", "pytest-xdist", "python", "-c", "import xdist"],
        cwd=project_root, capture_output=True, text=True, errors="replace", shell=False)
    if proc.returncode != 0:
        raise SuiteConfigError(
            f"suite.xdist is configured for {sorted(config.xdist)} but pytest-xdist "
            f"cannot be provisioned here (uv exit {proc.returncode}). Fix the "
            f"environment or remove the 'xdist' allowlist from {CONFIG_NAME}; do NOT "
            f"let the run continue without it.\n{(proc.stderr or '').strip()[:300]}")
