"""Deterministic, event-log-only report generation for iterate throughput.

Covers: reproducibility from shipwright_events.jsonl alone, pre-instrumentation
runs identified plainly (never as zero), degraded/partial coverage surfaced,
and CI-retry attribution showing through into the rendered nested table.
Pure ``run_stat()`` computation tests (no report I/O) live in
``test_iterate_throughput_stats.py`` — split at ~300 lines.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(_SCRIPTS))

from lib import iterate_timings as it  # noqa: E402
from lib import iterate_timings_normalize as itn  # noqa: E402
from lib.iterate_throughput_stats import iterate_work_completed_events, run_stat  # noqa: E402
from tools.iterate_throughput_report import compute_report, write_report  # noqa: E402


def _events_file(project: Path) -> Path:
    path = project / "shipwright_events.jsonl"
    if not path.exists():
        path.write_text("", encoding="utf-8")
    return path


def _write_work_completed(project: Path, run_id: str, ts: str, iterate_timings=None) -> None:
    event = {"type": "work_completed", "source": "iterate", "adr_id": run_id, "ts": ts}
    if iterate_timings is not None:
        event["iterate_timings"] = iterate_timings
    path = _events_file(project)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event) + "\n")


def test_report_is_empty_state_with_no_events(tmp_path):
    report = compute_report(tmp_path)
    assert "No iterate `work_completed` events found yet." in report


def test_pre_instrumentation_run_identified_plainly_not_as_zero(tmp_path):
    _write_work_completed(tmp_path, "iterate-2026-07-01-old", "2026-07-01T00:00:00+00:00")
    report = compute_report(tmp_path)
    assert "Pre-instrumentation run" in report
    assert "0.0 min" not in report and "0 min" not in report


def test_degraded_coverage_surfaced_not_hidden(tmp_path):
    run_id = "iterate-2026-08-04-degraded"
    it.record_start(tmp_path, run_id, name="review", parent=None,
                    ts="2026-08-04T10:00:00+00:00")
    it.record_end(tmp_path, run_id, name="review", parent=None,
                  ts="2026-08-04T10:05:00+00:00")
    valid, _ = itn.normalize_iterate_timings(itn.read_raw_events(tmp_path, run_id))
    _write_work_completed(tmp_path, run_id, "2026-08-04T10:05:01+00:00", iterate_timings=valid)

    report = compute_report(tmp_path)
    assert "DEGRADED" in report
    assert "1/5" in report  # coverage denominator = fold-time-capturable groups, not all 7


def test_bare_start_marks_for_every_capturable_group_read_as_degraded_not_complete(tmp_path):
    """External code review: presence alone is not coverage. A run with only
    `start` marks for all five fold-time-capturable groups (no matching end)
    must not report 5/5 non-degraded — it is the textbook partial run this
    report exists to surface."""
    run_id = "iterate-2026-08-04-bare-starts"
    for i, name in enumerate((
        "discovery_diagnosis", "planning", "implementation", "verification", "review",
    )):
        it.record_start(tmp_path, run_id, name=name, parent=None,
                        ts=f"2026-08-04T10:0{i}:00+00:00")
    valid, _ = itn.normalize_iterate_timings(itn.read_raw_events(tmp_path, run_id))
    _write_work_completed(tmp_path, run_id, "2026-08-04T10:10:00+00:00", iterate_timings=valid)

    report = compute_report(tmp_path)
    assert "DEGRADED" in report
    assert "0/5" in report
    assert "started, not closed" in report


def test_missing_agent_group_reads_unattributed_with_a_reason(tmp_path):
    """External code review: the card's own acceptance criterion is
    'unattributed WITH REASON, never silently omitted'. A fold-time-
    capturable group with no agent marks at all must say WHY it's missing,
    distinct from the two structurally-limited groups (finalization,
    delivery) whose absence at fold time is expected, not a missed mark."""
    run_id = "iterate-2026-08-04-missing-group"
    # Only 4 of the 5 fold-time-capturable groups marked; "review" is absent.
    for name in ("discovery_diagnosis", "planning", "implementation", "verification"):
        it.record_start(tmp_path, run_id, name=name, parent=None,
                        ts="2026-08-04T10:00:00+00:00")
        it.record_end(tmp_path, run_id, name=name, parent=None,
                      ts="2026-08-04T10:05:00+00:00")
    valid, _ = itn.normalize_iterate_timings(itn.read_raw_events(tmp_path, run_id))
    _write_work_completed(tmp_path, run_id, "2026-08-04T10:05:01+00:00", iterate_timings=valid)

    report = compute_report(tmp_path)
    assert "| review | *unattributed — no agent start/end marks recorded* |" in report
    assert "| finalization | *not reached before F5b fold (structural)* |" in report
    assert "| delivery | *not reached before F5b fold (structural)* |" in report


def test_derived_ancestor_labeled_distinctly_in_the_rendered_table(tmp_path):
    """iterate-2026-08-05-iterate-timings-derived-parent: the production
    shape where F0's producer spans name 'verification' as their parent but
    no agent mark ever recorded it. The report must show the reconstructed
    duration labeled *derived*, not the old *unattributed* absence row."""
    run_id = "iterate-2026-08-05-derived-shape"
    raw = [
        {"event": "span", "name": "pre_f0_validation", "parent": "verification", "attempt": 1,
         "source": "producer", "outcome": "completed",
         "start_utc": "2026-08-04T10:00:00+00:00", "end_utc": "2026-08-04T10:00:02+00:00",
         "duration_ms": 2000, "extra": {}},
        {"event": "span", "name": "canonical_f0_active", "parent": "verification", "attempt": 1,
         "source": "producer", "outcome": "completed",
         "start_utc": "2026-08-04T10:00:02+00:00", "end_utc": "2026-08-04T10:05:00+00:00",
         "duration_ms": 298000, "extra": {}},
    ]
    valid, rejected = itn.normalize_iterate_timings(raw)
    assert not rejected
    _write_work_completed(tmp_path, run_id, "2026-08-04T10:05:01+00:00", iterate_timings=valid)

    report = compute_report(tmp_path)
    assert "*(derived — reconstructed from child spans)*" in report
    assert "| verification | *unattributed" not in report
    assert "(+1 derived)" in report


def test_report_is_deterministic_given_the_same_events(tmp_path):
    run_id = "iterate-2026-08-04-deterministic"
    it.record_start(tmp_path, run_id, name="delivery", parent=None,
                    ts="2026-08-04T10:00:00+00:00")
    it.record_end(tmp_path, run_id, name="delivery", parent=None,
                  ts="2026-08-04T10:30:00+00:00")
    valid, _ = itn.normalize_iterate_timings(itn.read_raw_events(tmp_path, run_id))
    _write_work_completed(tmp_path, run_id, "2026-08-04T10:30:01+00:00", iterate_timings=valid)

    first = compute_report(tmp_path)
    second = compute_report(tmp_path)
    assert first == second


def test_write_report_creates_the_documented_path(tmp_path):
    _write_work_completed(tmp_path, "iterate-2026-08-04-write", "2026-08-04T10:00:00+00:00")
    path = write_report(tmp_path)
    assert path == tmp_path / ".shipwright" / "compliance" / "performance" / "iterate-throughput.md"
    assert path.exists()


def test_ci_retry_attribution_visible_in_nested_table(tmp_path):
    run_id = "iterate-2026-08-04-ci-retry"
    raw = [
        {"event": "span", "name": "delivery", "parent": None, "attempt": 1, "source": "agent",
         "outcome": "completed", "start_utc": "2026-08-04T10:00:00+00:00",
         "end_utc": "2026-08-04T11:00:00+00:00", "duration_ms": 3600000, "extra": {}},
        {"event": "span", "name": "delivery_wait", "parent": "delivery", "attempt": 1,
         "source": "producer", "outcome": "completed", "start_utc": "2026-08-04T10:00:00+00:00",
         "end_utc": "2026-08-04T11:00:00+00:00", "duration_ms": 3600000, "extra": {}},
        {"event": "span", "name": "ci_wait", "parent": "delivery_wait", "attempt": 1,
         "source": "producer", "outcome": "completed", "start_utc": "2026-08-04T10:00:00+00:00",
         "end_utc": "2026-08-04T10:15:00+00:00", "duration_ms": 900000, "extra": {}},
        {"event": "span", "name": "ci_wait", "parent": "delivery_wait", "attempt": 2,
         "source": "producer", "outcome": "completed", "start_utc": "2026-08-04T10:45:00+00:00",
         "end_utc": "2026-08-04T11:00:00+00:00", "duration_ms": 900000, "extra": {}},
    ]
    valid, rejected = itn.normalize_iterate_timings(raw)
    assert not rejected
    _write_work_completed(tmp_path, run_id, "2026-08-04T11:00:01+00:00", iterate_timings=valid)

    report = compute_report(tmp_path)
    assert report.count("| ci_wait |") == 2  # both attempts rendered distinctly


def test_rolling_stats_appear_with_enough_instrumented_runs(tmp_path):
    for i in range(3):
        run_id = f"iterate-2026-08-0{i + 1}-rolling"
        it.record_start(tmp_path, run_id, name="review", parent=None,
                        ts=f"2026-08-0{i + 1}T10:00:00+00:00")
        it.record_end(tmp_path, run_id, name="review", parent=None,
                      ts=f"2026-08-0{i + 1}T10:1{i}:00+00:00")
        valid, _ = itn.normalize_iterate_timings(itn.read_raw_events(tmp_path, run_id))
        _write_work_completed(tmp_path, run_id, f"2026-08-0{i + 1}T10:20:00+00:00",
                              iterate_timings=valid)
    report = compute_report(tmp_path)
    assert "Rolling comparison (last 3 instrumented runs)" in report
    assert "Fewer than 2 instrumented runs" not in report


def test_run_stat_helper_matches_events_used_by_report(tmp_path):
    """iterate_work_completed_events + run_stat is the same path compute_report
    uses internally — pin it directly so a future refactor cannot silently
    diverge the two."""
    _write_work_completed(tmp_path, "iterate-2026-08-04-a", "2026-08-04T10:00:00+00:00")
    from lib.config import read_events
    events = read_events(tmp_path)
    runs = iterate_work_completed_events(events)
    assert len(runs) == 1
    stat = run_stat(runs[0])
    assert stat["run_id"] == "iterate-2026-08-04-a"
    assert stat["pre_instrumentation"] is True


def test_extra_with_pipe_or_newline_is_rejected_at_validation(tmp_path):
    """External code review: a length cap alone still let a CLI-supplied
    --extra-json value hold up to 200 chars of arbitrary prose under an
    allowed key. extra values are now identifier-shaped-only, so prose
    (which almost always uses '|', quotes, or newlines) is rejected at the
    write boundary, not merely escaped later at render time."""
    raw = [
        {"event": "span", "name": "code_review", "parent": "review", "attempt": 1,
         "source": "agent", "outcome": "completed",
         "start_utc": "2026-08-04T10:00:00+00:00", "end_utc": "2026-08-04T10:01:00+00:00",
         "duration_ms": 60000, "extra": {"reviewer": "a | b\nc"}},
    ]
    valid, rejected = itn.normalize_iterate_timings(raw)
    assert not valid
    assert "identifier-shaped" in rejected[0]["reason"]


def test_extra_field_pipe_character_does_not_break_the_table(tmp_path):
    """Defense in depth: even if a '|' somehow reached the durable event (a
    pre-tightening record, a future validation bug), the render layer must
    still escape it rather than let it corrupt the markdown table structure.
    Bypasses normalize_iterate_timings deliberately — this tests the
    RENDERER's own escaping, independent of input validation."""
    run_id = "iterate-2026-08-04-escape"
    already_valid_spans = [
        {"name": "review", "parent": None, "source": "agent", "outcome": "completed",
         "start_utc": "2026-08-04T10:00:00+00:00", "end_utc": "2026-08-04T10:05:00+00:00",
         "duration_ms": 300000, "exclusive_ms": 240000, "attempt": 1, "extra": {}},
        {"name": "code_review", "parent": "review", "source": "agent", "outcome": "completed",
         "start_utc": "2026-08-04T10:00:00+00:00", "end_utc": "2026-08-04T10:01:00+00:00",
         "duration_ms": 60000, "exclusive_ms": 60000, "attempt": 1,
         "extra": {"reviewer": "a | b\nc"}},
    ]
    _write_work_completed(tmp_path, run_id, "2026-08-04T10:05:01+00:00",
                          iterate_timings=already_valid_spans)
    report = compute_report(tmp_path)
    assert "reviewer=a \\| b c" in report  # '|' escaped, newline collapsed to a space
    row_line = next(ln for ln in report.splitlines() if "reviewer=" in ln)
    assert row_line.count("|") == 7  # 6 table-cell delimiters (5 cols) + 1 escaped pipe


