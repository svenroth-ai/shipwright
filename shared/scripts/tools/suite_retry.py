#!/usr/bin/env python3
"""F0 suite runner - the serial retry of a unit that failed its parallel attempt.

Extracted from `run_test_suite.run_suite` (that module sits at its bloat baseline) and
given ONE new behaviour: a TEST failure is retried on the red tests only, when
`suite_failed_only.failed_only_count` proves the pytest cache describes the attempt;
every other case (and every doubt) is the whole-unit serial retry the runner always had.

The runner's own seams (`_exec`, evidence retention, coverage clearing, the event
emitter, ...) arrive in a `RetryOps` built when `run_suite` RUNS, not when this module
is imported - so a test that patches `run_test_suite._exec` still intercepts the retry.

Honest scope of the narrow retry: a test that is red only because ANOTHER test of its
unit left state behind passes alone, so it would read as a race here although a whole
serial run (CI) keeps it red. That is why the failed-only path (a) is capped at
`FAILED_ONLY_MAX_TESTS` (wide failure is pollution-shaped), (b) keeps its OWN
`retry_kind`, and (c) is still recorded as a race in the Triage Inbox - the card tells a
human to establish which one it was. CI stays the authoritative full serial gate.

ASCII-only operator strings (a cp1252 console raises UnicodeEncodeError, #244).
"""

from __future__ import annotations

import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, NamedTuple, TextIO

from scripts.tools.suite_failed_only import (
    failed_only_args, failed_only_count, merge_junit, testcase_count,
)
from scripts.tools.suite_units import INFRA, PASS, TEST_FAILURE

#: how a unit recovered on its retry - purely for an honest operator message
RETRY_SERIAL = "serial"   # a test failure that passed when run alone, without xdist
RETRY_INFRA = "infra"     # a transient infrastructure fault that did not reproduce
RETRY_FAILED_ONLY = "failed-only"  # the red tests alone passed (the rest were not re-run)
#: more red tests than this looks like state pollution, not a race: re-run the whole unit
FAILED_ONLY_MAX_TESTS = 10
_WHOLE = "authoritative-serial"
_INCOMPLETE_MARKERS = ("stopping after", "worker crashed", "node down", "crashed while running")


@dataclass(frozen=True)
class RetryOps:
    """The runner's seams, resolved at call time (see the module docstring)."""

    exec_fn: Callable[..., tuple]
    retain_fn: Callable[..., tuple]
    clear_cov_fn: Callable[..., None]
    build_fn: Callable[..., list]
    repro_fn: Callable[..., str]
    emit_fn: Callable[..., None]
    heartbeat_fn: Callable[..., Any]
    classify_fn: Callable[..., str]
    workers_fn: Callable[[str], int | None]


class _Attempt(NamedTuple):
    rc: int
    out: str
    secs: float          # the attempt that produced the verdict
    ran: bool
    truncated: bool
    cancelled: bool
    report: Path
    narrow: bool         # False once a narrow try fell back to the whole unit
    extra_secs: float    # wall-clock of a discarded narrow try


def _expected_failed(res, attempt_dir: Path) -> int:
    """How many red tests a narrow retry must re-run; 0 = the narrow path is not allowed."""
    if res.outcome != TEST_FAILURE:
        return 0
    # A stopped run (-x/--maxfail) or a crashed xdist worker leaves tests un-run / coverage
    # lost: the unit is not described by its red tests, so re-run it whole.
    if any(marker in res.output for marker in _INCOMPLETE_MARKERS):
        return 0
    n = failed_only_count(attempt_dir / "c", attempt_dir / "r.xml")
    return n if 0 < n <= FAILED_ONLY_MAX_TESTS else 0


def _run_attempt(ops: RetryOps, unit, project_root: Path, dirs: tuple[Path, Path, Path],
                 *, workers: int | None, expected: int, timeout: int | None,
                 cancel_event: threading.Event, emit: Callable[..., None]) -> _Attempt:
    """Execute the retry; a narrow try that cannot be trusted becomes the whole-unit run.

    Runs INSIDE the caller's heartbeat context so the (up to ~22 min) fallback is as
    visible as any other retry.
    """
    initial_dir, retry_dir, merged_dir = dirs
    report = retry_dir / "r.xml"
    extra = 0.0
    if expected:
        rc, out, secs, ran, trunc, cancelled = ops.exec_fn(
            unit, project_root, None, retry_dir, timeout, cancel_event,
            cache_dir=initial_dir / "c", extra_args=failed_only_args(unit))
        if cancelled:
            return _Attempt(rc, out, secs, ran, trunc, cancelled, report, True, 0.0)
        merged = merged_dir / "r.xml"
        # Trust the narrow verdict only if pytest re-ran EXACTLY the red tests: fewer means
        # `--lf` skipped an id it could no longer collect (a vanished red test), more means
        # no id matched and pytest ran everything (a whole run whose coverage must not append).
        if (ops.classify_fn(rc, ran) != INFRA
                and testcase_count(report) == expected
                and merge_junit(initial_dir / "r.xml", report, merged)):
            return _Attempt(rc, out, secs, ran, trunc, False, merged, True, 0.0)
        # rc 5 (nothing selected), a crash, a short re-run or an unmergeable report:
        # never guess - the whole-unit retry, exactly as before.
        ops.clear_cov_fn(unit)
        report.unlink(missing_ok=True)  # a stale narrow report must not pose as this run's
        extra = secs
        emit(event="start", phase="serial-retry", retry_kind=_WHOLE)
    rc, out, secs, ran, trunc, cancelled = ops.exec_fn(
        unit, project_root, workers, retry_dir, timeout, cancel_event)
    return _Attempt(rc, out, secs, ran, trunc, cancelled, report, False, extra)


