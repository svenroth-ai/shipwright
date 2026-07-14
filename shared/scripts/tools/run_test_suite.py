#!/usr/bin/env python3
"""F0 suite runner - run the project's test units concurrently, safely.

Rationale, the allowlist rule and the honest "accelerated pre-gate" framing live in
`plugins/shipwright-iterate/skills/iterate/references/F0.md` + `docs/hooks-and-pipeline.md`.
Units are DISCOVERED (same rule as ci.yml) and run as parallel processes; pytest-xdist is
a per-unit OPT-IN. Discovery + the `suite` config boundary live in `suite_units.py`.

The safety net (why concurrency does not weaken the gate):
- **"Did pytest run?" is PROVEN, not guessed** - every unit writes a JUnit report, present
  iff pytest executed. `uv run` also exits 1 on its own env-build failures, and sniffing
  prose is unsound (pytest pluralises "error" -> "errors", so a fixture-level race reads
  nothing like a normal failure).
- **A test failure is re-run SERIALLY, without xdist** - the way F0 used to run it; that
  verdict is authoritative, so a race can never cause a false STOP.
- **An infra fault is re-run once with the IDENTICAL shape** (xdist still on): a
  deterministic fault (rc 5, usage error, unprovisionable xdist) still fails, but a
  transient one (uv-cache races that 18 concurrent processes *create*) recovers.

**Honest scope:** F0 is an *accelerated pre-gate*. The retries remove false STOPs; they do
NOT prove serial equivalence for units that PASSED, so `ci.yml` stays SERIAL as the
authoritative gate (guarded by test_f0_ci_parity.py); retries get a clean TEMP dir but the
repo tree is shared. Output is ASCII-only - a cp1252 console raises UnicodeEncodeError on
non-ASCII, which on the retry path would abort the very gate this keeps green (#244).
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import os
import subprocess  # nosec B404 - fixed argv, shell=False; no user-supplied strings
import sys
import tempfile
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

# Resolve `shared/` so this file imports the sibling under the SAME dotted name the
# tests use (scripts.tools.*) -> one module object, not two. Binding the generic
# top-level `tools`/`lib` package here would re-create the ADR-045 collision class.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.tools.suite_units import (  # noqa: E402  (re-export: one import site)
    SuiteConfig,
    SuiteConfigError,
    Unit,
    discover_units,
    ensure_xdist_available,
    load_suite_config,
)

_RC_TIMEOUT = 124        # conventional timeout rc; INFRA like any other fault
_RC_SPAWN_FAILED = 126

PASS = "pass"
TEST_FAILURE = "test_failure"
INFRA = "infra"

#: how a unit recovered on its retry - purely for an honest operator message
RETRY_SERIAL = "serial"   # a test failure that passed when run alone, without xdist
RETRY_INFRA = "infra"     # a transient infrastructure fault that did not reproduce


@dataclass
class UnitResult:
    unit_id: str
    outcome: str
    rc: int
    seconds: float
    output: str = ""
    race: bool = False           # passed only on a retry
    retry_kind: str | None = None
    serial_rc: int | None = None


@dataclass
class SuiteResult:
    results: list[UnitResult]
    exit_code: int
    seconds: float
    xdist_ids: tuple[str, ...] = field(default_factory=tuple)


def build_command(unit: Unit, xdist_workers: int | None,
                  report: Path | None = None) -> list[str]:
    """argv only - never a shell string (config/paths must not reach a shell)."""
    cmd = ["uv", "run", "--with", "pytest", "--with", "pytest-mock"]
    for dep in unit.extra_deps:
        cmd += ["--with", dep]
    if xdist_workers:
        cmd += ["--with", "pytest-xdist"]  # provisioned, not assumed (AC12)
    cmd += ["pytest", unit.target, "-q", "-p", "no:cacheprovider"]
    cmd += list(unit.markers)
    if xdist_workers:
        cmd += ["-n", str(xdist_workers)]
    if report is not None:  # existence of this file PROVES pytest ran (see docstring)
        cmd += ["--junit-xml", str(report)]
    return cmd


def classify(rc: int, pytest_ran: bool = False) -> str:
    """pytest: 0 ok / 1 tests failed / 2,3,4 infra / 5 nothing collected.

    ``rc`` is ``uv run``'s. rc 1 is a TEST failure only when pytest provably ran;
    otherwise `uv` failed before pytest ever started -> infrastructure fault.
    """
    if rc == 0:
        return PASS
    if rc == 1:
        return TEST_FAILURE if pytest_ran else INFRA
    return INFRA


def cpu_budget(config: SuiteConfig | None) -> int:
    if config is not None and config.max_workers:
        return config.max_workers
    return max(1, (os.cpu_count() or 2) - 2)


class _Budget:
    """Outer pool and inner xdist workers draw from ONE budget (no oversubscription).

    Liveness comes from the clamp in ``acquire``: no unit can ever ask for more than the
    whole budget, so the wait predicate is always eventually satisfiable.
    """

    def __init__(self, total: int) -> None:
        self.total = max(1, total)
        self._used = 0
        self._cond = threading.Condition()

    def acquire(self, weight: int) -> int:
        weight = max(1, min(weight, self.total))
        with self._cond:
            while self._used + weight > self.total:
                self._cond.wait()
            self._used += weight
        return weight

    def release(self, weight: int) -> None:
        with self._cond:
            self._used -= weight
            self._cond.notify_all()


def warm_up(project_root: Path) -> None:
    """Create/sync the environment ONCE, serially, before 18 processes race for it.

    18 concurrent cold `uv run` calls contend on the shared uv cache (a documented
    hardlink-race source on Windows). One warm serial call turns that into a no-op.
    Best-effort: a failure here surfaces as a normal unit fault, not a crash.
    """
    try:
        subprocess.run(  # nosec B603 - fixed argv, shell=False
            ["uv", "run", "--with", "pytest", "python", "-c", "pass"],
            cwd=project_root, capture_output=True, text=True, shell=False, timeout=600)
    except (OSError, subprocess.SubprocessError):
        pass


def _exec(unit: Unit, project_root: Path, xdist_workers: int | None, tmp_dir: Path,
          timeout: int | None = None) -> tuple[int, str, float, bool]:
    """Run one unit. Returns (rc, output, seconds, pytest_ran).

    A spawn failure or a hang becomes a FAULT rc, never an exception: one unlaunchable
    unit must not discard the other units' results.
    """
    env = os.environ.copy()
    tmp_dir.mkdir(parents=True, exist_ok=True)
    for key in ("TMPDIR", "TEMP", "TMP"):  # units must not collide via shared temp state
        env[key] = str(tmp_dir)
    report = tmp_dir / "r.xml"
    started = time.time()
    try:
        proc = subprocess.run(  # nosec B603 - fixed argv from a validated allowlist
            build_command(unit, xdist_workers, report),
            cwd=project_root / unit.cwd, env=env, shell=False,
            capture_output=True, text=True, errors="replace", timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return (_RC_TIMEOUT, f"FAULT: unit timed out after {timeout}s",
                time.time() - started, False)
    except OSError as exc:  # uv not on PATH, ENOMEM/EAGAIN on spawn, ...
        return (_RC_SPAWN_FAILED, f"FAULT: could not launch unit: {exc}",
                time.time() - started, False)
    out = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode, out, time.time() - started, report.exists()


def run_suite(project_root: Path, config: SuiteConfig | None = None) -> SuiteResult:
    units = discover_units(project_root)
    if not units:
        raise SuiteConfigError(  # a suite that runs nothing must never report GREEN
            f"no test units discovered under {project_root} - check --project-root.")
    if config is None:
        config = load_suite_config(project_root, [u.id for u in units])
    ensure_xdist_available(config, project_root)  # every entry path, not just the CLI one
    warm_up(project_root)
    budget = _Budget(cpu_budget(config))
    started = time.time()

    # ignore_cleanup_errors: a leaked temp file (a still-open handle on Windows) must
    # never turn a GREEN suite into a traceback - that would be a false STOP. Short path
    # segments keep Windows MAX_PATH headroom for the tests' own fixture trees.
    with tempfile.TemporaryDirectory(prefix="swf0-", ignore_cleanup_errors=True) as tmp:
        tmp_root = Path(tmp)

        def _one(indexed: tuple[int, Unit]) -> UnitResult:
            idx, unit = indexed
            workers = config.xdist.get(unit.id)
            weight = budget.acquire(workers or 1)
            try:  # a unit may never fan out wider than the budget it holds
                rc, out, secs, ran = _exec(unit, project_root, weight if workers else None,
                                           tmp_root / "p" / f"u{idx}", config.timeout_seconds)
            finally:
                budget.release(weight)
            return UnitResult(unit.id, classify(rc, ran), rc, secs, out)

        with cf.ThreadPoolExecutor(max_workers=max(1, len(units))) as pool:
            results = list(pool.map(_one, enumerate(units)))

        # Retries - AFTER the pool drains, so "serially" is literally true, and in a clean
        # temp dir. A TEST failure is re-run WITHOUT xdist (the authoritative old-F0 shape).
        # An INFRA fault is re-run with the IDENTICAL shape, so a deterministic fault (rc 5,
        # usage error, unprovisionable xdist) reproduces and still fails - only a transient
        # concurrency-induced fault recovers.
        by_id = {u.id: u for u in units}
        for idx, res in enumerate(results):
            if res.outcome == PASS:
                continue
            unit = by_id[res.unit_id]
            keep_xdist = res.outcome == INFRA
            workers = config.xdist.get(res.unit_id) if keep_xdist else None
            rc, out, _, ran = _exec(unit, project_root, workers,
                                    tmp_root / "s" / f"u{idx}", config.timeout_seconds)
            res.serial_rc = rc
            if classify(rc, ran) == PASS:
                res.race = True  # keep the FIRST output: it is the evidence
                res.outcome = PASS
                res.retry_kind = RETRY_INFRA if keep_xdist else RETRY_SERIAL
            else:
                res.outcome, res.output = classify(rc, ran), out

    failed = [r for r in results if r.outcome != PASS]
    return SuiteResult(results, 1 if failed else 0, time.time() - started,
                       tuple(config.xdist))


# --- reporting (ASCII only - see module docstring) ---
def _retry_note(res: UnitResult, xdist_ids: tuple[str, ...]) -> str:
    """Say only what was MEASURED. A green retry proves the unit passes when run again;
    it does NOT prove the cause - a flaky test looks identical from here."""
    if res.retry_kind == RETRY_INFRA:
        return (f"  {res.unit_id}: infrastructure fault (rc {res.rc}) that did NOT "
                "reproduce - most likely contention between concurrent units.")
    if res.unit_id in xdist_ids:
        return (f"  {res.unit_id}: red in parallel, GREEN alone. Fix it, or drop it from "
                "suite.xdist.")
    return (f"  {res.unit_id}: red in parallel, GREEN alone. It is NOT xdist-allowlisted, "
            "so this is inter-unit pollution or a flaky test - triage it.")


def _report(result: SuiteResult) -> None:
    for res in sorted(result.results, key=lambda r: -r.seconds):
        tag = {PASS: "PASS", TEST_FAILURE: "FAIL", INFRA: "FAULT"}[res.outcome]
        note = "  [passed on a retry - gate not stopped]" if res.race else ""
        print(f"  {tag:5} {res.seconds:7.1f}s  {res.unit_id}{note}")
    for res in result.results:  # output for what failed AND for a retry (its evidence)
        if res.outcome != PASS or res.race:
            serial = f", retry rc={res.serial_rc}" if res.serial_rc is not None else ""
            print(f"\n{'=' * 70}\n{res.unit_id} "
                  f"({'RETRY-GREEN' if res.race else res.outcome}, rc={res.rc}{serial})"
                  f"\n{'=' * 70}\n{res.output}")
    retried = [r for r in result.results if r.race]
    if retried:
        print("\nWARNING: unit(s) passed only on a retry, so the gate is GREEN but they "
              "are not sound:")
        for res in retried:
            print(_retry_note(res, result.xdist_ids))
    print(f"\nF0 suite: {len(result.results)} units in {result.seconds / 60:.1f} min "
          f"-> {'GREEN' if result.exit_code == 0 else 'RED'}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Run the F0 test suite (parallel units).")
    ap.add_argument("--project-root", default=".", type=Path)
    args = ap.parse_args()
    try:
        result = run_suite(args.project_root.resolve())
    except SuiteConfigError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    _report(result)
    return result.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
