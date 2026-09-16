"""Dedup-by-request-id and phase attribution — split out of
test_context_cost_core.py (300-line size guideline, req3-05 t9).

@covers FR-01.20/AC01, AC02, AC03 — one exchange counted exactly once
regardless of how many transcript lines share its request id; an exchange
counted while a phase was active carries that phase's label; an exchange
with no active phase is still recorded, labelled ``unphased``, never
dropped.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(_SCRIPTS))

from lib import context_cost_core as ccc  # noqa: E402
from lib import iterate_phase_groups as ipg  # noqa: E402

RUN_ID = "iterate-2026-08-07-context-cost-meter"
_T0 = datetime(2026, 8, 7, 12, 0, 0, tzinfo=timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _assistant_record(request_id: str, ts: datetime, model: str, usage: dict) -> dict:
    return {
        "type": "assistant",
        "requestId": request_id,
        "timestamp": _iso(ts),
        "message": {"model": model, "usage": usage},
    }


def _write_transcript(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in records) + "\n",
        encoding="utf-8",
    )


@pytest.mark.covers("FR-01.20/AC01")
def test_multi_record_single_response_dedups_to_one_call(tmp_path):
    """FR-01.20/AC01 — "every exchange with the model is counted exactly
    once — never once per transcript line — because a single exchange is
    written as several lines that all share one request id.\""""
    usage = {"input_tokens": 100, "output_tokens": 50}
    transcript = tmp_path / "session.jsonl"
    _write_transcript(
        transcript,
        [
            _assistant_record("req-1", _T0, "claude-sonnet-5", usage),
            _assistant_record("req-1", _T0, "claude-sonnet-5", usage),
        ],
    )
    summary = ccc.compute_summary(transcript, tmp_path, run_id=None)
    assert summary["calls"] == 1


@pytest.mark.covers("FR-01.20/AC03")
def test_call_before_first_mark_is_unphased(tmp_path):
    """FR-01.20/AC03 — no active phase yet: still recorded, labelled
    unphased, never dropped."""
    ipg.append_mark(tmp_path, RUN_ID, "scope", ts=_iso(_T0 + timedelta(minutes=10)))
    transcript = tmp_path / "session.jsonl"
    _write_transcript(
        transcript,
        [_assistant_record("req-1", _T0, "claude-sonnet-5", {"input_tokens": 10})],
    )
    summary = ccc.compute_summary(transcript, tmp_path, run_id=RUN_ID)
    assert summary["by_phase"].keys() == {"unphased"}


@pytest.mark.covers("FR-01.20/AC02")
def test_call_after_a_mark_gets_that_phase(tmp_path):
    """FR-01.20/AC02 — an exchange counted while a phase was active carries
    that phase's label."""
    ipg.append_mark(tmp_path, RUN_ID, "scope", ts=_iso(_T0))
    ipg.append_mark(tmp_path, RUN_ID, "build", ts=_iso(_T0 + timedelta(minutes=5)))
    transcript = tmp_path / "session.jsonl"
    _write_transcript(
        transcript,
        [
            _assistant_record(
                "req-1", _T0 + timedelta(minutes=6), "claude-sonnet-5", {"input_tokens": 10}
            )
        ],
    )
    summary = ccc.compute_summary(transcript, tmp_path, run_id=RUN_ID)
    assert set(summary["by_phase"].keys()) == {"build"}


@pytest.mark.covers("FR-01.20/AC03")
def test_no_run_id_means_every_call_is_unphased(tmp_path):
    """FR-01.20/AC03 — "no phase is active — no pipeline is running, or the
    session is outside one" is the other half of this AC's precondition;
    still recorded, labelled, never dropped."""
    ipg.append_mark(tmp_path, RUN_ID, "build", ts=_iso(_T0))
    transcript = tmp_path / "session.jsonl"
    _write_transcript(
        transcript,
        [
            _assistant_record(
                "req-1", _T0 + timedelta(minutes=1), "claude-sonnet-5", {"input_tokens": 10}
            )
        ],
    )
    summary = ccc.compute_summary(transcript, tmp_path, run_id=None)
    assert set(summary["by_phase"].keys()) == {"unphased"}
