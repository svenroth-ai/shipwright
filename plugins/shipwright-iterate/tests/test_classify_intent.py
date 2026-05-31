"""Unit tests for classify_intent.py (backfill — missing in v0.2.0)."""

import json
import sys
from pathlib import Path


sys.path.insert(
    0,
    str(Path(__file__).resolve().parent.parent / "scripts" / "lib"),
)

from classify_intent import classify


class TestIntentClassification:
    def test_feature_keywords(self):
        result = classify("add a new search feature to the course list")
        assert result["type"] == "feature"
        assert result["confidence"] > 0.5

    def test_change_keywords(self):
        result = classify("refactor the sidebar component to use different layout")
        assert result["type"] == "change"

    def test_bug_keywords(self):
        result = classify("fix the broken login page error")
        assert result["type"] == "bug"
        assert result["confidence"] > 0.5

    def test_non_english_input_not_classified(self):
        """Non-English input should not match English-only keywords."""
        result = classify("Login ist kaputt, fehler beim Redirect")
        assert result["type"] == "none"

    def test_none_for_greeting(self):
        result = classify("hello there")
        assert result["type"] == "none"

    def test_none_for_slash_command(self):
        result = classify("/shipwright-build something")
        assert result["type"] == "none"

    def test_none_for_question(self):
        result = classify("what does this function do?")
        assert result["type"] == "none"

    def test_none_for_empty(self):
        result = classify("")
        assert result["type"] == "none"

    def test_confidence_increases_with_keywords(self):
        single = classify("add a feature")
        multi = classify("add and create a new feature, implement it")
        assert multi["confidence"] >= single["confidence"]

    def test_summary_truncation(self):
        long_msg = "fix " + "a" * 200
        result = classify(long_msg)
        assert len(result["summary"]) <= 83  # 80 + "..."
        assert result["summary"].endswith("...")

    def test_affected_frs_empty_without_config(self):
        result = classify("fix the login page")
        assert result["affected_frs"] == []


class TestSyncConfigMapping:
    def test_frs_found_from_sync_config(self, tmp_path):
        config = {
            "mappings": [
                {"pattern": "src/components/login/**", "frs": ["FR-01.03"]},
            ]
        }
        config_path = tmp_path / "sync.json"
        config_path.write_text(json.dumps(config))

        result = classify("fix the login component issue", str(config_path))
        assert "FR-01.03" in result["affected_frs"]

    def test_frs_empty_when_no_match(self, tmp_path):
        config = {
            "mappings": [
                {"pattern": "src/components/dashboard/**", "frs": ["FR-02.01"]},
            ]
        }
        config_path = tmp_path / "sync.json"
        config_path.write_text(json.dumps(config))

        result = classify("fix the login page", str(config_path))
        assert result["affected_frs"] == []

    def test_nonexistent_config(self):
        result = classify("fix something", "/nonexistent/path.json")
        assert result["affected_frs"] == []

    def test_confidence_boost_with_fr_match(self, tmp_path):
        config = {
            "mappings": [
                {"pattern": "src/components/login/**", "frs": ["FR-01.03"]},
            ]
        }
        config_path = tmp_path / "sync.json"
        config_path.write_text(json.dumps(config))

        without = classify("fix the login issue")
        with_config = classify("fix the login issue", str(config_path))
        assert with_config["confidence"] >= without["confidence"]