def test_report_renders_wall_clock_and_instrumented_ratio():
    event = {"type": "work_completed", "source": "iterate", "adr_id": "iterate-2026-08-04-wall",
             "ts": "2026-08-04T10:00:00+00:00",
             "phase_timings": [{"phase": "scope", "started": "2026-08-04T09:00:00+00:00"}],
             "iterate_timings": [
                 {"name": "planning", "parent": None, "source": "agent", "outcome": "completed",
                  "start_utc": "2026-08-04T09:30:00+00:00", "end_utc": "2026-08-04T10:00:00+00:00",
                  "duration_ms": 1_800_000, "exclusive_ms": 1_800_000, "attempt": 1, "extra": {}},
             ]}
    from lib.iterate_throughput_render import render_report
    report = render_report([run_stat(event)])
    assert "**Wall clock (scope through F5b):** 60.0 min (measured)" in report
    assert "**Instrumented:** 30.0 min of wall clock (50.0%)" in report

def test_report_labels_implausible_duration_as_excluded_evidence():
    event = {"type": "work_completed", "source": "iterate", "adr_id": "iterate-2026-08-04-outlier",
             "ts": "2026-08-04T10:00:00+00:00",
             "phase_timings": [{"phase": "scope", "started": "2026-08-04T09:00:00+00:00"}],
             "iterate_timings": [
                 {"name": "planning", "parent": None, "source": "agent", "outcome": "unavailable",
                  "start_utc": "2026-08-04T09:00:00+00:00", "end_utc": "2026-08-04T10:00:00+00:00",
                  "duration_ms": 3_600_000, "exclusive_ms": 3_600_000, "attempt": 1,
                  "extra": {"unavailable_reason": "implausible_duration"}},
             ]}
    from lib.iterate_throughput_render import render_report
    report = render_report([run_stat(event)])
    assert "*unavailable — implausible_duration* (60.0 min excluded from work)" in report

