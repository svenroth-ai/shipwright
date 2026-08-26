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
repo tree is shared. The runner's own prose is ASCII-only (#244); a unit's captured pytest output is arbitrary third-party text that discipline never reaches, so `suite_console.py` guards the report instead of losing it to UnicodeEncodeError after the verdict is decided.
"""

from __future__ import annotations

import argparse
import os
import subprocess  # nosec B404 - fixed argv, shell=False; no user-supplied strings
import sys
import tempfile
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TextIO
from uuid import uuid4

# Resolve `shared/` so this file imports the sibling under the SAME dotted name the
# tests use (scripts.tools.*) -> one module object, not two. Binding the generic
# top-level `tools`/`lib` package here would re-create the ADR-045 collision class.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.tools.suite_budget import (  # noqa: E402
    Budget as _Budget, emit_unit_event as _emit_unit_event,
    heartbeat_while as _heartbeat_while,
    run_parallel as _run_parallel,
)
from scripts.tools.suite_diagnostics import write_attempt_evidence  # noqa: E402
from scripts.tools.suite_process import (  # noqa: E402
    RC_CANCELLED as _RC_CANCELLED, read_output_tail as _read_output_tail,
    run_process as _run_process,
)
from scripts.tools.suite_console import print_console  # noqa: E402
from scripts.tools.suite_coverage import (  # noqa: E402
    GATE_FAILED, GATE_PASSED, GateResult, coverage_run_lock, final_exit_code,
    prepare_coverage, run_gate,
)
from scripts.tools.suite_gate_runtime import gate_green_suite  # noqa: E402
from scripts.tools.suite_worktree_diff import source_fingerprint  # noqa: E402
from scripts.tools.suite_race_triage import (  # noqa: E402
    emit_race_followups, resolve_commit,
)
from scripts.tools.suite_report import (  # noqa: E402
    render_retry_block, render_run_report, reproduce_command, suite_command,
)
from scripts.tools.suite_retention import Retention  # noqa: E402
from scripts.tools.suite_host_resources import (  # noqa: E402
    HostLeaseError, f0_cpu_lease, normalize_cpu_weight, uv_warmup_lease,
)
from scripts.tools.suite_timing import (  # noqa: E402
    record_canonical_f0_active_span, record_canonical_f0_active_span_failed,
    record_f0_queue_span,
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
    started_utc: str = ""  # real per-unit dispatch time, not the suite's
    race: bool = False           # passed only on a retry
    retry_kind: str | None = None
    serial_rc: int | None = None
    retry_cmd: str | None = None  # the argv the retry ACTUALLY ran (reproduce-me)
    evidence_path: str | None = None
    retry_evidence_path: str | None = None
    evidence_error: str | None = None
    truncated: bool = False
    cancelled: bool = False


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


def warm_up(project_root: Path) -> None:
    """Create/sync the environment ONCE, serially, before 18 processes race for it.

    One serial call avoids Windows hardlink races from concurrent cold `uv run` calls.
    Best-effort: failure remains a normal unit fault. `pytest-cov` is included because
    coverage instrumentation adds it to nearly every unit environment key.
    """
    try:
        subprocess.run(  # nosec B603 - fixed argv, shell=False
            [*UV_RUN, "--with", "pytest", "--with", "pytest-cov",
             "python", "-c", "pass"],
            cwd=project_root, capture_output=True, text=True, shell=False, timeout=600)
    except (OSError, subprocess.SubprocessError):
        pass


def _exec(unit: Unit, project_root: Path, xdist_workers: int | None, tmp_dir: Path,
          timeout: int | None = None,
          cancel_event: threading.Event | None = None,
          ) -> tuple[int, str, float, bool, bool, bool]:
    """Run one unit. Returns rc, output, seconds, pytest_ran, truncated, cancelled.

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
    log_path = tmp_dir / "attempt.log"
    started = time.monotonic()
    try:
        result = _run_process(
            build_command(unit, xdist_workers, report),
            cwd=project_root / unit.cwd, env=env,
            log_path=log_path, timeout=timeout,
            cancel_event=cancel_event,
        )
    except KeyboardInterrupt:
        if cancel_event is not None:
            cancel_event.set()
        tail, truncated = _read_output_tail(log_path)
        return (_RC_CANCELLED, "FAULT: unit cancelled by operator\n" + tail,
                time.monotonic() - started, report.exists(), truncated, True)
    except OSError as exc:  # uv not on PATH, ENOMEM/EAGAIN on spawn, ...
        return (_RC_SPAWN_FAILED, f"FAULT: could not launch unit: {exc}",
                0.0, False, False, False)
    out = result.tail
    if result.timed_out:
        out = f"FAULT: unit timed out after {timeout}s\n" + out
    elif result.cancelled:
        out = "FAULT: unit cancelled by parent\n" + out
    return (result.returncode, out, result.seconds, report.exists(),
            result.truncated, result.cancelled)


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


