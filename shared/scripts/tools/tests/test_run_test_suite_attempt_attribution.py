"""F0 producer timing: per-attempt numbering and per-unit invocation records.

Split out of ``test_run_test_suite_timing.py`` at the ~300-line file-size
guideline (test-phase-attribution) — that file keeps the base f0_queue/
canonical_f0_active recording tests; this one covers the two things this
change adds on top: attempt auto-numbering (Design §1) and per-unit
``f0_unit_result`` emission (Design §2), plus the import-path landmine
probe (AC9) both share.
"""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

_SHARED = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(_SHARED))

import scripts.lib.iterate_timings_normalize as itn
import scripts.tools.suite_timing as mod

RUN = "iterate-2026-08-04-iterate-timing-attribution"


# --------------------------------------------------------------------------- #
# Attempt auto-numbering (test-phase-attribution AC2/AC7/AC8/AC12)
# --------------------------------------------------------------------------- #

def test_attempt_resolves_to_n_plus_1_from_a_synthetic_sidecar(tmp_path):
    """AC2 — verified via a synthetic sidecar, never via a live F0 run: F0.md's
    STOP-before-retry protocol means a green run invokes F0 exactly once, so
    attempt never leaves 1 in a real run this session could produce. Each
    simulated attempt below is its own process — the cache is cleared between
    them, matching how a real whole-suite re-invocation is always a fresh
    OS process, never a second call inside the same one (Design §1)."""
    start = datetime(2026, 8, 4, 10, 0, 0, tzinfo=timezone.utc)
    for _ in range(3):
        mod._attempt_cache.clear()  # a fresh process never inherits another's cache
        mod.record_canonical_f0_active_span_failed(tmp_path, RUN, active_start=start,
                                                    weight=1, capacity=1)
    attempts = [e["attempt"] for e in itn.read_raw_events(tmp_path, RUN)
               if e["name"] == "canonical_f0_active"]
    assert attempts == [1, 2, 3]


def test_orphaned_cpu_f0_queue_with_no_canonical_still_advances(tmp_path):
    """AC7 — a process killed between the CPU-lease grant and the ``except``
    boundary leaves a cpu-stage f0_queue with no canonical_f0_active partner;
    the next invocation must not collide with it."""
    mod.record_f0_queue_span(tmp_path, RUN, waited_seconds=5.0, weight=1, capacity=1,
                             stage="cpu")
    mod._attempt_cache.clear()
    start = datetime(2026, 8, 4, 10, 0, 0, tzinfo=timezone.utc)
    mod.record_canonical_f0_active_span_failed(tmp_path, RUN, active_start=start,
                                                weight=1, capacity=1)
    raw = itn.read_raw_events(tmp_path, RUN)
    canonical = next(e for e in raw if e["name"] == "canonical_f0_active")
    assert canonical["attempt"] == 2


def test_orphaned_warmup_only_f0_queue_still_advances(tmp_path):
    """AC8 — a process killed during the CPU-lease WAIT itself (the largest
    window, per plan review) leaves only a warmup-stage f0_queue, no cpu
    f0_queue, no canonical_f0_active. Counting cpu+canonical alone would
    compute max(0, 0) + 1 == 1, colliding with the orphaned attempt 1."""
    mod.record_f0_queue_span(tmp_path, RUN, waited_seconds=5.0, weight=1, capacity=1,
                             stage="warmup")
    mod._attempt_cache.clear()
    start = datetime(2026, 8, 4, 10, 0, 0, tzinfo=timezone.utc)
    mod.record_canonical_f0_active_span_failed(tmp_path, RUN, active_start=start,
                                                weight=1, capacity=1)
    raw = itn.read_raw_events(tmp_path, RUN)
    canonical = next(e for e in raw if e["name"] == "canonical_f0_active")
    assert canonical["attempt"] == 2


