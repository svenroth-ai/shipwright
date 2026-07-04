"""Golden snapshot tests for the HTML report + terminal card (AC: stable snapshots).

Both renders come from the single :func:`support.canonical_model`, so the two
goldens can't drift on the fixture. Regenerate intentionally with
``UPDATE_GOLDEN=1`` after a deliberate template change; an accidental drift
fails the build.
"""

from __future__ import annotations

import os
from pathlib import Path

from html_report import render_html
from render_terminal import render_terminal
from support import canonical_model

_FIXTURES = Path(__file__).resolve().parent / "fixtures"
# Fixed footer stamp so the HTML golden is byte-stable.
_GEN = "2026-07-04 00:00 UTC"


def _assert_golden(name: str, actual: str) -> None:
    golden = _FIXTURES / name
    if os.environ.get("UPDATE_GOLDEN"):
        golden.parent.mkdir(parents=True, exist_ok=True)
        golden.write_text(actual, encoding="utf-8", newline="\n")
    expected = golden.read_text(encoding="utf-8")
    assert actual == expected, (
        f"snapshot drift in {name} — rerun with UPDATE_GOLDEN=1 if intended")


def test_html_snapshot_matches_golden():
    actual = render_html(canonical_model(), generated_at=_GEN)
    _assert_golden("g3_html_report.html", actual)


def test_terminal_snapshot_matches_golden():
    actual = render_terminal(canonical_model())
    _assert_golden("g3_terminal_card.txt", actual)