def resolve_suite_config(project_root: Path) -> SuiteConfig:
    units = discover_units(project_root)
    if not units:
        raise SuiteConfigError(
            f"no test units discovered under {project_root} - check --project-root.")
    return load_suite_config(project_root, [u.id for u in units])


def _retain_attempt_evidence(project_root: Path, *, run_id: str | None,
                             unit_id: str, phase: str, rc: int, seconds: float,
                             output: str, pytest_ran: bool,
                             truncated: bool) -> tuple[str | None, str | None]:
    """Persist a failed attempt without allowing diagnostics to hide its verdict."""
    try:
        path = write_attempt_evidence(
            project_root, run_id=run_id or "unknown-run", unit_id=unit_id,
            phase=phase, rc=rc, seconds=seconds, tail=output,
            truncated=truncated, pytest_ran=pytest_ran,
        )
    except Exception as exc:  # noqa: BLE001 - the red verdict must still be returned
        return None, f"{type(exc).__name__}: {exc}"
    return path.as_posix(), None


def run_suite(project_root: Path, config: SuiteConfig | None = None, *,
              budget_total: int | None = None, preflight: bool = True,
              heartbeat_seconds: float = 30.0, run_id: str | None = None,
              stream: TextIO | None = None) -> SuiteResult:
    units = discover_units(project_root)
    if not units:
        raise SuiteConfigError(  # a suite that runs nothing must never report GREEN
            f"no test units discovered under {project_root} - check --project-root.")
    if config is None:
        config = load_suite_config(project_root, [u.id for u in units])
    if preflight:
        ensure_xdist_available(config, project_root)
        warm_up(project_root)
    units = instrument_for_coverage(units, project_root, prepare_coverage(project_root))
    requested_budget = budget_total if budget_total is not None else config.max_workers
    budget = _Budget(normalize_cpu_weight(requested_budget))
    cancel_event = threading.Event()
    started = time.time()
    # Every unit's OWN JUnit report, on ANY outcome - not just failures - so
    # stage_f0_evidence.py (AC3) can stage the SAME run F0 already performed
    # instead of a second pytest pass. None (no run_id) means no retention.
    retention = Retention(project_root, run_id) if run_id else None

    def _xdist_workers(unit_id: str) -> int | None:
        requested = config.xdist.get(unit_id)
        return min(requested, budget.total) if requested else None

    # ignore_cleanup_errors: a leaked temp file (a still-open handle on Windows) must
    # never turn a GREEN suite into a traceback - that would be a false STOP. Short path
    # segments keep Windows MAX_PATH headroom for the tests' own fixture trees.
    with tempfile.TemporaryDirectory(prefix="swf0-", ignore_cleanup_errors=True) as tmp:
        tmp_root = Path(tmp)

        for unit in units:
            requested = _xdist_workers(unit.id) or 1
            _emit_unit_event(stream, run_id=run_id, event="queued", unit_id=unit.id,
                             weight=requested)

        def _one(indexed: tuple[int, Unit]) -> UnitResult:
            idx, unit = indexed
            workers = _xdist_workers(unit.id)
            weight = budget.acquire(workers or 1, cancel_event=cancel_event)
            started_utc = datetime.now(timezone.utc).isoformat()
            _emit_unit_event(stream, run_id=run_id, event="start", unit_id=unit.id,
                             weight=weight)
            try:  # a unit may never fan out wider than the budget it holds
                rc, out, secs, ran, truncated, cancelled = _exec(
                    unit, project_root, weight if workers else None,
                    tmp_root / "p" / f"u{idx}", config.timeout_seconds, cancel_event)
            finally:
                budget.release(weight)
            outcome = classify(rc, ran)
            if retention is not None:
                retention.record(unit, tmp_root / "p" / f"u{idx}" / "r.xml", outcome)
            result = UnitResult(
                unit.id, outcome, rc, secs, out, started_utc=started_utc,
                truncated=truncated, cancelled=cancelled)
            if outcome != PASS:
                result.evidence_path, result.evidence_error = _retain_attempt_evidence(
                    project_root, run_id=run_id, unit_id=unit.id, phase="initial",
                    rc=rc, seconds=secs, output=out, pytest_ran=ran,
                    truncated=truncated)
            _emit_unit_event(stream, run_id=run_id, event="complete", unit_id=unit.id,
                             weight=weight, outcome=outcome, seconds=secs)
            return result

        results = _run_parallel(
            units, _one, heartbeat_seconds=heartbeat_seconds,
            run_id=run_id, stream=stream, cancel_event=cancel_event,
        )

        # Retries - AFTER the pool drains, so "serially" is literally true, and in a clean
        # temp dir. A TEST failure is re-run WITHOUT xdist (the authoritative old-F0 shape).
        # An INFRA fault is re-run with the IDENTICAL shape, so a deterministic fault (rc 5,
        # usage error, unprovisionable xdist) reproduces and still fails - only a transient
        # concurrency-induced fault recovers.
        by_id = {u.id: u for u in units}
        completed_units = sum(res.outcome == PASS for res in results)
        for idx, res in enumerate(results):
            if res.outcome == PASS:
                continue
            unit = by_id[res.unit_id]
            keep_xdist = res.outcome == INFRA
            workers = _xdist_workers(res.unit_id) if keep_xdist else None
            _clear_failed_attempt_coverage(unit)
            # Capture the REAL retry argv: a follow-up card that guesses the command
            # is an attractive but unreliable "reproduce me".
            res.retry_cmd = reproduce_command(unit.cwd, build_command(unit, workers))
            retry_weight = _xdist_workers(res.unit_id) if keep_xdist else 1
            retry_state = "identical-shape-infra" if keep_xdist else "authoritative-serial"
            _emit_unit_event(stream, run_id=run_id, event="start", unit_id=res.unit_id,
                             weight=retry_weight or 1, phase="serial-retry",
                             retry_kind=retry_state)
            with _heartbeat_while(
                    heartbeat_seconds=heartbeat_seconds, run_id=run_id,
                    completed=completed_units, total=len(units),
                    initial_completed=len(results),
                    phase="serial-retry",
                    unit_id=res.unit_id, stream=stream):
                rc, out, retry_secs, ran, retry_truncated, retry_cancelled = _exec(
                    unit, project_root, workers, tmp_root / "s" / f"u{idx}",
                    config.timeout_seconds, cancel_event)
            res.serial_rc = rc
            if retry_cancelled:
                res.retry_evidence_path, error = _retain_attempt_evidence(
                    project_root, run_id=run_id, unit_id=unit.id, phase="cancelled-retry",
                    rc=rc, seconds=retry_secs, output=out, pytest_ran=ran,
                    truncated=retry_truncated)
                res.evidence_error = res.evidence_error or error
                _emit_unit_event(
                    stream, run_id=run_id, event="complete", unit_id=res.unit_id,
                    weight=retry_weight or 1, outcome="cancelled",
                    seconds=retry_secs, phase="serial-retry",
                    retry_kind=retry_state)
                raise KeyboardInterrupt
            # retry_kind + the extra wall-clock apply either way (doubt review).
            res.retry_kind = RETRY_INFRA if keep_xdist else RETRY_SERIAL
            res.seconds += retry_secs
            if classify(rc, ran) == PASS:
                res.race = True  # keep the FIRST output: it is the evidence
                res.outcome = PASS
            else:
                res.outcome, res.output = classify(rc, ran), out
                res.truncated = retry_truncated
                res.cancelled = retry_cancelled
                res.retry_evidence_path, error = _retain_attempt_evidence(
                    project_root, run_id=run_id, unit_id=unit.id, phase="retry",
                    rc=rc, seconds=retry_secs, output=out, pytest_ran=ran,
                    truncated=retry_truncated)
                res.evidence_error = res.evidence_error or error
            if retention is not None:  # supersedes the initial attempt's report
                retention.record(unit, tmp_root / "s" / f"u{idx}" / "r.xml", res.outcome)
            _emit_unit_event(stream, run_id=run_id, event="complete",
                             unit_id=res.unit_id, weight=retry_weight or 1,
                             outcome=res.outcome, seconds=retry_secs,
                             phase="serial-retry", retry_kind=retry_state)
            completed_units += 1

    if retention is not None:
        retention.publish()
    failed = [r for r in results if r.outcome != PASS or r.evidence_error]
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


