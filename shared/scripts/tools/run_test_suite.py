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
  verdict is authoritative, so a race can never cause a false STOP. It also never
  EVAPORATES: `suite_race_triage` writes the unit into the tracked Triage Inbox, and a
  race that could not be recorded stops an otherwise-green run with rc 3 - a warning
  that dies with the session is how a race comes back when it is expensive.
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

from scripts.tools.suite_coverage import (  # noqa: E402
    GATE_FAILED, GATE_PASSED, GateResult, build_worktree_diff, compare_branch,
    coverage_run_lock, final_exit_code, prepare_coverage, run_gate,
)
from scripts.tools.suite_worktree_diff import source_fingerprint  # noqa: E402
from scripts.tools.suite_race_triage import (  # noqa: E402
    emit_race_followups, resolve_commit,
)
from scripts.tools.suite_report import (  # noqa: E402
    render_retry_block, render_run_report, reproduce_command, suite_command,
)
from scripts.tools.suite_units import (  # noqa: E402  (re-export: one import site)
    INFRA,
    PASS,
    TEST_FAILURE,
    UV_RUN,
    SuiteConfig,
    SuiteConfigError,
    Unit,
    discover_units,
    ensure_xdist_available,
    instrument_for_coverage,
    load_suite_config,
)

_RC_TIMEOUT = 124        # conventional timeout rc; INFRA like any other fault
_RC_SPAWN_FAILED = 126

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
    retry_cmd: str | None = None  # the argv the retry ACTUALLY ran (reproduce-me)


@dataclass
class SuiteResult:
    results: list[UnitResult]
    exit_code: int
    seconds: float
    xdist_ids: tuple[str, ...] = field(default_factory=tuple)
    #: coverage data files the instrumented units were told to write. Empty means
    #: "nothing to gate"; a NAMED file that never appeared means the measurement
    #: evaporated - the gate must not confuse the two.
    cov_files: tuple[str, ...] = ()


