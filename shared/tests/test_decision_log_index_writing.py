"""Writing ``decision_log_index.md`` — atomicity, locking, LF-exactness.

Mirrors ``test_adr_index_writing.py``. The renderer's own rules live in
``test_decision_log_index.py``; the call sites live in
``test_decision_log_index_producers.py``.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from lib import atomic_write
from lib.decision_log_index import (
    DECISION_LOG_INDEX_FILENAME,
    DECISION_LOG_PATH,
    REGEN_COMMAND,
    REGEN_TOOL_RELPATH,
    rebuild_decision_log_index,
    regen_command_resolved,
    render_decision_log_index,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _log(root: Path, text: str) -> Path:
    path = root / DECISION_LOG_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _regen_script() -> Path:
    return _REPO_ROOT / "shared" / REGEN_TOOL_RELPATH


def test_missing_decision_log_is_a_strict_noop(tmp_path):
    assert rebuild_decision_log_index(tmp_path) is None
    assert not (tmp_path / DECISION_LOG_PATH).exists()


def test_rebuild_writes_the_render_beside_the_log(tmp_path):
    _log(tmp_path, "### ADR-001: X\n")
    path = rebuild_decision_log_index(tmp_path)
    assert path is not None
    assert path.name == DECISION_LOG_INDEX_FILENAME
    assert path.parent == (tmp_path / DECISION_LOG_PATH).parent
    log_text = (tmp_path / DECISION_LOG_PATH).read_text(encoding="utf-8")
    assert path.read_text(encoding="utf-8") == render_decision_log_index(log_text)


def test_failed_write_leaves_the_previous_index_intact(tmp_path, monkeypatch):
    _log(tmp_path, "### ADR-001: X\n")
    good = rebuild_decision_log_index(tmp_path).read_text(encoding="utf-8")
    _log(tmp_path, "### ADR-001: X\n\n### ADR-002: Y\n")

    def boom(*a, **k):
        raise OSError("disk full")

    monkeypatch.setattr(atomic_write.os, "replace", boom)
    with pytest.raises(OSError):
        rebuild_decision_log_index(tmp_path)
    index = (tmp_path / DECISION_LOG_PATH).parent / DECISION_LOG_INDEX_FILENAME
    assert index.read_text(encoding="utf-8") == good


def test_render_is_written_verbatim_lf_even_on_windows(tmp_path):
    _log(tmp_path, "### ADR-001: X\n")
    raw = rebuild_decision_log_index(tmp_path).read_bytes()
    assert b"\r\n" not in raw


def test_regen_command_names_a_script_that_exists():
    assert "aggregate_decisions" not in REGEN_COMMAND
    assert _regen_script().is_file(), f"{REGEN_COMMAND} names a script that is missing"


def test_regen_command_is_layout_independent():
    assert "{shared_root}" in REGEN_COMMAND
    resolved = regen_command_resolved()
    assert "{shared_root}" not in resolved
    assert Path(resolved.split("uv run ", 1)[1].split(" ", 1)[0]).is_file()


def test_cli_regenerates_the_index(tmp_path):
    _log(tmp_path, "### ADR-090: X\n")
    proc = subprocess.run(
        [sys.executable, str(_regen_script()), "--project-root", str(tmp_path)],
        capture_output=True, text=True, encoding="utf-8",
    )
    assert proc.returncode == 0, proc.stderr
    index = (tmp_path / DECISION_LOG_PATH).parent / DECISION_LOG_INDEX_FILENAME
    assert "- [ADR-090 — X]" in index.read_text(encoding="utf-8")


def test_cli_on_a_repo_without_a_decision_log_creates_nothing(tmp_path):
    proc = subprocess.run(
        [sys.executable, str(_regen_script()), "--project-root", str(tmp_path)],
        capture_output=True, text=True, encoding="utf-8",
    )
    assert proc.returncode == 0, proc.stderr
    assert not (tmp_path / DECISION_LOG_PATH).exists()
