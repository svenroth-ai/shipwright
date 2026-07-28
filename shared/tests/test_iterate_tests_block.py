"""Tests for the F5b ``tests`` block fold — AC-4 of iterate-2026-07-28-hygiene-sweep.

Group D's D1 counts a spec FR as covered only when a ``work_completed`` event
names it AND carries ``tests.total > 0`` (``group_d.py:139``). ``finalize_iterate``
— the only writer in the worktree flow — never wrote that key, so from the month
the worktree flow became the norm the log stopped carrying test evidence
(2026-07: 66 events with totals, 96 without). D1/D3 then reported the recorder's
silence as the project's gap; FR-01.17 and FR-01.18 are the visible edge of it.

These tests pin the derivation, the run_id staleness guard, the extras-override
precedence, and the fail-open posture.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(_SCRIPTS))

from lib import iterate_tests_block as itb  # noqa: E402

RUN = "iterate-2026-07-28-hygiene-sweep"


def _write_results(root: Path, payload: dict) -> Path:
    target = root / "shipwright_test_results.json"
    target.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return target


def _results(run_id: str = RUN, **layers) -> dict:
    latest = {"run_id": run_id, "date": "2026-07-28"}
    latest.update(layers)
    return {"iterate_latest": latest}


# ---------------------------------------------------------------------------
# derive_tests_block — the mapping (external review OpenAI #4: make it explicit)
# ---------------------------------------------------------------------------


class TestDerive:
    def test_unit_and_integration_totals_are_summed(self, tmp_path: Path):
        _write_results(tmp_path, _results(
            unit={"status": "passed", "passed": 6435, "total": 6454, "skipped": 19},
            integration={"status": "passed", "passed": 422, "total": 422, "skipped": 0},
        ))
        assert itb.derive_tests_block(tmp_path, RUN) == {
            "passed": 6857, "total": 6876, "skipped": 19, "e2e_run": False,
        }

    def test_not_run_layers_contribute_nothing(self, tmp_path: Path):
        """e2e/smoke/pgtap carry ``status: not_run`` + a reason and no counts."""
        _write_results(tmp_path, _results(
            unit={"status": "passed", "passed": 10, "total": 10, "skipped": 0},
            e2e={"status": "not_run", "reason": "no web surface in this diff"},
            smoke={"status": "not_run", "reason": "no server surface"},
            pgtap={"status": "not_run", "reason": "no database"},
        ))
        block = itb.derive_tests_block(tmp_path, RUN)
        assert block == {"passed": 10, "total": 10, "skipped": 0, "e2e_run": False}

    def test_e2e_run_is_true_when_e2e_actually_ran(self, tmp_path: Path):
        _write_results(tmp_path, _results(
            unit={"status": "passed", "passed": 10, "total": 10, "skipped": 0},
            e2e={"status": "passed", "passed": 4, "total": 4, "skipped": 0},
        ))
        block = itb.derive_tests_block(tmp_path, RUN)
        assert block["e2e_run"] is True
        assert block["total"] == 14

    def test_a_failing_run_reports_its_real_numbers(self, tmp_path: Path):
        """A red run must not be laundered into a green-looking block."""
        _write_results(tmp_path, _results(
            unit={"status": "failed", "passed": 98, "total": 100, "skipped": 0},
        ))
        block = itb.derive_tests_block(tmp_path, RUN)
        assert block == {"passed": 98, "total": 100, "skipped": 0, "e2e_run": False}

    def test_zero_total_yields_no_block(self, tmp_path: Path):
        """``total: 0`` is not evidence; emitting it would look like a claim."""
        _write_results(tmp_path, _results(
            unit={"status": "not_run", "reason": "nothing selected"},
        ))
        assert itb.derive_tests_block(tmp_path, RUN) is None

    def test_skipped_omitted_when_no_layer_reported_one(self, tmp_path: Path):
        """Absent ``skipped`` must stay absent — every reader keys on the
        ``isinstance(skipped, int)`` present/absent predicate (tests_block SSoT)."""
        _write_results(tmp_path, _results(
            unit={"status": "passed", "passed": 10, "total": 10},
        ))
        assert "skipped" not in itb.derive_tests_block(tmp_path, RUN)


# ---------------------------------------------------------------------------
# Staleness guard — trg-81fbf8ed / project_derived_snapshots_stale_ledger
# ---------------------------------------------------------------------------


class TestStalenessGuard:
    def test_a_foreign_run_id_is_treated_as_absent(self, tmp_path: Path):
        """shipwright_test_results.json is a DERIVED SNAPSHOT: a restore resets it
        to the previous run. Laundering those totals into this run's event is
        exactly the fail-open trg-81fbf8ed found in the F11 ledger check."""
        _write_results(tmp_path, _results(
            run_id="iterate-2026-07-27-some-other-run",
            unit={"status": "passed", "passed": 999, "total": 999, "skipped": 0},
        ))
        assert itb.derive_tests_block(tmp_path, RUN) is None

    def test_missing_run_id_is_treated_as_absent(self, tmp_path: Path):
        payload = {"iterate_latest": {
            "unit": {"status": "passed", "passed": 5, "total": 5, "skipped": 0}}}
        _write_results(tmp_path, payload)
        assert itb.derive_tests_block(tmp_path, RUN) is None


# ---------------------------------------------------------------------------
# Fail-open posture — finalize must never die on a results-file problem
# ---------------------------------------------------------------------------


class TestFailOpen:
    def test_absent_file_leaves_event_unchanged(self, tmp_path: Path):
        event = {"v": 1}
        assert itb.fold_into_event(event, tmp_path, RUN) == {"v": 1}

    def test_malformed_json_leaves_event_unchanged(self, tmp_path: Path):
        (tmp_path / "shipwright_test_results.json").write_text(
            "{not json", encoding="utf-8")
        event = {"v": 1}
        assert itb.fold_into_event(event, tmp_path, RUN) == {"v": 1}

    def test_non_dict_iterate_latest_leaves_event_unchanged(self, tmp_path: Path):
        _write_results(tmp_path, {"iterate_latest": "nope"})
        assert itb.fold_into_event({"v": 1}, tmp_path, RUN) == {"v": 1}

    def test_non_int_counts_are_ignored_not_crashed(self, tmp_path: Path):
        _write_results(tmp_path, _results(
            unit={"status": "passed", "passed": "many", "total": None},
        ))
        assert itb.fold_into_event({"v": 1}, tmp_path, RUN) == {"v": 1}

    def test_a_total_without_a_usable_passed_skips_that_layer(self, tmp_path: Path):
        """External code review (OpenAI): coercing a malformed ``passed`` to 0
        would record 'every test in this layer failed' from unreadable data.
        The layer is skipped; the remaining layers still count."""
        _write_results(tmp_path, _results(
            unit={"status": "passed", "passed": "many", "total": 100},
            integration={"status": "passed", "passed": 20, "total": 20, "skipped": 0},
        ))
        assert itb.derive_tests_block(tmp_path, RUN) == {
            "passed": 20, "total": 20, "skipped": 0, "e2e_run": False}

    def test_no_layer_survives_means_no_block(self, tmp_path: Path):
        _write_results(tmp_path, _results(
            unit={"status": "passed", "total": 100},  # passed absent entirely
        ))
        assert itb.fold_into_event({"v": 1}, tmp_path, RUN) == {"v": 1}

    def test_a_derived_block_failing_validation_is_dropped_not_raised(
        self, tmp_path: Path,
    ):
        """passed + skipped > total is a producer bug in F5's file. Diagnose and
        drop — finalize must not abort on it."""
        _write_results(tmp_path, _results(
            unit={"status": "passed", "passed": 10, "total": 10, "skipped": 5},
        ))
        assert itb.fold_into_event({"v": 1}, tmp_path, RUN) == {"v": 1}


# ---------------------------------------------------------------------------
# Precedence — external review OpenAI #5
# ---------------------------------------------------------------------------


class TestPrecedence:
    def test_explicit_extras_tests_wins_over_derivation(self, tmp_path: Path):
        _write_results(tmp_path, _results(
            unit={"status": "passed", "passed": 10, "total": 10, "skipped": 0},
        ))
        event = {"tests": {"passed": 3, "total": 3}}
        assert itb.fold_into_event(event, tmp_path, RUN)["tests"] == {
            "passed": 3, "total": 3}

    def test_an_invalid_explicit_block_raises_rather_than_being_written(
        self, tmp_path: Path,
    ):
        """Parity with record_event.py:219 — a corrupt tests block is refused at
        the write boundary, not silently appended to an append-only log."""
        with pytest.raises(ValueError):
            itb.fold_into_event(
                {"tests": {"passed": 9, "total": 5, "skipped": 3}}, tmp_path, RUN)

    def test_a_non_dict_explicit_block_raises(self, tmp_path: Path):
        with pytest.raises(ValueError):
            itb.fold_into_event({"tests": None}, tmp_path, RUN)


# ---------------------------------------------------------------------------
# Round-trip — touches_io_boundary probe
# ---------------------------------------------------------------------------


def test_round_trip_derived_block_satisfies_the_shared_validator(tmp_path: Path):
    """The block this producer writes must pass the SAME validator every
    consumer trusts (shared/scripts/tests_block.py)."""
    sys.path.insert(0, str(_SCRIPTS))
    from tests_block import validate_tests_block  # noqa: PLC0415

    _write_results(tmp_path, _results(
        unit={"status": "passed", "passed": 6435, "total": 6454, "skipped": 19},
        integration={"status": "passed", "passed": 422, "total": 422, "skipped": 0},
    ))
    block = itb.derive_tests_block(tmp_path, RUN)
    validate_tests_block(block)  # must not raise
    reloaded = json.loads(json.dumps(block))
    assert reloaded == block
    validate_tests_block(reloaded)


# ---------------------------------------------------------------------------
# The regression this AC exists to close
# ---------------------------------------------------------------------------


def test_d1_sees_a_folded_event_as_covering(tmp_path: Path):
    """End of the chain: an event folded by this module satisfies the exact
    predicate ``group_d._check_d1`` applies (``tests.total > 0``)."""
    _write_results(tmp_path, _results(
        unit={"status": "passed", "passed": 6435, "total": 6454, "skipped": 19},
    ))
    event = {"type": "work_completed", "affected_frs": ["FR-01.17"]}
    itb.fold_into_event(event, tmp_path, RUN)

    tests = event.get("tests")
    total = tests.get("total") if isinstance(tests, dict) else None
    assert isinstance(total, int) and total > 0


# The WIRING. External code review (OpenAI): every test above would still pass
# if the ``_fold_tests_block(...)`` call were deleted from finalize_iterate —
# module perfect, AC-4 broken in production. These drive the real F5b writer.
# Mutation-verified: removing the call fails the first test with KeyError.


class TestFinalizeIterateWiring:
    def _finalize(self, tmp_path: Path, extras: dict) -> dict:
        """Run the real ``finalize_iterate._record_event`` and return its event."""
        sys.path.insert(0, str(_SCRIPTS))
        from tools import finalize_iterate  # noqa: PLC0415

        (tmp_path / "shipwright_events.jsonl").touch()
        finalize_iterate._record_event(
            tmp_path, "", RUN, "iterate: wiring probe", event_extras=extras)
        lines = [ln for ln in (tmp_path / "shipwright_events.jsonl")
                 .read_text(encoding="utf-8").splitlines() if ln.strip()]
        assert lines, "no event was appended"
        return json.loads(lines[-1])

    def test_finalize_writes_the_derived_totals_onto_the_event(self, tmp_path: Path):
        _write_results(tmp_path, _results(
            unit={"status": "passed", "passed": 6435, "total": 6454, "skipped": 19},
            integration={"status": "passed", "passed": 422, "total": 422,
                         "skipped": 0},
        ))
        event = self._finalize(
            tmp_path, {"spec_impact": "none", "change_type": "tooling",
                       "none_reason": "wiring probe"})
        assert event["tests"] == {
            "passed": 6857, "total": 6876, "skipped": 19, "e2e_run": False}

    def test_finalize_keeps_an_explicit_extras_block(self, tmp_path: Path):
        _write_results(tmp_path, _results(
            unit={"status": "passed", "passed": 10, "total": 10, "skipped": 0},
        ))
        event = self._finalize(
            tmp_path, {"spec_impact": "none", "change_type": "tooling",
                       "none_reason": "wiring probe",
                       "tests": {"passed": 3, "total": 3}})
        assert event["tests"] == {"passed": 3, "total": 3}

    def test_finalize_writes_no_tests_key_without_a_matching_ledger(
        self, tmp_path: Path,
    ):
        """A stale snapshot from another run must not become this run's evidence."""
        _write_results(tmp_path, _results(
            run_id="iterate-2026-07-27-somebody-else",
            unit={"status": "passed", "passed": 999, "total": 999, "skipped": 0},
        ))
        event = self._finalize(
            tmp_path, {"spec_impact": "none", "change_type": "tooling",
                       "none_reason": "wiring probe"})
        assert "tests" not in event
