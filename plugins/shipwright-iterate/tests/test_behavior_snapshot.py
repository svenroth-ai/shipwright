"""Unit tests for behavior_snapshot.py — the OS1 / P3.2 behavior-preserving gate.

Pure verdict/record tests on synthetic ``SuiteResult`` inputs + a
producer->file->consumer round-trip (Boundary Probe for the
``touches_io_boundary`` flag). The slow end-to-end CLI integration lives in
test_behavior_snapshot_cli.py.
"""

from __future__ import annotations

import sys
from pathlib import Path

LIB = Path(__file__).resolve().parent.parent / "scripts" / "lib"
sys.path.insert(0, str(LIB))

from behavior_snapshot import (  # noqa: E402
    SuiteResult,
    build_snapshot,
    compute_verdict,
    read_snapshot,
    snapshot_path,
    write_snapshot,
)


def _result(node_ids, *, passed, failed, exit_code, loc):
    return SuiteResult(
        node_ids=list(node_ids),
        passed=passed,
        failed=failed,
        total=passed + failed,
        exit_code=exit_code,
        loc=loc,
    )


def _green(node_ids=("t::a", "t::b"), *, loc=40):
    return _result(node_ids, passed=len(node_ids), failed=0, exit_code=0, loc=loc)


# --- build_snapshot ---------------------------------------------------------


def test_build_snapshot_marks_green_and_sorts_node_ids():
    snap = build_snapshot("iterate-2026-06-13-x", _green(("t::b", "t::a")), ["pytest"])
    assert snap["green"] is True
    assert snap["node_ids"] == ["t::a", "t::b"]
    assert snap["total"] == 2
    assert snap["node_ids_collected"] is True
    assert snap["schema_version"] >= 1


def test_build_snapshot_marks_red_baseline():
    snap = build_snapshot(
        "r", _result(("t::a",), passed=0, failed=1, exit_code=1, loc=10), ["pytest"]
    )
    assert snap["green"] is False


def test_build_snapshot_flags_empty_node_ids():
    snap = build_snapshot("r", _result((), passed=1, failed=0, exit_code=0, loc=5), ["x"])
    assert snap["node_ids_collected"] is False


# --- compute_verdict (the gate) ---------------------------------------------


def test_verdict_green_to_green_ok():
    snap = build_snapshot("r", _green(), ["pytest"])
    verdict = compute_verdict(snap, _green())
    assert verdict.ok is True
    assert verdict.reasons == []


def test_verdict_rejects_status_flip_via_exit_code():
    snap = build_snapshot("r", _green(), ["pytest"])
    current = _result(("t::a", "t::b"), passed=1, failed=1, exit_code=1, loc=38)
    verdict = compute_verdict(snap, current)
    assert verdict.ok is False
    assert any("status" in r.lower() or "fail" in r.lower() for r in verdict.reasons)


def test_verdict_rejects_removed_test_coverage():
    snap = build_snapshot("r", _green(("t::a", "t::b")), ["pytest"])
    # t::b deleted; remaining test still green
    current = _result(("t::a",), passed=1, failed=0, exit_code=0, loc=30)
    verdict = compute_verdict(snap, current)
    assert verdict.ok is False
    assert any("coverage" in r.lower() or "removed" in r.lower() for r in verdict.reasons)


def test_verdict_loc_drop_with_coverage_loss_rejected():
    snap = build_snapshot("r", _green(("t::a", "t::b"), loc=80), ["pytest"])
    current = _result(("t::a",), passed=1, failed=0, exit_code=0, loc=40)
    assert compute_verdict(snap, current).ok is False


def test_verdict_loc_drop_without_coverage_loss_ok():
    """The desirable simplify outcome: fewer source lines, same green coverage."""
    snap = build_snapshot("r", _green(("t::a", "t::b"), loc=80), ["pytest"])
    current = _green(("t::a", "t::b"), loc=40)  # same tests, fewer source LOC
    verdict = compute_verdict(snap, current)
    assert verdict.ok is True, verdict.reasons


def test_verdict_added_test_still_ok():
    """Adding coverage during a simplify is fine; only removal/flip is rejected."""
    snap = build_snapshot("r", _green(("t::a", "t::b")), ["pytest"])
    current = _green(("t::a", "t::b", "t::c"))
    assert compute_verdict(snap, current).ok is True


# --- round-trip (Boundary Probe) --------------------------------------------


def test_snapshot_roundtrip_reproduces_verdict(tmp_path):
    run_id = "iterate-2026-06-13-roundtrip"
    snap = build_snapshot(run_id, _green(("t::a", "t::b"), loc=80), ["pytest", "-q"])
    path = write_snapshot(tmp_path, run_id, snap)
    assert path == snapshot_path(tmp_path, run_id)
    assert path.is_file()

    reloaded = read_snapshot(tmp_path, run_id)
    assert reloaded == snap  # byte-faithful round-trip

    # The deserialized record drives the same verdict as the live record.
    current = _result(("t::a",), passed=1, failed=0, exit_code=0, loc=30)
    assert compute_verdict(reloaded, current).ok == compute_verdict(snap, current).ok is False