def test_legacy_f0_queue_with_no_stage_key_counts_as_cpu(tmp_path):
    """AC12 — every real f0_queue entry recorded before this change has no
    `stage` key at all; the counting policy must read it as "cpu", not
    "warmup", and must not crash on it."""
    import scripts.lib.iterate_timings as it_lib
    it_lib.record_producer_span(
        tmp_path, RUN, name="f0_queue", parent="verification",
        start_utc="2026-08-04T10:00:00+00:00", end_utc="2026-08-04T10:00:01+00:00",
        duration_ms=1000, extra={"weight": 1, "capacity": 1})  # no "stage" key
    mod._attempt_cache.clear()
    start = datetime(2026, 8, 4, 10, 0, 0, tzinfo=timezone.utc)
    mod.record_canonical_f0_active_span_failed(tmp_path, RUN, active_start=start,
                                                weight=1, capacity=1)
    raw = itn.read_raw_events(tmp_path, RUN)
    canonical = next(e for e in raw if e["name"] == "canonical_f0_active")
    assert canonical["attempt"] == 2  # not 1 — the legacy entry counted, as cpu


def test_a_truthy_non_dict_extra_counts_as_cpu_without_raising(tmp_path):
    """Doubt review: a hand-corrupted sidecar line whose `extra` is valid
    JSON but not a dict (a string, a list) must not raise inside
    _count_prior_attempts - it runs INSIDE the resolver's lock, and the
    poisoned line never leaves the file, so a crash there would break every
    future attempt resolution in the run, not just this one call."""
    entries = [
        {"event": "span", "name": "f0_queue", "extra": "not-a-dict"},
        {"event": "span", "name": "f0_queue", "extra": ["also", "not", "a", "dict"]},
    ]
    assert mod._count_prior_attempts(entries) == 2  # both counted as cpu, no raise


def test_same_process_calls_share_one_resolved_attempt(tmp_path):
    """The warmup f0_queue, cpu f0_queue, and canonical_f0_active calls in ONE
    real F0 invocation must all resolve to the SAME attempt number — the
    generalized "whichever call is first to write resolves; the rest reuse
    the cache" rule."""
    mod.record_f0_queue_span(tmp_path, RUN, waited_seconds=5.0, weight=1, capacity=1,
                             stage="warmup")
    mod.record_f0_queue_span(tmp_path, RUN, waited_seconds=3.0, weight=1, capacity=1,
                             stage="cpu")
    start = datetime(2026, 8, 4, 10, 0, 0, tzinfo=timezone.utc)
    result = SimpleNamespace(seconds=10.0, results=[])
    mod.record_canonical_f0_active_span(tmp_path, RUN, active_start=start, result=result,
                                        weight=1, capacity=1)
    raw = itn.read_raw_events(tmp_path, RUN)
    assert {e["attempt"] for e in raw} == {1}


# --------------------------------------------------------------------------- #
# Per-unit invocation records (test-phase-attribution AC3/AC4/AC13)
# --------------------------------------------------------------------------- #

def _unit(unit_id="shared/tests", outcome="pass", seconds=12.5,
         started_utc="2026-08-04T10:18:02+00:00", retry_kind=None):
    return SimpleNamespace(unit_id=unit_id, outcome=outcome, seconds=seconds,
                           started_utc=started_utc, retry_kind=retry_kind)


