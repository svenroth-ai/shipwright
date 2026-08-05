"""F0 console-reporting encoding safety — split from `test_run_test_suite.py`.

`_finish_locked` prints a unit's raw captured pytest output, which is arbitrary
third-party text the runner's own ASCII-only prose discipline
(`test_operator_facing_strings_are_ascii_only` in `test_suite_units.py`) never
reaches. On a Windows cp1252 console, a character that codepage can't encode used
to raise UnicodeEncodeError AFTER the suite had already decided pass/fail,
truncating the report at the one moment — a red unit — the console is the
operator's primary read. `print_console` (`suite_console.py`) guards it.
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

import scripts.tools.run_test_suite as mod
from scripts.tools.suite_units import TEST_FAILURE


def test_console_report_survives_non_cp1252_captured_output(tmp_path, monkeypatch):
    """Observed twice finalizing iterate-2026-08-05-iterate-timings-derived-parent."""
    result = mod.SuiteResult(
        results=[mod.UnitResult("shared/tests", TEST_FAILURE, 1, 1.0,
                                output="boom � tail")],
        exit_code=1, seconds=1.0,
    )
    monkeypatch.setattr(mod, "run_gate", lambda *a, **k: mod.GateResult(
        mod.GATE_PASSED, ["gate note �"]))
    console = io.TextIOWrapper(io.BytesIO(), encoding="cp1252", errors="strict")
    monkeypatch.setattr(sys, "stdout", console)

    rc = mod._finish_locked(tmp_path, "cp1252-repro", result, None, None)

    console.flush()
    printed = console.buffer.getvalue().decode("cp1252")
    assert rc == 1
    assert "boom ? tail" in printed
    assert "gate note ?" in printed
