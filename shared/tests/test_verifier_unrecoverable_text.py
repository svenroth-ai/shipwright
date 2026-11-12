"""Finding text for a recorded event that cannot be repaired in this run."""

from __future__ import annotations

import json

import pytest

from tools.verifiers.plan_stub_check import check_plan_stub_recorded

_RUN = "iterate-2026-11-12-x"


@pytest.mark.covers("FR-01.11")
def test_missing_plan_path_text_says_the_warning_cannot_be_cleared(tmp_path):
    evt = {"type": "work_completed", "source": "iterate", "commit": "", "adr_id": _RUN, "intent": "change",
           "changed_files": ["shared/scripts/lib/x.py"]}
    (tmp_path / "shipwright_events.jsonl").write_text(json.dumps(evt) + "\n", encoding="utf-8")
    detail = check_plan_stub_recorded(tmp_path, _RUN, "").detail
    assert "cannot be cleared" in detail and "cannot be rewritten" in detail and "Next time" in detail


@pytest.mark.covers("FR-01.11")
def test_late_ac_record_text_says_the_warning_cannot_be_cleared():
    from pathlib import Path
    src = (Path(__file__).resolve().parents[1] / "scripts" / "lib" / "ac_record.py").read_text(encoding="utf-8")
    assert "committed after the first code commit" in src and "cannot be cleared" in src