def test_report_labels_the_absent_alternative_entry_path_not_applicable():
    event = {"type": "work_completed", "source": "iterate", "adr_id": "planning-only",
             "ts": "2026-08-04T10:00:00+00:00", "iterate_timings": [
                 {"name": "planning", "parent": None, "source": "agent", "outcome": "completed",
                  "start_utc": "2026-08-04T09:00:00+00:00", "end_utc": "2026-08-04T10:00:00+00:00",
                  "duration_ms": 3_600_000, "exclusive_ms": 3_600_000, "attempt": 1, "extra": {}},
                 {"name": "implementation", "parent": None, "source": "agent", "outcome": "completed",
                  "start_utc": "2026-08-04T09:00:00+00:00", "end_utc": "2026-08-04T10:00:00+00:00",
                  "duration_ms": 3_600_000, "exclusive_ms": 3_600_000, "attempt": 1, "extra": {}},
                 {"name": "verification", "parent": None, "source": "agent", "outcome": "completed",
                  "start_utc": "2026-08-04T09:00:00+00:00", "end_utc": "2026-08-04T10:00:00+00:00",
                  "duration_ms": 3_600_000, "exclusive_ms": 3_600_000, "attempt": 1, "extra": {}},
                 {"name": "review", "parent": None, "source": "agent", "outcome": "completed",
                  "start_utc": "2026-08-04T09:00:00+00:00", "end_utc": "2026-08-04T10:00:00+00:00",
                  "duration_ms": 3_600_000, "exclusive_ms": 3_600_000, "attempt": 1, "extra": {}},
             ]}
    from lib.iterate_throughput_render import render_report
    report = render_report([run_stat(event)])
    assert "4/4 applicable fold-time groups" in report
    assert "*not applicable — planning is the recorded entry path*" in report
