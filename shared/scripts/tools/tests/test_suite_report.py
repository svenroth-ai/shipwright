"""F0 suite reporting - what the operator is told, on the console and on the card.

iterate-2026-07-27-f0-race-triage. `suite_report.py` is pure: it composes every
operator-facing string of an F0 run. Keeping the console block and the triage card in
ONE module is the mechanism behind the claim that the two cannot drift, so this file
tests them together.

Persistence, dedup and the fail-closed path live in `test_suite_race_triage.py`; the
CLI wiring in `test_suite_race_cli.py`.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from scripts.tools.run_test_suite import (  # noqa: E402
    PASS,
    RETRY_INFRA,
    RETRY_SERIAL,
    TEST_FAILURE,
    SuiteResult,
    UnitResult,
)
from scripts.tools.suite_race_triage import RaceFollowupReport  # noqa: E402
from scripts.tools.suite_report import (  # noqa: E402
    render_retry_block,
    render_run_report,
    reproduce_command,
    suite_command,
)

_XDIST = ("shared/tests",)


def _raced(unit_id="shared/tests", rc=1, serial_rc=0, output="", cmd="pytest tests"):
    return UnitResult(unit_id, PASS, rc, 1.0, output, race=True,
                      retry_kind=RETRY_SERIAL, serial_rc=serial_rc, retry_cmd=cmd)


def _suite(*results, exit_code=0, xdist=_XDIST):
    return SuiteResult(list(results), exit_code, 12.0, xdist)


def _report_with(recorded=None, failed=None):
    return RaceFollowupReport(recorded=recorded or {}, failed=failed or {})


# --- command composition (AC6/AC14) ---

def test_a_command_is_shell_quoted_and_carries_the_units_directory():
    cmd = reproduce_command("plugins/odd name", ["uv", "run", "pytest", "a b"])
    assert cmd.startswith("cd 'plugins/odd name' && ") and "'a b'" in cmd
    assert reproduce_command(".", ["uv", "run", "pytest"]) == "uv run pytest"


# --- AC7: the console block carries the handle (or an unmissable failure) ---

def test_the_console_names_the_durable_handle(tmp_path):
    race = _raced()
    result = _suite(race)
    report = _report_with({'shared/tests': 'trg-abc12345'})

    text = "\n".join(render_retry_block(result, [race], report))
    assert report.recorded["shared/tests"] in text
    assert "outlives the session" in text


def test_the_console_shouts_when_the_record_was_lost():
    race = _raced()
    report = _report_with(failed={"shared/tests": "append failed (OSError)"})
    text = "\n".join(render_retry_block(_suite(race), [race], report))
    assert "*** FAILED TO RECORD: append failed (OSError) ***" in text


def test_an_infra_retry_keeps_its_own_note_and_no_handle():
    infra = UnitResult("integration-tests", PASS, 2, 1.0, "", race=True,
                       retry_kind=RETRY_INFRA, serial_rc=0)
    text = "\n".join(render_retry_block(_suite(infra), [], _report_with()))
    assert "infrastructure fault (rc 2) that did NOT reproduce" in text
    assert "Tracked as" not in text


def test_no_retries_renders_nothing():
    clean = UnitResult("a", PASS, 0, 1.0)
    assert render_retry_block(_suite(clean), [], _report_with()) == []


def test_the_parallel_command_names_the_root_and_the_run(tmp_path):
    cmd = suite_command(tmp_path, "iterate-z")
    assert "run_test_suite.py" in cmd and str(tmp_path) in cmd
    assert cmd.endswith("--run-id iterate-z")
    assert "--run-id" not in suite_command(tmp_path), "the flag is optional"


def test_the_summary_table_tags_every_outcome_and_flags_a_retry():
    joined = "\n".join(render_run_report(
        _suite(_raced(), UnitResult("b", PASS, 0, 0.5))))
    assert "[passed on a retry - gate not stopped]" in joined
    assert "F0 suite: 2 units in" in joined and "-> GREEN" in joined


def test_a_failing_units_captured_output_IS_shown_on_the_console():
    """The mirror of the card rule: the console is where the evidence belongs, so a
    card that omits the output is not hiding it - it is putting it where it is safe."""
    red = UnitResult("x", TEST_FAILURE, 1, 1.0, "E   assert 1 == 2")
    joined = "\n".join(render_run_report(_suite(red, exit_code=1)))
    assert "E   assert 1 == 2" in joined and "-> RED" in joined


def test_truncation_marker_is_added_only_by_the_console_renderer():
    red = UnitResult("x", TEST_FAILURE, 1, 1.0, "terminal failure", truncated=True)
    joined = "\n".join(render_run_report(_suite(red, exit_code=1)))
    assert "FAULT: output tail truncated" in joined
    assert joined.index("FAULT: output tail truncated") < joined.index("terminal failure")


def test_failure_report_names_bounded_evidence_and_write_faults():
    red = UnitResult(
        "x", TEST_FAILURE, 1, 1.0, "failed",
        evidence_path=".shipwright/runs/r/initial.json",
        retry_evidence_path=".shipwright/runs/r/retry.json",
        evidence_error="PermissionError: locked",
    )
    joined = "\n".join(render_run_report(_suite(red, exit_code=1)))
    assert "bounded diagnostic evidence:" in joined
    assert "retry diagnostic evidence:" in joined
    assert "diagnostic evidence could not be retained" in joined
