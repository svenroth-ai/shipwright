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
from dataclasses import dataclass, field, replace
from pathlib import Path

SHARED_TEST_DIRS = ("shared/tests", "shared/scripts/tests", "shared/scripts/tools/tests")
INTEGRATION_DIR = "integration-tests"
#: The interpreter F0 must run, because it is the one CI judges the push with. Without
#: it uv resolves per DIRECTORY from ambient state, and a plugin dir is its own uv
#: project, so the repo-root `.python-version` never reaches it - measured on main
#: @6d2b2013: 14 plugin units on 3.13.13 while every workflow ran 3.11.15, F0 green and
#: CI red. ONE owner: the tracked `.python-version` files and every workflow's
#: `uv python install` are pinned to this value by `tests/test_f0_ci_parity.py`.
#: The PATCH level is deliberately unpinned: it floats on both sides, and pinning it
#: would need re-pinning across five workflows on every 3.11.x release and eventually
#: name a build uv has pruned. Do not "tighten" this to 3.11.x.
PYTHON_VERSION = "3.11"
#: Every uv invocation the F0 gate makes starts here, so the pin cannot be present at
#: two call sites and forgotten at the third (build_command / warm_up / this module's
#: ensure_xdist_available) - a pre-flight or warm-up on another interpreter answers for
#: an environment the units never run in.
UV_RUN = ("uv", "run", "--python", PYTHON_VERSION)
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

#: Unit-outcome vocabulary. Here rather than in the runner because two modules need
#: it - `run_test_suite.classify()` PRODUCES it, `suite_report` RENDERS it - and this
#: is the leaf both already import (a copy in the renderer could silently diverge).
PASS = "pass"
TEST_FAILURE = "test_failure"
INFRA = "infra"


class SuiteConfigError(RuntimeError):
    """The ``suite`` config is absent, malformed, or not runnable - never swallowed."""


@dataclass(frozen=True)
class Unit:
    id: str
    cwd: str
    target: str
    markers: tuple[str, ...] = ()
    extra_deps: tuple[str, ...] = ()
    #: Coverage instrumentation, set by `instrument_for_coverage` (empty until then,
    #: so an uninstrumented unit runs exactly as it did before).
    cov_args: tuple[str, ...] = ()
    cov_file: str | None = None


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


def cov_label(unit_id: str) -> str:
    """`shared/scripts/tests` -> `shared-scripts-tests`, a filename-safe label.

    `combine_coverage.py` reads the label back to decide whether the tier needs
    remapping onto `plugins/<name>/scripts/`, and it splits on `.` (pytest-cov's
    xdist suffix), so the separator here must not be a dot.
    """
    return unit_id.replace("/", "-")


def _cov_source(unit: Unit, project_root: Path) -> str | None:
    """The `--cov=` root for a unit, or None when it has nothing to measure.

    Same rule as ci.yml: a plugin is measured through its own `scripts/` (it runs
    from its own CWD), while the shared and integration tiers run from the repo
    root and measure `shared/`.
    """
    if unit.cwd == ".":
        return "shared" if (project_root / "shared").is_dir() else None
    return "scripts" if (project_root / unit.cwd / "scripts").is_dir() else None


def instrument_for_coverage(units, project_root: Path, data_dir: Path) -> list[Unit]:
    """Attach per-unit coverage measurement, so F0 can run the diff-coverage gate
    CI runs (`suite_coverage`). Units with nothing measurable are returned as-is.

    Every path handed to a unit is ABSOLUTE: a plugin unit runs from its own CWD,
    and coverage does not search parent directories for its config, so a relative
    `--cov-config` would silently drop `relative_files` and leave the XML full of
    absolute paths that diff-cover cannot match against git.

    Without a root `pyproject.toml` nothing is instrumented at all - that config is
    where `relative_files` lives, and a measurement it cannot honour would look
    green while proving nothing.

    Both inputs are RESOLVED here rather than trusted: the CLI happens to pass an
    absolute root, but a programmatic `run_suite(Path("."))` would otherwise emit
    `--cov-config=pyproject.toml`, which a plugin unit - running from
    `plugins/<name>` - resolves to that plugin's own pyproject instead of the root
    one, silently losing `relative_files`. A function whose correctness depends on
    the caller having normalised its argument is a trap, not a contract.
    """
    project_root = Path(project_root).resolve()
    data_dir = Path(data_dir).resolve()
    config = project_root / "pyproject.toml"
    if not config.is_file():
        return list(units)
    out: list[Unit] = []
    seen: dict[str, str] = {}
    for unit in units:
        source = _cov_source(unit, project_root)
        if source is None:
            out.append(unit)
            continue
        label = cov_label(unit.id)
        if label in seen:  # two concurrent writers on one file would silently merge
            raise SuiteConfigError(
                f"units {seen[label]!r} and {unit.id!r} would share the same "
                f"coverage data file (.coverage.{label}) - rename one unit.")
        seen[label] = unit.id
        out.append(replace(
            unit,
            extra_deps=(*unit.extra_deps, "pytest-cov"),
            # Appended AFTER unit.markers by build_command, so the shared tier's
            # composed `-m "not slow and not cross_plugin"` is untouched.
            cov_args=(f"--cov={source}", f"--cov-config={config}", "--cov-report="),
            cov_file=str(data_dir / f".coverage.{label}"),
        ))
    return out


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
        [*UV_RUN, "--with", "pytest-xdist", "python", "-c", "import xdist"],
        cwd=project_root, capture_output=True, text=True, errors="replace", shell=False)
    if proc.returncode != 0:
        raise SuiteConfigError(
            f"suite.xdist is configured for {sorted(config.xdist)} but pytest-xdist "
            f"cannot be provisioned here, or the pinned interpreter {PYTHON_VERSION} "
            f"could not be (uv exit {proc.returncode}) - this call needs both, so the "
            f"stderr below says which. Fix the environment or remove the 'xdist' "
            f"allowlist from {CONFIG_NAME}; do NOT let the run continue without it."
            f"\n{(proc.stderr or '').strip()[:300]}")