def build_command(unit: Unit, xdist_workers: int | None, report: Path | None = None) -> list[str]:
    """argv only - never a shell string (config/paths must not reach a shell)."""
    cmd = [*UV_RUN, "--with", "pytest", "--with", "pytest-mock"]
    for dep in unit.extra_deps:
        cmd += ["--with", dep]
    if xdist_workers:
        cmd += ["--with", "pytest-xdist"]  # provisioned, not assumed (AC12)
    cmd += ["pytest", unit.target, "-q", "-p", "no:cacheprovider"]
    # Coverage args go AFTER the markers: a CLI `-m` REPLACES the pyproject default,
    # so anything wedged between `-m` and its expression would silently rewrite the
    # shared tier's selection rather than add to it.
    cmd += [*unit.markers, *unit.cov_args]
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
    hardlink-race source on Windows). One warm serial call turns that into a no-op, for
    the interpreter UV_RUN pins. Best-effort: a failure here is a normal unit fault.

    `pytest-cov` is warmed too: coverage instrumentation adds it to nearly every unit's
    env key, so leaving it out would re-create the very contention this exists to remove
    on the first run after any pytest-cov release.
    """
    try:
        subprocess.run(  # nosec B603 - fixed argv, shell=False
            [*UV_RUN, "--with", "pytest", "--with", "pytest-cov",
             "python", "-c", "pass"],
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
    # Per-unit data file, never a shared one: the pool runs these CONCURRENTLY. Popped
    # first so an UNinstrumented unit cannot inherit an ambient COVERAGE_FILE from the
    # operator's shell and scribble into someone else's tier.
    env.pop("COVERAGE_FILE", None)
    if unit.cov_file:
        env["COVERAGE_FILE"] = unit.cov_file
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


def _clear_failed_attempt_coverage(unit: Unit) -> None:
    """Discard coverage from an attempt whose verdict was not accepted.

    pytest-cov/xdist may suffix ``COVERAGE_FILE``. Combining a failed parallel
    attempt with its authoritative retry can cover lines the successful retry never
    executed and false-green the gate, so both the base and exact suffix family go.
    """
    if not unit.cov_file:
        return
    base = Path(unit.cov_file)
    candidates = [base, *base.parent.glob(f"{base.name}.*")]
    for path in candidates:
        try:
            path.unlink(missing_ok=True)
        except OSError as exc:
            raise SuiteConfigError(
                f"could not discard failed-attempt coverage {path}: {exc}") from exc


def run_suite(project_root: Path, config: SuiteConfig | None = None) -> SuiteResult:
    units = discover_units(project_root)
    if not units:
        raise SuiteConfigError(  # a suite that runs nothing must never report GREEN
            f"no test units discovered under {project_root} - check --project-root.")
    if config is None:
        config = load_suite_config(project_root, [u.id for u in units])
    ensure_xdist_available(config, project_root)  # every entry path, not just the CLI one
    warm_up(project_root)
    units = instrument_for_coverage(units, project_root, prepare_coverage(project_root))
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
            _clear_failed_attempt_coverage(unit)
            # Capture the REAL retry argv: a follow-up card that guesses the command
            # is an attractive but unreliable "reproduce me".
            res.retry_cmd = reproduce_command(unit.cwd, build_command(unit, workers))
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
                       tuple(config.xdist),
                       tuple(u.cov_file for u in units if u.cov_file))


def unrecorded_races(result: SuiteResult) -> list[UnitResult]:
    """Units red in parallel and GREEN on the authoritative ALONE re-run.

    The ONE owner of this rule (the producer holds no copy): `RETRY_SERIAL` is set
    only when the parallel outcome was a genuine pytest TEST failure - every other
    class (rc 2/3/4/5, timeout, spawn failure, rc 1 with no report) is INFRA.
    """
    return [r for r in result.results if r.race and r.retry_kind == RETRY_SERIAL]


def _source_snapshot_error(root: Path, expected: str | None) -> str:
    current, error = source_fingerprint(root)
    if error:
        return error
    if current != expected:
        return ("Python sources or test/coverage configuration changed while "
                "coverage was being measured; re-run F0 on the final working tree")
    return ""


def _gate_green_suite(root: Path, result: SuiteResult,
                      source_before: str | None) -> GateResult:
    error = _source_snapshot_error(root, source_before)
    if error:
        return GateResult(GATE_FAILED, [f"diff-coverage: FAILED - {error}."])
    branch = compare_branch(root)
    if branch is None:
        return run_gate(root, expected=result.cov_files, branch=None,
                        diff_file=None, suite_green=True)
    error = _source_snapshot_error(root, source_before)
    if error:
        return GateResult(GATE_FAILED, [f"diff-coverage: FAILED - {error}."])
    diff_file, diff_error = build_worktree_diff(root, branch)
    error = diff_error or _source_snapshot_error(root, source_before)
    if error:
        return GateResult(GATE_FAILED, [f"diff-coverage: FAILED - {error}."])
    gate = run_gate(root, expected=result.cov_files, branch=branch,
                    diff_file=diff_file, suite_green=True)
    error = _source_snapshot_error(root, source_before)
    return (GateResult(GATE_FAILED, [f"diff-coverage: FAILED - {error}."])
            if error else gate)


def _run_locked(root: Path, run_id: str | None) -> int:
    """The full reset -> suite -> combine -> gate critical section."""
    source_before, fingerprint_error = source_fingerprint(root)
    result = run_suite(root)
    # Record BEFORE reporting and before ANY return: a red sibling must never skip it.
    races = unrecorded_races(result)
    report = emit_race_followups(root, races, result.xdist_ids, run_id=run_id,
                                 commit=resolve_commit(root),
                                 suite_command=suite_command(root, run_id))
    # Print the suite's own evidence FIRST: the gate below can take a minute, and a
    # finished suite's results must not be withheld for it - nor lost if it is
    # interrupted part-way through.
    for line in render_run_report(result) + render_retry_block(result, races, report):
        print(line)
    # The gate CI runs, run here: an under-tested diff STOPs the run instead of
    # reddening a PR after the iterate has already reported done. A red suite (or
    # higher-priority evidence-recording failure) must not fetch, prompt, or hang.
    if result.exit_code != 0:
        gate = run_gate(root, expected=result.cov_files, branch=None, diff_file=None,
                        suite_green=False)
    elif report.failed:
        gate = GateResult(GATE_PASSED, [
            "diff-coverage: skipped - race evidence could not be recorded."])
    else:
        if fingerprint_error:
            gate = GateResult(GATE_FAILED, [
                f"diff-coverage: FAILED - {fingerprint_error}."])
        else:
            gate = _gate_green_suite(root, result, source_before)
    for line in gate.lines:
        print(line)
    return final_exit_code(result.exit_code, report.failed, gate)


def main() -> int:
    ap = argparse.ArgumentParser(description="Run the F0 test suite (parallel units).")
    ap.add_argument("--project-root", default=".", type=Path)
    ap.add_argument("--run-id", default=None, help="stamped onto any follow-up filed")
    args = ap.parse_args()
    root = args.project_root.resolve()
    try:
        with coverage_run_lock(root):
            return _run_locked(root, args.run_id)
    except SuiteConfigError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
