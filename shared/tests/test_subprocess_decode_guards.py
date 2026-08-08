"""Captured command output with a non-UTF-8 byte must not crash its reader."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_RUN = subprocess.run
import pytest

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(_SCRIPTS))

from lib import pr_blockers  # noqa: E402
from tools import watch_pr_delivery  # noqa: E402


def _non_utf8_child(*_args, **kwargs):
    return _RUN(
        [sys.executable, "-c", "import sys; sys.stdout.buffer.write(b'\\x81')"],
        **kwargs,
    )


def test_pr_blocker_reader_degrades_on_a_non_utf8_child_byte(monkeypatch):
    monkeypatch.setattr(pr_blockers.subprocess, "run", _non_utf8_child)
    assert pr_blockers._gh_json(["gh"]) is None


def test_delivery_reader_reports_unreadable_json_not_a_decode_crash(monkeypatch):
    monkeypatch.setattr(watch_pr_delivery.subprocess, "run", _non_utf8_child)
    with pytest.raises(RuntimeError, match="unreadable JSON"):
        watch_pr_delivery._gh_pr_json("1", None)


def test_plan_marker_test_runner_uses_replace_for_captured_output():
    source = (
        Path(__file__).resolve().with_name("test_mark_review_state.py")
        .read_text(encoding="utf-8")
    )
    assert 'encoding="utf-8", errors="replace"' in source
