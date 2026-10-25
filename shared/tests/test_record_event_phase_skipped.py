"""``phase_skipped`` is a first-class ``record_event`` type (gate-honesty follow-ups).

The orchestrator's ``recover-phase-task --force-status skipped --reason`` sends it, so a
skipped phase leaves a durable line in the tracked log. Like ``phase_failed`` it carries
phase + split + JSON detail and is NOT deduplicated: two skips of the same phase (the
task re-opened and skipped again) are two decisions, both kept.
New file because the existing ``test_record_event.py`` modules are baseline-capped.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_TOOLS = Path(__file__).resolve().parents[1] / "scripts" / "tools"
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

import record_event  # noqa: E402

pytestmark = pytest.mark.covers("FR-01.01/AC03")


def _skip(root: Path, reason: str, split: str | None = None) -> int:
    argv = ["--project-root", str(root), "--type", "phase_skipped", "--phase", "plan",
            "--detail", json.dumps({"phaseTaskId": "ptk-1", "reason": reason})]
    if split:
        argv += ["--split-id", split]
    return record_event.main(argv)


def test_phase_skipped_lands_with_phase_split_and_detail(tmp_path, capsys):
    assert _skip(tmp_path, "planned by hand", split="01-core") == 0
    assert json.loads(capsys.readouterr().out)["type"] == "phase_skipped"
    events = record_event.read_events(tmp_path)
    assert len(events) == 1
    assert (events[0]["phase"], events[0]["splitId"]) == ("plan", "01-core")
    assert json.loads(events[0]["detail"])["reason"] == "planned by hand"


def test_phase_skipped_is_not_deduplicated(tmp_path):
    assert _skip(tmp_path, "first") == 0
    assert _skip(tmp_path, "second") == 0
    reasons = [json.loads(e["detail"])["reason"] for e in record_event.read_events(tmp_path)]
    assert reasons == ["first", "second"]