def _gate_green_suite(root: Path, result: SuiteResult,
                      source_before: str | None) -> GateResult:
    return gate_green_suite(root, result, source_before, fingerprint=source_fingerprint)


@contextmanager
def _run_host_leased_suite(root: Path, run_id: str | None):
    """Serialize uv setup, then hold the CPU grant through the F0 verdict."""
    source_before, fingerprint_error = source_fingerprint(root)
    config = resolve_suite_config(root)
    with uv_warmup_lease(root, run_id=run_id) as warmup_grant:
        # Recorded immediately on grant, BEFORE ensure_xdist_available/warm_up
        # run - those can take real time, and capturing "now" only after they
        # finish (as the original code did) shifted the reported queue-wait
        # window later than the real one by however long they took (doubt
        # review). f0_cpu_lease's own call below was already correct.
        record_f0_queue_span(root, run_id, waited_seconds=warmup_grant.waited_seconds,
                             weight=1, capacity=1, stage="warmup")
        ensure_xdist_available(config, root)
        warm_up(root)
    with f0_cpu_lease(root, config, run_id=run_id) as grant:
        record_f0_queue_span(root, run_id, waited_seconds=grant.waited_seconds,
                             weight=grant.weight, capacity=grant.capacity, stage="cpu")
        active_start = datetime.now(timezone.utc)
        try:
            result = run_suite(root, config, budget_total=grant.weight,
                               preflight=False, run_id=run_id)
        except BaseException:
            # A real producer boundary that never returns is exactly the run
            # where attribution matters most - record it incomplete rather
            # than silently losing the span (external code review).
            record_canonical_f0_active_span_failed(
                root, run_id, active_start=active_start,
                weight=grant.weight, capacity=grant.capacity)
            raise
        record_canonical_f0_active_span(
            root, run_id, active_start=active_start, result=result,
            weight=grant.weight, capacity=grant.capacity)
        yield result, source_before, fingerprint_error


