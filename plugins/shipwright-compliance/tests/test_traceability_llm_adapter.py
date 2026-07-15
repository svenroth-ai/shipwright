"""Smoke tests for the stubbed record/replay LLM adapter (P1 AC3 + R4 controls).

Split out of test_traceability_fixtures.py to keep both modules <= 300 LOC.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

_FIX = Path(__file__).resolve().parent / "fixtures" / "traceability"


def _import_adapter():
    path = _FIX / "llm_adapter" / "record_replay.py"
    spec = importlib.util.spec_from_file_location("_traceability_record_replay", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_llm_adapter_replays_offline_and_refuses_bodies(tmp_path):
    rr = _import_adapter()
    adapter = rr.RecordReplayAdapter(_FIX / "llm_adapter" / "cassette.json")
    resp = adapter.adjudicate({
        "test_path": "unit/orders.test.ts",
        "test_title": "writes the order row",
        "candidate_frs": ["FR-03.02", "FR-03.03"],
    })
    assert resp["proposed_fr"] == "FR-03.03"
    assert resp["auto_write"] is False            # LLM-alone verdict is advisory (R4)
    # an unknown payload is a hard ReplayError, never a silent fabrication
    with pytest.raises(rr.ReplayError):
        adapter.adjudicate({"test_path": "x", "test_title": "y", "candidate_frs": []})
    # a payload carrying a test body is refused (R4 data control): both via a
    # disallowed key AND via an over-long value smuggled into an allowed field.
    with pytest.raises(ValueError):
        rr.RecordReplayAdapter.key_for({
            "test_path": "x", "test_title": "y", "candidate_frs": [], "body": "secret",
        })
    with pytest.raises(ValueError):
        rr.RecordReplayAdapter.key_for({
            "test_path": "x", "test_title": "B" * 5000, "candidate_frs": [],
        })
    # a body cannot hide in candidate_frs either (must be canonical FR ids)
    for bad in (["password=secret"], ["FR-1.3"], ["FR-01.03", "sk-live-abcdef"], "not-a-list",
                ["def test(): " + "z" * 500]):
        with pytest.raises(ValueError):
            rr.RecordReplayAdapter.key_for({"test_path": "x", "test_title": "y", "candidate_frs": bad})
    # an unsafe cassette that recorded auto_write=true cannot leak an authorization (R4)
    payload = {"test_path": "u/x.test.ts", "test_title": "t", "candidate_frs": ["FR-01.03"]}
    unsafe = tmp_path / "unsafe.json"
    unsafe.write_text(json.dumps({"schema_version": 2, "interactions": {
        rr.RecordReplayAdapter.key_for(payload): {"response": {"proposed_fr": "FR-01.03", "auto_write": True}},
    }}), encoding="utf-8")
    assert rr.RecordReplayAdapter(unsafe).adjudicate(payload)["auto_write"] is False
