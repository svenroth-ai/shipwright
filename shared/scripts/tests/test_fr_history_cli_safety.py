"""``fr_history.py``: what a hostile or awkward record can do to the output (S7).

Sibling of ``test_fr_history_cli.py`` (outcomes, exit codes, JSON). This module
is about text safety: the event log is fed partly by imported code-host
findings, so any field may carry escape sequences or newlines, and the console
it is read on may be a legacy codepage.

Two rules are asserted here, both learned the hard way:

* **Every rendered field is sanitised at the boundary**, not one field at render
  time. The first version covered ``summary`` alone — and only because its
  wrapper happened to ``split()``.
* **stdout is UTF-8 pinned; stderr is not**, so everything written to stderr
  passes through ``_ascii``. A non-ASCII id used to raise ``UnicodeEncodeError``
  from the message rejecting it.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests._fr_history_fixtures import project, work  # noqa: E402

_TOOL = Path(__file__).resolve().parents[1] / "tools" / "fr_history.py"

EXIT_OK = 0
EXIT_UNKNOWN_FR = 3
EXIT_LOG_UNREADABLE = 4


def _run(root: Path, *args) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(_TOOL), *args, "--project-root", str(root)],
        capture_output=True, text=True, encoding="utf-8",
    )


def test_terminal_control_sequences_in_a_summary_are_stripped(tmp_path):
    """A log record must not be able to repaint the terminal it is read in."""
    root = project(tmp_path, [
        work(affected_frs=["FR-01.01"], adr_id="run-a",
             summary="benign \x1b[2Jspoofed \x1b[31mred"),
    ])
    proc = _run(root, "FR-01.01")
    assert proc.returncode == EXIT_OK
    assert "\x1b" not in proc.stdout
    assert "benign" in proc.stdout


def test_a_newline_in_a_summary_cannot_fake_an_extra_entry(tmp_path):
    root = project(tmp_path, [
        work(affected_frs=["FR-01.01"], adr_id="run-a",
             summary="real\n  2. ~ 2026-01-01  forged-run-id"),
    ])
    proc = _run(root, "FR-01.01")
    assert "1 recorded change(s)" in proc.stdout
    assert "  2. ~" not in proc.stdout


def test_a_long_summary_is_wrapped_without_losing_words(tmp_path):
    words = " ".join(f"word{i}" for i in range(40))
    root = project(tmp_path, [
        work(affected_frs=["FR-01.01"], adr_id="run-a", summary=words),
    ])
    proc = _run(root, "FR-01.01")
    assert proc.returncode == EXIT_OK
    for i in (0, 20, 39):
        assert f"word{i}" in proc.stdout


def test_an_empty_history_does_not_claim_the_requirement_exists_when_unverified(tmp_path):
    """FIX 3: the positive-claim-over-an-empty-set shape, fourth instance.

    With no readable catalog, "This requirement exists" is an assertion nothing
    checked — and it directly contradicted the NOTE the same output prints a
    dozen lines later. Trigger: an id nobody has ever heard of, against a
    project dir holding only an event log.
    """
    (tmp_path / "shipwright_events.jsonl").write_text(
        json.dumps(work(affected_frs=["FR-01.01"], adr_id="run-a")) + "\n",
        encoding="utf-8",
    )
    proc = _run(tmp_path, "FR-99.99")
    assert proc.returncode == EXIT_OK
    assert "No recorded changes." in proc.stdout
    assert "This requirement exists" not in proc.stdout, (
        "the output asserts a made-up requirement exists, over a catalog it "
        "could not read"
    )
    assert "could NOT be checked" in proc.stdout
    assert "not checked for existence" in proc.stdout


def test_an_empty_history_does_claim_existence_when_it_was_verified(tmp_path):
    """CONTROL: the sentence is suppressed by the guard, not deleted."""
    root = project(tmp_path, [work(affected_frs=["FR-01.01"], adr_id="run-a")])
    proc = _run(root, "FR-01.02")
    assert proc.returncode == EXIT_OK
    assert "This requirement exists" in proc.stdout
    assert "could NOT be checked" not in proc.stdout


def test_control_sequences_in_the_run_id_are_stripped(tmp_path):
    """FIX 4: sanitising covered `summary` only; `label` rendered raw."""
    root = project(tmp_path, [
        work(affected_frs=["FR-01.01"], adr_id="run-a\x1b[2J\x1b[31mforged"),
    ])
    proc = _run(root, "FR-01.01")
    assert proc.returncode == EXIT_OK
    assert "\x1b" not in proc.stdout


def test_a_newline_in_the_run_id_cannot_fake_an_extra_entry(tmp_path):
    """The forgery `_wrap`'s docstring claimed to prevent, via the field beside it.

    ``strip_control_chars`` preserves newlines by design, so stripping alone was
    never enough — the boundary now folds whitespace.
    """
    root = project(tmp_path, [
        work(affected_frs=["FR-01.01"],
             adr_id="run-a\n  2. ~ 2026-01-01  forged-run-id"),
    ])
    proc = _run(root, "FR-01.01")
    assert "1 recorded change(s)" in proc.stdout
    assert "\n  2. ~" not in proc.stdout


@pytest.mark.parametrize("field,value", [
    ("commit", "abc123\x1b[31m"),
    ("spec_impact", "modify\x1b[2J"),
    ("ts", "2026-01-01T00:00:00+00:00\x1b[5m"),
])
def test_every_rendered_field_is_sanitised_not_just_the_summary(tmp_path, field, value):
    root = project(tmp_path, [
        work(affected_frs=["FR-01.01"], adr_id="run-a", **{field: value}),
    ])
    proc = _run(root, "FR-01.01")
    assert proc.returncode == EXIT_OK
    assert "\x1b" not in proc.stdout


def test_control_sequences_in_the_queried_id_do_not_reach_the_heading(tmp_path):
    root = project(tmp_path, [work(affected_frs=["FR-01.01"], adr_id="run-a")])
    proc = _run(root, "FR-01.01\x1b[2J")
    assert "\x1b" not in proc.stdout + proc.stderr


def test_an_unreadable_log_is_reported_as_a_failure_not_as_no_changes(tmp_path):
    """FIX 5: the swallow one layer above the fragment counting.

    An unreadable log rendered as "No recorded changes.", exit 0, no warning —
    a confident negative answer over a file nobody managed to open.
    """
    root = project(tmp_path, [work(affected_frs=["FR-01.01"], adr_id="run-a")])
    log = root / "shipwright_events.jsonl"
    log.unlink()
    log.mkdir()  # a directory where a file is expected -> OSError on read
    proc = _run(root, "FR-01.01")
    assert proc.returncode == EXIT_LOG_UNREADABLE
    assert "No recorded changes." not in proc.stdout
    assert "cannot answer" in proc.stderr


def test_a_non_ascii_id_does_not_crash_the_message_that_rejects_it(tmp_path):
    """stderr is not UTF-8 pinned, and the message interpolates the user's argv.

    `strip_control_chars` preserves >= 0xA0, so an id like `FR-01.01→` reached a
    cp1252 stderr and raised UnicodeEncodeError from the very message explaining
    the rejection. Escaped rather than dropped, so the id stays recognisable.
    """
    root = project(tmp_path, [work(affected_frs=["FR-01.01"], adr_id="run-a")])
    proc = _run(root, "FR-01.01→")
    assert proc.returncode == EXIT_UNKNOWN_FR
    assert "Traceback" not in proc.stderr
    assert proc.stderr.isascii(), (
        "stderr is not reconfigured to UTF-8, so every byte written there must "
        "be ASCII"
    )
    assert "FR-01.01" in proc.stderr


def test_an_unreadable_log_message_is_also_ascii_safe(tmp_path):
    """The same rule applies to the path interpolated into the exit-4 message."""
    root = project(tmp_path, [work(affected_frs=["FR-01.01"], adr_id="run-a")])
    log = root / "shipwright_events.jsonl"
    log.unlink()
    log.mkdir()
    proc = _run(root, "FR-01.01")
    assert proc.returncode == EXIT_LOG_UNREADABLE
    assert proc.stderr.isascii()
