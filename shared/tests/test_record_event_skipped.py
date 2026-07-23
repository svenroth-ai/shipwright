"""iterate-2026-07-23-tests-skipped-tracking — ``--tests-skipped`` on
work_completed events + the shared ``_validate_tests_block`` invariant.

Kept in a focused sibling module so the grandfathered ``test_record_event.py``
is not ratcheted past its bloat baseline. ``total`` counts selected tests
(passed + failed + skipped), so recording the skip count lets the compliance
readers separate host-gated skips from genuine failures.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_TOOLS = Path(__file__).resolve().parents[1] / "scripts" / "tools"
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

from record_event import build_event, main, parse_args, read_events  # noqa: E402


def _wc_args(**kwargs) -> list[str]:
    argv = ["--project-root", ".", "--type", "work_completed",
            "--source", "build", "--commit", "abc123"]
    for flag, key in (("--tests-passed", "tests_passed"),
                      ("--tests-total", "tests_total"),
                      ("--tests-skipped", "tests_skipped")):
        if key in kwargs:
            argv += [flag, str(kwargs[key])]
    if kwargs.get("e2e_run"):
        argv += ["--e2e-run", "true"]
    return argv


class TestTestsSkippedFlag:
    def test_skipped_written_into_tests_block(self):
        event = build_event(parse_args(_wc_args(tests_passed=828, tests_total=831, tests_skipped=3)))
        assert event["tests"] == {"passed": 828, "total": 831, "skipped": 3}

    def test_skipped_absent_when_flag_omitted(self):
        """No --tests-skipped → the key is absent (legacy shape, not skipped:0)."""
        event = build_event(parse_args(_wc_args(tests_passed=10, tests_total=10)))
        assert "skipped" not in event["tests"]

    def test_skipped_coexists_with_e2e_run(self):
        event = build_event(parse_args(_wc_args(tests_passed=5, tests_total=8,
                                                tests_skipped=3, e2e_run=True)))
        assert event["tests"] == {"passed": 5, "total": 8, "skipped": 3, "e2e_run": True}

    def test_passed_plus_skipped_exceeds_total_rejected(self):
        args = parse_args(_wc_args(tests_passed=9, tests_total=10, tests_skipped=3))
        with pytest.raises(ValueError, match=r"passed \(9\) \+ skipped \(3\) > total \(10\)"):
            build_event(args)

    def test_passed_plus_skipped_equal_total_ok(self):
        event = build_event(parse_args(_wc_args(tests_passed=7, tests_total=10, tests_skipped=3)))
        assert event["tests"]["skipped"] == 3

    def test_negative_skipped_rejected_at_parse(self):
        """_non_negative_int rejects a negative skip count at the CLI boundary."""
        with pytest.raises(SystemExit):
            parse_args(_wc_args(tests_passed=10, tests_total=10, tests_skipped=-1))

    def test_cli_round_trip_writes_and_reads_skipped(self, tmp_path):
        rc = main(["--project-root", str(tmp_path), "--type", "work_completed",
                   "--source", "build", "--commit", "c0ffee", "--section", "01-x",
                   "--tests-passed", "828", "--tests-total", "831", "--tests-skipped", "3"])
        assert rc == 0
        wc = [e for e in read_events(tmp_path) if e.get("type") == "work_completed"]
        assert len(wc) == 1 and wc[0]["tests"]["skipped"] == 3

    def test_main_rejects_corrupt_block_with_structured_error(self, tmp_path, capsys):
        """A cross-field violation surfaces as {"success": false, ...} + exit 1
        (like the FR gates), NOT a raw traceback — a JSON hook can parse it."""
        rc = main(["--project-root", str(tmp_path), "--type", "work_completed",
                   "--source", "build", "--commit", "x",
                   "--tests-passed", "9", "--tests-total", "10", "--tests-skipped", "3"])
        assert rc == 1
        out = json.loads(capsys.readouterr().out)
        assert out["success"] is False and out["error"] == "invalid_event"
        assert not (tmp_path / "shipwright_events.jsonl").exists()


class TestAmendmentTestsBlockValidation:
    """An event_amended correcting `tests` bypasses the --tests-* flag guards and
    folds onto the target via apply_amendments — so the same invariant is enforced
    on that write route, not just the flag path."""

    def _amend(self, fields: dict) -> list[str]:
        return ["--project-root", ".", "--type", "event_amended",
                "--amends", "evt-deadbeef", "--fields", json.dumps(fields)]

    def test_valid_tests_amendment_ok(self):
        event = build_event(parse_args(self._amend({"tests": {"passed": 8, "total": 10, "skipped": 2}})))
        assert event["fields"]["tests"] == {"passed": 8, "total": 10, "skipped": 2}

    def test_amendment_passed_plus_skipped_exceeds_total_rejected(self):
        args = parse_args(self._amend({"tests": {"passed": 9, "total": 10, "skipped": 3}}))
        with pytest.raises(ValueError, match=r"> total \(10\)"):
            build_event(args)

    def test_amendment_non_int_skipped_rejected(self):
        args = parse_args(self._amend({"tests": {"passed": 8, "total": 10, "skipped": "3"}}))
        with pytest.raises(ValueError, match="non-negative integer"):
            build_event(args)

    def test_amendment_negative_skipped_rejected(self):
        args = parse_args(self._amend({"tests": {"passed": 8, "total": 10, "skipped": -1}}))
        with pytest.raises(ValueError, match="non-negative integer"):
            build_event(args)

    def test_amendment_bool_skipped_rejected(self):
        args = parse_args(self._amend({"tests": {"passed": 8, "total": 10, "skipped": True}}))
        with pytest.raises(ValueError, match="non-negative integer"):
            build_event(args)

    def test_amendment_non_tests_fields_unvalidated(self):
        """A correction that does not touch `tests` is passed through untouched."""
        event = build_event(parse_args(self._amend({"spec_impact": "none"})))
        assert event["fields"] == {"spec_impact": "none"}
