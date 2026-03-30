"""Tests for estimate_context_pressure.py."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.estimate_context_pressure import estimate_pressure


class TestEstimatePressure:
    def test_below_threshold(self, tmp_path):
        counter = tmp_path / ".shipwright_toolcall_count"
        counter.write_text("50", encoding="utf-8")
        result = estimate_pressure(counter, threshold=120)
        assert result["tool_calls"] == 50
        assert result["threshold"] == 120
        assert result["recommend_checkpoint"] is False

    def test_at_threshold(self, tmp_path):
        counter = tmp_path / ".shipwright_toolcall_count"
        counter.write_text("120", encoding="utf-8")
        result = estimate_pressure(counter, threshold=120)
        assert result["recommend_checkpoint"] is True

    def test_above_threshold(self, tmp_path):
        counter = tmp_path / ".shipwright_toolcall_count"
        counter.write_text("200", encoding="utf-8")
        result = estimate_pressure(counter, threshold=120)
        assert result["tool_calls"] == 200
        assert result["recommend_checkpoint"] is True

    def test_missing_file(self, tmp_path):
        counter = tmp_path / ".shipwright_toolcall_count"
        result = estimate_pressure(counter, threshold=120)
        assert result["tool_calls"] == 0
        assert result["recommend_checkpoint"] is False

    def test_corrupt_file(self, tmp_path):
        counter = tmp_path / ".shipwright_toolcall_count"
        counter.write_text("not-a-number", encoding="utf-8")
        result = estimate_pressure(counter, threshold=120)
        assert result["tool_calls"] == 0
        assert result["recommend_checkpoint"] is False

    def test_empty_file(self, tmp_path):
        counter = tmp_path / ".shipwright_toolcall_count"
        counter.write_text("", encoding="utf-8")
        result = estimate_pressure(counter, threshold=120)
        assert result["tool_calls"] == 0

    def test_custom_threshold(self, tmp_path):
        counter = tmp_path / ".shipwright_toolcall_count"
        counter.write_text("30", encoding="utf-8")
        result = estimate_pressure(counter, threshold=25)
        assert result["recommend_checkpoint"] is True
