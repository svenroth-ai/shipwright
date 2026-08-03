"""Unit tests for behavior_snapshot.py — the OS1 / P3.2 behavior-preserving gate.

Pure verdict/record tests on synthetic ``SuiteResult`` inputs + a
producer->file->consumer round-trip (Boundary Probe for the
``touches_io_boundary`` flag). The slow end-to-end CLI integration lives in
integration-tests/test_behavior_snapshot_gate.py.
"""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))  # shared/

from scripts.tools.behavior_snapshot import (  # noqa: E402
    SuiteResult,
    build_snapshot,
    collect_test_ids,
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


# --- collect_test_ids: verbosity independence -------------------------------
#
# pytest SUMS -v/-q, and `--collect-only` prints `path::name` node-ids ONLY at
# effective verbosity exactly -1 (>=0 prints the indented tree, <=-2 prints
# per-file counts). A bare `-q` is therefore a RELATIVE nudge whose landing
# point depends on the target project's configured `addopts`: under this
# monorepo's `addopts = "-v ..."` it lands on 0 and yields zero parseable ids,
# which silently made compute_verdict's removed-coverage and count-drop arms
# inert for every SIMPLIFY run. `--verbosity=-1` is ABSOLUTE and pins the one
# level that emits node-ids regardless of configuration.
#
# These spawn a real pytest subprocess (~1s each) and are deliberately left
# UNMARKED rather than `slow`: the root `-m 'not slow'` default would deselect
# them in CI, re-opening the exact silent hole they exist to close. The
# function under test runs in-process, so diff-coverage still sees it.

_MINI_TESTS = """
    import pytest

    def test_alpha():
        assert True

    def test_beta():
        assert True

    @pytest.mark.slow
    def test_gamma_slow():
        assert True
"""


def _mini_project(root: Path, addopts: str) -> Path:
    """A throwaway pytest project with its own rootdir and configured addopts."""
    proj = root / "mini"
    (proj / "tests").mkdir(parents=True)
    (proj / "pyproject.toml").write_text(
        '[project]\nname = "mini"\nversion = "0.1.0"\n\n'
        "[tool.pytest.ini_options]\n"
        f'addopts = "{addopts}"\n'
        'markers = ["slow: excluded from the default run"]\n',
        encoding="utf-8",
    )
    (proj / "tests" / "test_mini.py").write_text(
        textwrap.dedent(_MINI_TESTS).strip() + "\n", encoding="utf-8"
    )
    return proj


@pytest.mark.parametrize(
    "addopts",
    [
        "--tb=short",           # verbosity 0 — the only config the old code handled
        "-v --tb=short",        # +1 — this monorepo; the old code returned []
        "-v -v -v --tb=short",  # +3 — defeats any fixed number of extra -q flags
        "-q --tb=short",        # -1 — already quiet; an extra -q overshoots to -2
    ],
)
def test_collect_test_ids_independent_of_configured_verbosity(tmp_path, addopts):
    """Node-ids must be collected whatever verbosity the project configures."""
    proj = _mini_project(tmp_path, addopts)

    ids = collect_test_ids(proj, [sys.executable, "-m", "pytest"], [])

    assert len(ids) == 3, f"addopts={addopts!r} yielded {ids!r}"
    assert all("::" in i for i in ids), ids
    assert any(i.endswith("::test_alpha") for i in ids), ids


def test_collect_test_ids_preserves_configured_marker_filter(tmp_path):
    """The fix must not clobber addopts — a deselecting `-m` must still apply.

    Guards the rejected alternative (`-o addopts=`), which restored node-ids by
    discarding the project's own filters and so collected tests the suite never
    runs — inflating the baseline the count-drop arm compares against.
    """
    proj = _mini_project(tmp_path, "-v --tb=short -m 'not slow'")

    ids = collect_test_ids(proj, [sys.executable, "-m", "pytest"], [])

    assert len(ids) == 2, ids
    assert not any("test_gamma_slow" in i for i in ids), ids


def test_collect_test_ids_returns_empty_for_non_pytest_runner(tmp_path):
    """A non-pytest runner still yields no ids (snapshot then reports INERT)."""
    proj = _mini_project(tmp_path, "--tb=short")

    ids = collect_test_ids(proj, [sys.executable, "-c", "print('no tests here')"], [])

    assert ids == []
