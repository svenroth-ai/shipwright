"""WP8 / F25 — ``surface_verification`` F0.5-runner decode (UTF-8 + errors=replace).

Split out of ``test_utf8_config_readers.py`` (which keeps the F24 config-reader
tests) so neither module crosses the 300-LOC budget.

F25 (MED): ``surface_verification`` ran the F0.5 runner ``text=True`` with no
``encoding=`` → on cp1252 Windows the reader-thread decode raised on vitest's
``❯`` (U+276F → byte 0x9D) / em-dash → F0.5 false-failed though the suite passed.
Fixed by ``encoding="utf-8", errors="replace"``. These tests drive the real
``run_with_retries`` / ``verify_surface`` against a runner emitting ``❯`` / em-dash
on stdout AND stderr plus a raw 0x9D byte that ``errors="replace"`` must absorb.
"""

from __future__ import annotations

import sys
from pathlib import Path

# surface_verification lives in shared/scripts.
_SHARED_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))


# Fixture runner emitting the glyphs vitest/pytest produce: ``❯`` (U+276F) +
# em-dash on stdout AND stderr, plus a raw cp1252-undefined byte (0x9D) that
# ``errors="replace"`` must absorb (→ U+FFFD) without crashing the decode or
# corrupting the ASCII summary token (external plan review OpenAI #5, #8).
_RUNNER_SCRIPT = (
    "import sys\n"
    "sys.stdout.buffer.write('❯ vitest run — boundary suite\\n'.encode('utf-8'))\n"
    "sys.stdout.buffer.write(b'\\x9d raw undefined byte\\n')\n"
    "sys.stderr.buffer.write('stderr ❯ note\\n'.encode('utf-8'))\n"
    "sys.stdout.buffer.write('=== 5 passed in 0.30s ===\\n'.encode('utf-8'))\n"
    "sys.stdout.flush()\n"
    "sys.stderr.flush()\n"
)


def test_run_with_retries_decodes_unicode_runner_output(tmp_path):
    """run_with_retries decodes UTF-8 runner output (❯ / em-dash) without
    raising, parses tests_run, and absorbs the one malformed byte as U+FFFD."""
    from surface_verification import parse_tests_run, run_with_retries

    runner_py = tmp_path / "fixture_runner.py"
    runner_py.write_text(_RUNNER_SCRIPT, encoding="utf-8")

    exit_code, combined, attempts = run_with_retries(
        [sys.executable, str(runner_py)], tmp_path
    )

    assert exit_code == 0
    assert attempts == 1
    assert "❯" in combined and "—" in combined  # valid glyphs survive
    assert "�" in combined  # the one malformed byte → single U+FFFD, no crash
    assert parse_tests_run(combined, "web") == 5


def test_verify_surface_unicode_runner_clean_evidence(tmp_path):
    """verify_surface over a Unicode-emitting runner → clean pass (exit 0,
    tests_run=5) + a clean round-tripped evidence log."""
    from surface_verification import EXIT_OK, verify_surface

    runner_py = tmp_path / "fixture_runner.py"
    runner_py.write_text(_RUNNER_SCRIPT, encoding="utf-8")

    exit_code, block = verify_surface(
        project_root=tmp_path,
        run_id="iterate-2026-06-12-utf8-config-readers",
        surface="web",
        runner=[sys.executable, str(runner_py)],
        justification=None,
        tests_run_override=None,
    )

    assert exit_code == EXIT_OK
    assert block["tests_run"] == 5

    log_path = (
        tmp_path / ".shipwright" / "runs"
        / "iterate-2026-06-12-utf8-config-readers"
        / "surface_verification.log"
    )
    assert log_path.exists()
    # Evidence-log WRITE path round-trips the glyphs cleanly — fix is complete
    # end-to-end, not just at the decode (external plan review OpenAI #7).
    log_text = log_path.read_text(encoding="utf-8")
    assert "❯" in log_text and "—" in log_text
