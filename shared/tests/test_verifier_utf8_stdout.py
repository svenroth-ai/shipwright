"""Verifier CLIs must not crash on a Windows cp1252 console.

iterate-2026-06-13-verifier-utf8-stdout — ``format_report`` details can carry
non-ASCII (e.g. ``→`` from ``check_architecture_documented``). On Windows
``sys.stdout`` defaults to cp1252, so ``print(format_report(...))`` raised
``UnicodeEncodeError`` and masked the verifier's results. ``ensure_utf8_stdout``
(called at each CLI ``main()`` entry) pins stdout to UTF-8.
"""

from __future__ import annotations

import io
import sys

import pytest

from tools.verifiers.common import CheckResult, format_report
from tools.verifiers.stdio import ensure_utf8_stdout


def _cp1252_stdout(monkeypatch) -> io.BytesIO:
    """Repoint sys.stdout at a fresh cp1252-encoded stream; return its buffer."""
    raw = io.BytesIO()
    monkeypatch.setattr(sys, "stdout", io.TextIOWrapper(raw, encoding="cp1252"))
    return raw


def test_arrow_report_crashes_cp1252_stdout(monkeypatch):
    """Root cause: a report whose detail carries '→' cannot be written to a
    legacy-codepage console — the exact crash that masked the verifier."""
    _cp1252_stdout(monkeypatch)
    report = format_report(
        "t", [CheckResult("c", False, "convention -> use '→' in conventions.md")]
    )
    with pytest.raises(UnicodeEncodeError):
        sys.stdout.write(report)
        sys.stdout.flush()


def test_ensure_utf8_stdout_makes_report_printable_under_cp1252(monkeypatch):
    """Fix: pinning stdout to UTF-8 (before any write) lets the same
    '→'-bearing report print without crashing."""
    raw = _cp1252_stdout(monkeypatch)
    report = format_report("t", [CheckResult("c", False, "convention → conventions.md")])
    ensure_utf8_stdout()
    print(report)
    sys.stdout.flush()
    assert "→".encode("utf-8") in raw.getvalue()


def test_ensure_utf8_stdout_is_a_noop_when_already_utf8(capsys):
    """Safe / idempotent when stdout is already UTF-8 or lacks reconfigure —
    never raises, leaves a normal report printable."""
    ensure_utf8_stdout()
    print(format_report("t", [CheckResult("c", True, "ok")]))
    assert "SHIPWRIGHT VERIFIER: t" in capsys.readouterr().out


def test_main_prints_arrow_report_under_cp1252_without_crashing(monkeypatch):
    """End-to-end wiring guard: verify_iterate_finalization.main() must pin
    stdout BEFORE printing the report. Removing the ``ensure_utf8_stdout()``
    call in main() re-breaks this test."""
    import tools.verify_iterate_finalization as vif

    raw = _cp1252_stdout(monkeypatch)
    monkeypatch.setattr(
        vif, "run_all_checks",
        lambda *a, **k: [CheckResult("arch", False, "convention → conventions.md")],
    )
    monkeypatch.setattr(
        sys, "argv", ["verify", "--run-id", "iterate-x", "--project-root", "."]
    )
    with pytest.raises(SystemExit) as exc:  # one ERROR finding → exit 1
        vif.main()
    assert exc.value.code == 1
    sys.stdout.flush()
    assert "→".encode("utf-8") in raw.getvalue()
