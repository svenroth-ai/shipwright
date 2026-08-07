"""Tests for estimate_context_pressure.py."""

import json
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.estimate_context_pressure import estimate_pressure, estimate_pressure_context_cost


def _make_counter(tmp_path: Path) -> Path:
    """Create the .shipwright/ parent dir and return the counter-file path."""
    counter = tmp_path / ".shipwright" / "toolcall_count"
    counter.parent.mkdir(parents=True, exist_ok=True)
    return counter


class TestEstimatePressure:
    def test_below_threshold(self, tmp_path):
        counter = _make_counter(tmp_path)
        counter.write_text("50", encoding="utf-8")
        result = estimate_pressure(counter, threshold=120)
        assert result["tool_calls"] == 50
        assert result["threshold"] == 120
        assert result["recommend_checkpoint"] is False

    def test_at_threshold(self, tmp_path):
        counter = _make_counter(tmp_path)
        counter.write_text("120", encoding="utf-8")
        result = estimate_pressure(counter, threshold=120)
        assert result["recommend_checkpoint"] is True

    def test_above_threshold(self, tmp_path):
        counter = _make_counter(tmp_path)
        counter.write_text("200", encoding="utf-8")
        result = estimate_pressure(counter, threshold=120)
        assert result["tool_calls"] == 200
        assert result["recommend_checkpoint"] is True

    def test_missing_file(self, tmp_path):
        # Deliberately do NOT create the parent dir — exercise the
        # missing-file path (reader returns 0).
        counter = tmp_path / ".shipwright" / "toolcall_count"
        result = estimate_pressure(counter, threshold=120)
        assert result["tool_calls"] == 0
        assert result["recommend_checkpoint"] is False

    def test_corrupt_file(self, tmp_path):
        counter = _make_counter(tmp_path)
        counter.write_text("not-a-number", encoding="utf-8")
        result = estimate_pressure(counter, threshold=120)
        assert result["tool_calls"] == 0
        assert result["recommend_checkpoint"] is False

    def test_empty_file(self, tmp_path):
        counter = _make_counter(tmp_path)
        counter.write_text("", encoding="utf-8")
        result = estimate_pressure(counter, threshold=120)
        assert result["tool_calls"] == 0

    def test_custom_threshold(self, tmp_path):
        counter = _make_counter(tmp_path)
        counter.write_text("30", encoding="utf-8")
        result = estimate_pressure(counter, threshold=25)
        assert result["recommend_checkpoint"] is True


def _write_context_cost_summary(project_root: Path, session_id: str, summary: dict) -> None:
    path = project_root / ".shipwright" / "compliance" / "context-cost" / f"{session_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary), encoding="utf-8")


class TestEstimatePressureContextCost:
    """--source context-cost: reads the CURRENT session's measured-cost
    summary instead of the toolcall counter, at the same thresholds."""

    def test_reads_current_session_only_by_env_var(self, tmp_path, monkeypatch):
        # Same session id the writer (track_context_cost.py) would use when
        # its own payload is absent -- SHIPWRIGHT_SESSION_ID, no fallback to
        # a stdin payload this reader never has.
        monkeypatch.setenv("SHIPWRIGHT_SESSION_ID", "sess-current")
        _write_context_cost_summary(
            tmp_path, "sess-current",
            {"calls": 50, "cost_usd": 1.5, "unpriced_calls": 0, "cost_complete": True, "by_phase": {}},
        )
        _write_context_cost_summary(
            tmp_path, "sess-other-session",
            {"calls": 999, "cost_usd": 50.0, "unpriced_calls": 0, "cost_complete": True, "by_phase": {}},
        )

        result = estimate_pressure_context_cost(tmp_path, threshold=120, mode="builder")

        assert result["tool_calls"] == 50  # only the current session's file
        assert result["source"] == "context-cost"
        assert result["cost_usd"] == 1.5
        assert result["recommend_checkpoint"] is False

    def test_above_threshold_recommends_checkpoint(self, tmp_path, monkeypatch):
        monkeypatch.setenv("SHIPWRIGHT_SESSION_ID", "sess-current")
        _write_context_cost_summary(
            tmp_path, "sess-current",
            {"calls": 200, "cost_usd": 8.0, "unpriced_calls": 0, "cost_complete": True, "by_phase": {}},
        )

        result = estimate_pressure_context_cost(tmp_path, threshold=120, mode="builder")

        assert result["recommend_checkpoint"] is True

    def test_no_data_yet_is_zero_not_a_crash(self, tmp_path, monkeypatch):
        monkeypatch.setenv("SHIPWRIGHT_SESSION_ID", "sess-never-stopped")

        result = estimate_pressure_context_cost(tmp_path, threshold=120, mode="builder")

        assert result["tool_calls"] == 0
        assert result["recommend_checkpoint"] is False
        assert result["no_data"] is True

    def test_incomplete_cost_is_surfaced_not_hidden(self, tmp_path, monkeypatch):
        monkeypatch.setenv("SHIPWRIGHT_SESSION_ID", "sess-current")
        _write_context_cost_summary(
            tmp_path, "sess-current",
            {"calls": 10, "cost_usd": 0.2, "unpriced_calls": 1, "cost_complete": False, "by_phase": {}},
        )

        result = estimate_pressure_context_cost(tmp_path, threshold=120, mode="builder")

        assert result["cost_complete"] is False

    def test_no_session_id_at_all_is_no_data_not_a_stray_unknown_file(
        self, tmp_path, monkeypatch
    ):
        # External-review finding: a fixed "unknown" fallback for a missing
        # SHIPWRIGHT_SESSION_ID would pool every such call into one shared
        # file. Even with a stray "unknown.json" left on disk by an
        # unrelated caller, a genuinely absent session id must read back as
        # no-data, never that file's contents.
        monkeypatch.delenv("SHIPWRIGHT_SESSION_ID", raising=False)
        _write_context_cost_summary(
            tmp_path, "unknown",
            {"calls": 999, "cost_usd": 50.0, "unpriced_calls": 0, "cost_complete": True, "by_phase": {}},
        )

        result = estimate_pressure_context_cost(tmp_path, threshold=120, mode="builder")

        assert result["tool_calls"] == 0
        assert result["no_data"] is True