def test_normal_return_emits_one_span_per_unit_under_the_parent(tmp_path):
    """AC3 — each UnitResult from a normally-returned run_suite() call,
    including test failures (which do not raise), is persisted with its own
    real started_utc, correctly attached under canonical_f0_active by the
    existing fold."""
    start = datetime(2026, 8, 4, 10, 18, 0, tzinfo=timezone.utc)
    result = SimpleNamespace(seconds=30.0, results=[
        _unit("shared/tests", "pass", 12.5, "2026-08-04T10:18:02+00:00"),
        _unit("plugins/shipwright-build/tests", "test_failure", 8.0,
             "2026-08-04T10:18:05+00:00", retry_kind="serial"),
    ])
    mod.record_canonical_f0_active_span(tmp_path, RUN, active_start=start, result=result,
                                        weight=1, capacity=1)
    valid, rejected = itn.normalize_iterate_timings(itn.read_raw_events(tmp_path, RUN))
    assert not rejected
    units = [s for s in valid if s["name"] == "f0_unit_result"]
    assert len(units) == 2
    assert all(s["parent"] == "canonical_f0_active" for s in units)
    assert all(s["outcome"] == "completed" for s in units)
    by_id = {s["extra"]["unit"]: s for s in units}
    assert by_id["shared/tests"]["extra"]["conclusion"] == "pass"
    assert "retry_shape" not in by_id["shared/tests"]["extra"]
    assert by_id["plugins/shipwright-build/tests"]["extra"]["conclusion"] == "test_failure"
    assert by_id["plugins/shipwright-build/tests"]["extra"]["retry_shape"] == "serial"
    assert by_id["shared/tests"]["start_utc"] == "2026-08-04T10:18:02+00:00"


def test_unit_end_utc_is_clamped_to_the_parent_and_never_negative(tmp_path):
    """A unit whose own seconds/clock skew would push end_utc past the
    parent's own end, or a negative seconds value, must not produce an
    inverted or out-of-parent interval."""
    start = datetime(2026, 8, 4, 10, 18, 0, tzinfo=timezone.utc)
    result = SimpleNamespace(seconds=5.0, results=[
        _unit("shared/tests", "pass", 999.0, "2026-08-04T10:18:00+00:00"),
        _unit("plugins/shipwright-build/tests", "pass", -3.0, "2026-08-04T10:18:01+00:00"),
    ])
    mod.record_canonical_f0_active_span(tmp_path, RUN, active_start=start, result=result,
                                        weight=1, capacity=1)
    raw = {e["extra"]["unit"]: e for e in itn.read_raw_events(tmp_path, RUN)
          if e["name"] == "f0_unit_result"}
    parent_end = "2026-08-04T10:18:05+00:00"  # active_start + result.seconds (5.0)
    assert raw["shared/tests"]["end_utc"] == parent_end  # clamped, not overshooting
    negative = raw["plugins/shipwright-build/tests"]
    assert negative["end_utc"] == negative["start_utc"]  # floored at 0, never inverted


def test_unit_started_after_parent_end_never_inverts_the_interval(tmp_path):
    """External code review: end_utc was clamped to parent_end, but start_utc
    was not - a unit.started_utc past parent_end (clock skew, a hand-built
    UnitResult) produced end_utc < start_utc. The start must clamp too."""
    start = datetime(2026, 8, 4, 10, 18, 0, tzinfo=timezone.utc)
    result = SimpleNamespace(seconds=5.0, results=[
        _unit("shared/tests", "pass", 1.0, "2026-08-04T10:18:30+00:00"),  # 25s past parent_end
    ])
    mod.record_canonical_f0_active_span(tmp_path, RUN, active_start=start, result=result,
                                        weight=1, capacity=1)
    raw = itn.read_raw_events(tmp_path, RUN)
    unit = next(e for e in raw if e["name"] == "f0_unit_result")
    parent_end = "2026-08-04T10:18:05+00:00"
    assert unit["start_utc"] == parent_end  # clamped down into the parent interval
    assert unit["end_utc"] == parent_end
    assert unit["duration_ms"] == 0


def test_failed_run_never_emits_unit_results(tmp_path):
    """AC4 — the exception path has no SuiteResult, so no f0_unit_result
    spans are attempted; F0 must not raise or break."""
    start = datetime(2026, 8, 4, 10, 18, 2, tzinfo=timezone.utc)
    mod.record_canonical_f0_active_span_failed(tmp_path, RUN, active_start=start,
                                                weight=1, capacity=1)
    raw = itn.read_raw_events(tmp_path, RUN)
    assert [e["name"] for e in raw] == ["canonical_f0_active"]


