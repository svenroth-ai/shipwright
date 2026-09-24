"""``write_terminal_marker.py`` must not write its shared-sentinel path under
a campaign-dag-scheduler R5a wave (campaign-mode.md step 3d + code review
round 3, MEDIUM #4): every unit in a wave shares the identical
``SHIPWRIGHT_LOOP_UNIT_ID`` sentinel value, and nothing polls for the DONE
file for ``kind == "sub_iterate"`` any more, so writing it is both dead
output and a needless concurrent-write race across sibling runners.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_HOOK_PATH = (
    Path(__file__).resolve().parents[1] / "scripts" / "hooks" / "write_terminal_marker.py"
)
_spec = importlib.util.spec_from_file_location("write_terminal_marker", _HOOK_PATH)
write_terminal_marker = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(write_terminal_marker)


def test_noops_under_the_wave_sentinel(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SHIPWRIGHT_LOOP_ID", "loop-1")
    monkeypatch.setenv("SHIPWRIGHT_LOOP_UNIT_ID", "__campaign_wave__")
    monkeypatch.setattr(sys, "stdin", __import__("io").StringIO("{}"))

    assert write_terminal_marker.main() == 0
    assert not (tmp_path / ".shipwright" / "runs").exists()


def test_noops_under_a_padded_sentinel(tmp_path, monkeypatch):
    """A CLAUDE_ENV_FILE round-trip can pad the exported value with
    whitespace (code review round 3's own motivating hazard) — the gate
    must still recognise it (round 4, MEDIUM: zero coverage until now)."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SHIPWRIGHT_LOOP_ID", "loop-1")
    monkeypatch.setenv("SHIPWRIGHT_LOOP_UNIT_ID", "  __campaign_wave__\n")
    monkeypatch.setattr(sys, "stdin", __import__("io").StringIO("{}"))

    assert write_terminal_marker.main() == 0
    assert not (tmp_path / ".shipwright" / "runs").exists()


def test_still_writes_for_a_genuine_per_unit_id(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SHIPWRIGHT_LOOP_ID", "loop-1")
    monkeypatch.setenv("SHIPWRIGHT_LOOP_UNIT_ID", "section-3")
    monkeypatch.setattr(sys, "stdin", __import__("io").StringIO("{}"))

    assert write_terminal_marker.main() == 0
    marker = tmp_path / ".shipwright" / "runs" / "loop-1" / "section-3" / "DONE"
    assert marker.exists()
