"""Tests for the shared context-cost computation core.

One function computes dedup + phase attribution + pricing from a transcript;
the Stop hook, the summary/statusline readers, and the F5b finalize fold all
call it — never three reimplementations (context-cost-meter, post two rounds
of external review that rejected a standing incremental-cache design in
favor of a full recompute on every call).
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


def test_multi_record_single_response_dedups_to_one_call(tmp_path):
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


def test_call_before_first_mark_is_unphased(tmp_path):
    ipg.append_mark(tmp_path, RUN_ID, "scope", ts=_iso(_T0 + timedelta(minutes=10)))
    transcript = tmp_path / "session.jsonl"
    _write_transcript(
        transcript,
        [_assistant_record("req-1", _T0, "claude-sonnet-5", {"input_tokens": 10})],
    )
    summary = ccc.compute_summary(transcript, tmp_path, run_id=RUN_ID)
    assert summary["by_phase"].keys() == {"unphased"}


def test_call_after_a_mark_gets_that_phase(tmp_path):
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


def test_no_run_id_means_every_call_is_unphased(tmp_path):
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


@pytest.mark.parametrize(
    "bad_record",
    [
        {"type": "assistant", "timestamp": _iso(_T0), "message": {"model": "x", "usage": {}}},
        {"type": "assistant", "requestId": "r", "timestamp": _iso(_T0), "message": {"usage": {}}},
        {"type": "assistant", "requestId": "r", "timestamp": _iso(_T0), "message": {"model": "x"}},
        {"type": "assistant", "requestId": ["not", "hashable"], "timestamp": _iso(_T0),
         "message": {"model": "x", "usage": {}}},
        {"type": "assistant", "requestId": "r", "timestamp": _iso(_T0),
         "message": {"model": ["not", "hashable"], "usage": {}}},
    ],
    ids=["missing-requestId", "missing-model", "missing-usage",
         "unhashable-requestId", "unhashable-model"],
)
def test_malformed_record_is_skipped_and_counted_not_fabricated(tmp_path, bad_record):
    transcript = tmp_path / "session.jsonl"
    _write_transcript(transcript, [bad_record])
    summary = ccc.compute_summary(transcript, tmp_path, run_id=None)
    assert summary["calls"] == 0
    assert summary["skipped_malformed"] == 1


def test_non_numeric_token_field_does_not_abort_other_calls_in_the_transcript(tmp_path):
    # External-review finding: a string input_tokens value used to raise a
    # TypeError out of the ENTIRE compute_summary loop, silently losing
    # every other call in the same transcript -- not just the malformed
    # record's own accounting.
    transcript = tmp_path / "session.jsonl"
    _write_transcript(
        transcript,
        [
            _assistant_record(
                "req-1", _T0, "claude-sonnet-5", {"input_tokens": "not-a-number"},
            ),
            _assistant_record(
                "req-2", _T0 + timedelta(seconds=1), "claude-sonnet-5", {"input_tokens": 1_000_000}
            ),
        ],
    )
    summary = ccc.compute_summary(transcript, tmp_path, run_id=None)
    assert summary["calls"] == 2  # both counted -- neither record aborted the loop
    assert summary["cost_usd"] == 3.00  # req-1's malformed field priced as 0, not fabricated


def test_aggregate_cost_is_priced_subtotal_with_completeness_flag(tmp_path):
    transcript = tmp_path / "session.jsonl"
    _write_transcript(
        transcript,
        [
            _assistant_record("req-1", _T0, "claude-sonnet-5", {"input_tokens": 1_000_000}),
            _assistant_record(
                "req-2", _T0 + timedelta(seconds=1), "claude-unknown-model", {"input_tokens": 1}
            ),
        ],
    )
    summary = ccc.compute_summary(transcript, tmp_path, run_id=None)
    assert summary["calls"] == 2
    assert summary["cost_usd"] == 3.00  # only the priced call counted
    assert summary["unpriced_calls"] == 1
    assert summary["cost_complete"] is False


def test_unpriced_calls_record_their_distinct_model_ids(tmp_path):
    # A bare count told an operator SOMETHING was unpriced but not WHICH
    # model needs a pricing-table entry -- external-review finding on this
    # same iterate. Two unpriced calls from the same unrecognized model
    # must not double up the list; a mix of unpriced models both appear.
    transcript = tmp_path / "session.jsonl"
    _write_transcript(
        transcript,
        [
            _assistant_record("req-1", _T0, "claude-sonnet-5", {"input_tokens": 10}),
            _assistant_record(
                "req-2", _T0 + timedelta(seconds=1), "claude-unknown-a", {"input_tokens": 1}
            ),
            _assistant_record(
                "req-3", _T0 + timedelta(seconds=2), "claude-unknown-a", {"input_tokens": 1}
            ),
            _assistant_record(
                "req-4", _T0 + timedelta(seconds=3), "claude-unknown-b", {"input_tokens": 1}
            ),
        ],
    )
    summary = ccc.compute_summary(transcript, tmp_path, run_id=None)
    assert summary["unpriced_calls"] == 3
    assert summary["unpriced_models"] == ["claude-unknown-a", "claude-unknown-b"]


def test_context_tokens_ttl_split_present_with_explicit_zero_wins_over_aggregate(tmp_path):
    # Mirrors model_pricing.compute_cost_usd's identical fix: presence of the
    # split KEY wins, not the split value's truthiness. An explicit-zero
    # split must still beat a nonzero aggregate rather than falling through
    # to it (external-review finding, iterate-2026-08-07-context-cost-meter).
    transcript = tmp_path / "session.jsonl"
    _write_transcript(
        transcript,
        [
            _assistant_record(
                "req-1", _T0, "claude-sonnet-5",
                {
                    "cache_creation_input_tokens": 1_000_000,
                    "cache_creation": {
                        "ephemeral_5m_input_tokens": 0,
                        "ephemeral_1h_input_tokens": 0,
                    },
                },
            )
        ],
    )
    summary = ccc.compute_summary(transcript, tmp_path, run_id=None)
    assert summary["context_tokens"] == 0  # split (explicitly zero) wins


def test_many_sub_microdollar_calls_sum_to_a_nonzero_total(tmp_path):
    # External-review finding: a single cache-read token costs $0.0000003 on
    # Sonnet 5 -- below the 6dp rounding threshold, so an old per-call-round
    # design would zero out EVERY one of these before summing, permanently
    # losing real cost from any total built out of many small calls. Four
    # 1-token calls (0.0000003 each) must sum to $0.000001, not $0.0.
    transcript = tmp_path / "session.jsonl"
    _write_transcript(
        transcript,
        [
            _assistant_record(
                f"req-{i}", _T0 + timedelta(seconds=i), "claude-sonnet-5",
                {"cache_read_input_tokens": 1},
            )
            for i in range(4)
        ],
    )
    summary = ccc.compute_summary(transcript, tmp_path, run_id=None)
    assert summary["calls"] == 4
    assert summary["cost_usd"] > 0.0


def test_by_phase_cost_is_not_rounded_after_every_addition(tmp_path):
    # Same bug, at the per-phase bucket level: rounding after each += (the
    # old code) compounds the same sub-microdollar loss inside by_phase even
    # once the top-level total is fixed.
    ipg.append_mark(tmp_path, RUN_ID, "build", ts=_iso(_T0))
    transcript = tmp_path / "session.jsonl"
    _write_transcript(
        transcript,
        [
            _assistant_record(
                f"req-{i}", _T0 + timedelta(minutes=1, seconds=i), "claude-sonnet-5",
                {"cache_read_input_tokens": 1},
            )
            for i in range(4)
        ],
    )
    summary = ccc.compute_summary(transcript, tmp_path, run_id=RUN_ID)
    assert summary["by_phase"]["build"]["cost_usd"] > 0.0


def test_non_dict_cache_creation_degrades_that_call_not_the_whole_summary(tmp_path):
    # An unexpected transcript shape for one field must never abort every
    # OTHER call's accounting in the same file.
    transcript = tmp_path / "session.jsonl"
    _write_transcript(
        transcript,
        [
            _assistant_record(
                "req-1", _T0, "claude-sonnet-5",
                {"input_tokens": 100, "cache_creation": "not-a-dict"},
            ),
            _assistant_record(
                "req-2", _T0 + timedelta(seconds=1), "claude-sonnet-5", {"input_tokens": 50}
            ),
        ],
    )
    summary = ccc.compute_summary(transcript, tmp_path, run_id=None)
    assert summary["calls"] == 2
    assert summary["skipped_malformed"] == 0


def test_all_priced_calls_report_cost_complete_true(tmp_path):
    transcript = tmp_path / "session.jsonl"
    _write_transcript(
        transcript,
        [_assistant_record("req-1", _T0, "claude-sonnet-5", {"input_tokens": 1_000_000})],
    )
    summary = ccc.compute_summary(transcript, tmp_path, run_id=None)
    assert summary["cost_complete"] is True
    assert summary["unpriced_calls"] == 0


# fold_into_event and resolve_active_project_root tests moved to
# test_context_cost_fold.py (300-line size guideline).