def _finish_locked(root: Path, run_id: str | None, result: SuiteResult,
                   source_before: str | None, fingerprint_error: str | None) -> int:
    # Record BEFORE reporting and before ANY return: a red sibling must never skip it.
    races = unrecorded_races(result)
    report = emit_race_followups(root, races, result.xdist_ids, run_id=run_id,
                                 commit=resolve_commit(root),
                                 suite_command=suite_command(root, run_id))
    # Print the suite's own evidence FIRST: the gate below can take a minute, and a
    # finished suite's results must not be withheld for it - nor lost if it is
    # interrupted part-way through.
    for line in render_run_report(result) + render_retry_block(result, races, report):
        print_console(line)
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
        print_console(line)
    return final_exit_code(result.exit_code, report.failed, gate)


def _run_locked(root: Path, run_id: str | None) -> int:
    """The full reset -> suite -> combine -> gate critical section."""
    with _run_host_leased_suite(root, run_id) as leased:
        result, source_before, fingerprint_error = leased
        return _finish_locked(root, run_id, result, source_before, fingerprint_error)


def main() -> int:
    ap = argparse.ArgumentParser(description="Run the F0 test suite (parallel units).")
    ap.add_argument("--project-root", default=".", type=Path)
    ap.add_argument("--run-id", default=None,
                    help="stable diagnostic id; generated when omitted")
    args = ap.parse_args()
    root = args.project_root.resolve()
    run_id = args.run_id or f"f0-{uuid4().hex}"
    if args.run_id is None:
        print(f"F0 invocation: run_id={run_id}")
    try:
        with coverage_run_lock(root):
            return _run_locked(root, run_id)
    except KeyboardInterrupt:
        print("F0 suite cancelled: owned test processes were terminated and reaped.",
              file=sys.stderr)
        return _RC_CANCELLED
    except (SuiteConfigError, HostLeaseError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