def retry_red_units(results: list, by_id: dict, ops: RetryOps, *, project_root: Path,
                    tmp_root: Path, timeout: int | None, cancel_event: threading.Event,
                    stream: TextIO | None, heartbeat_seconds: float, run_id: str | None,
                    retention: Any) -> None:
    """Retry every non-PASS result once, AFTER the pool drained; mutates `results`."""
    completed_units = sum(res.outcome == PASS for res in results)
    for idx, res in enumerate(results):
        if res.outcome == PASS:
            continue
        unit = by_id[res.unit_id]
        keep_xdist = res.outcome == INFRA
        workers = ops.workers_fn(res.unit_id) if keep_xdist else None
        dirs = (tmp_root / "p" / f"u{idx}", tmp_root / "s" / f"u{idx}",
                tmp_root / "m" / f"u{idx}")
        expected = 0 if keep_xdist else _expected_failed(res, dirs[0])
        repro_temp = Path(tempfile.gettempdir()) / "swf0-repro"  # short, like the real one
        res.retry_cmd = ops.repro_fn(unit.cwd, ops.build_fn(unit, workers, basetemp=repro_temp))
        weight = (ops.workers_fn(res.unit_id) if keep_xdist else 1) or 1

        def emit(*, event: str, **kw: Any) -> None:
            ops.emit_fn(stream, run_id=run_id, event=event, unit_id=res.unit_id,
                        weight=weight, **kw)

        state = ("identical-shape-infra" if keep_xdist
                 else "failed-only" if expected else _WHOLE)
        if not expected:
            ops.clear_cov_fn(unit)
        emit(event="start", phase="serial-retry", retry_kind=state)
        with ops.heartbeat_fn(
                heartbeat_seconds=heartbeat_seconds, run_id=run_id,
                completed=completed_units, total=len(by_id),
                initial_completed=len(results), phase="serial-retry",
                unit_id=res.unit_id, stream=stream):
            att = _run_attempt(ops, unit, project_root, dirs, workers=workers,
                               expected=expected, timeout=timeout,
                               cancel_event=cancel_event, emit=emit)
        if expected and not att.narrow:
            state = _WHOLE
        outcome = ops.classify_fn(att.rc, att.ran)
        res.serial_rc = att.rc
        if att.cancelled:
            res.retry_evidence_path, error = ops.retain_fn(
                project_root, run_id=run_id, unit_id=unit.id, phase="cancelled-retry",
                rc=att.rc, seconds=att.secs, output=att.out, pytest_ran=att.ran,
                truncated=att.truncated)
            res.evidence_error = res.evidence_error or error
            emit(event="complete", outcome="cancelled", seconds=att.secs,
                 phase="serial-retry", retry_kind=state)
            raise KeyboardInterrupt
        # retry_kind + the extra wall-clock apply either way (doubt review).
        res.retry_kind = (RETRY_INFRA if keep_xdist
                          else RETRY_FAILED_ONLY if att.narrow else RETRY_SERIAL)
        res.seconds += att.secs + att.extra_secs
        if outcome == PASS:
            res.race = True  # keep the FIRST output: it is the evidence
            res.outcome = PASS
        else:
            res.outcome, res.output = outcome, att.out
            res.truncated, res.cancelled = att.truncated, att.cancelled
            res.retry_evidence_path, error = ops.retain_fn(
                project_root, run_id=run_id, unit_id=unit.id, phase="retry",
                rc=att.rc, seconds=att.secs, output=att.out, pytest_ran=att.ran,
                truncated=att.truncated)
            res.evidence_error = res.evidence_error or error
        if retention is not None:  # supersedes the initial attempt's report
            retention.record(unit, att.report, res.outcome)
        emit(event="complete", outcome=res.outcome, seconds=att.secs,
             phase="serial-retry", retry_kind=state)
        completed_units += 1