def test_a_truthy_non_iterable_results_field_degrades_instead_of_raising(tmp_path):
    """External code review: `result.results` is read by a bare `for unit in
    units:` with no enclosing try/except at the call site — a shape mismatch
    (a test double, a future refactor) that is truthy but not iterable must
    degrade like every other timing failure in this module, not propagate
    out and abort an F0 run whose suite already passed and whose parent span
    is already durably written."""
    start = datetime(2026, 8, 4, 10, 18, 0, tzinfo=timezone.utc)
    result = SimpleNamespace(seconds=5.0, results=1)  # truthy, not iterable
    mod.record_canonical_f0_active_span(tmp_path, RUN, active_start=start, result=result,
                                        weight=1, capacity=1)  # must not raise
    raw = itn.read_raw_events(tmp_path, RUN)
    assert [e["name"] for e in raw] == ["canonical_f0_active"]  # parent kept, no unit spans


def test_overlength_unit_id_degrades_only_that_span(tmp_path):
    """AC13 — a unit id over the 80-char extra bound must not lose its
    siblings' spans; the degradation is explicit (that one span skipped),
    not a silent whole-batch loss."""
    start = datetime(2026, 8, 4, 10, 18, 0, tzinfo=timezone.utc)
    too_long = "x" * 81
    result = SimpleNamespace(seconds=10.0, results=[
        _unit(too_long, "pass", 1.0, "2026-08-04T10:18:01+00:00"),
        _unit("shared/tests", "pass", 1.0, "2026-08-04T10:18:02+00:00"),
    ])
    mod.record_canonical_f0_active_span(tmp_path, RUN, active_start=start, result=result,
                                        weight=1, capacity=1)
    raw = [e for e in itn.read_raw_events(tmp_path, RUN) if e["name"] == "f0_unit_result"]
    assert len(raw) == 1
    assert raw[0]["extra"]["unit"] == "shared/tests"


# --------------------------------------------------------------------------- #
# Import-path landmine (AC9) — the real F0 process only puts `shared/` on
# sys.path; iterate_timings_normalize/pairing/synthesis are NOT importable
# there. A same-process test can stay green via pytest's own broader
# resolution while the real entry point raises ModuleNotFoundError, so this
# spawns a genuinely fresh subprocess with sys.path restricted to `shared/`.
# --------------------------------------------------------------------------- #

def test_suite_timing_imports_cleanly_with_only_shared_on_sys_path(tmp_path):
    """External code review: the import succeeding is only half of AC9 -
    record_f0_queue_span swallows every runtime exception and only prints
    'skipped' to stderr, so this probe would stay green even if the NEW
    counted-resolver path (the code this run actually added) failed at CALL
    time under the restricted sys.path, not just at import time. Assert the
    resolver actually ran: no 'skipped' diagnostic, and a real attempt was
    written to the sidecar."""
    probe = (
        "import sys\n"
        f"sys.path.insert(0, {str(_SHARED)!r})\n"
        "from scripts.tools.suite_timing import record_f0_queue_span\n"
        "record_f0_queue_span(\n"
        f"    {str(tmp_path)!r}, {RUN!r}, waited_seconds=5.0, weight=1, capacity=1,\n"
        "    stage='cpu')\n"
        "print('OK')\n"
    )
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    result = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, text=True,
        cwd=str(tmp_path), env=env)
    assert result.returncode == 0, result.stderr
    assert "OK" in result.stdout
    assert "ModuleNotFoundError" not in result.stderr
    assert "skipped" not in result.stderr, result.stderr
    raw = itn.read_raw_events(tmp_path, RUN)
    assert [e["name"] for e in raw] == ["f0_queue"]
    assert raw[0]["attempt"] == 1
