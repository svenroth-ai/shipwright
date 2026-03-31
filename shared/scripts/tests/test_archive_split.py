"""Tests for archive_split tool."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.archive_split import archive_split


def _write_configs(tmp_path, build_config, project_config=None):
    """Helper to write config files for tests."""
    (tmp_path / "shipwright_build_config.json").write_text(
        json.dumps(build_config, indent=2), encoding="utf-8"
    )
    if project_config is None:
        project_config = {"splits": []}
    (tmp_path / "shipwright_project_config.json").write_text(
        json.dumps(project_config, indent=2), encoding="utf-8"
    )


def _read_build_config(tmp_path):
    return json.loads(
        (tmp_path / "shipwright_build_config.json").read_text(encoding="utf-8")
    )


def test_archive_split_basic(tmp_path):
    """Archives sections with all fields including test counts."""
    _write_configs(tmp_path, {
        "current_split": "01-foundation",
        "completed_splits": [],
        "sections": [
            {
                "name": "01-setup",
                "status": "complete",
                "commit": "abc123",
                "tests_passed": 15,
                "tests_total": 15,
                "code_review_findings": [{"issue": "minor", "status": "fixed"}],
            },
            {
                "name": "02-auth",
                "status": "complete",
                "commit": "def456",
                "tests_passed": 8,
                "tests_total": 8,
            },
        ],
    })

    result = archive_split(tmp_path, "02-course-platform")

    assert result["success"] is True
    assert result["archived_key"] == "split_01_sections"
    assert result["archived_count"] == 2
    assert result["current_split"] == "02-course-platform"
    assert result["completed_splits"] == ["01-foundation"]

    # Verify persisted config
    config = _read_build_config(tmp_path)
    assert config["current_split"] == "02-course-platform"
    assert config["completed_splits"] == ["01-foundation"]
    assert config["sections"] == []
    assert len(config["split_01_sections"]) == 2
    # Test counts preserved
    assert config["split_01_sections"][0]["tests_passed"] == 15
    assert config["split_01_sections"][0]["tests_total"] == 15
    assert config["split_01_sections"][0]["code_review_findings"][0]["status"] == "fixed"


def test_archive_split_idempotent(tmp_path):
    """Skips if split already archived."""
    _write_configs(tmp_path, {
        "current_split": "02-course-platform",
        "completed_splits": ["01-foundation"],
        "split_01_sections": [
            {"name": "01-setup", "status": "complete", "commit": "abc123"},
        ],
        "sections": [
            {"name": "01-lessons", "status": "in_progress"},
        ],
    })

    # Try to archive split 01 again (current_split is already 02)
    # This simulates re-running when archive_key already exists
    # We need to set current_split to 01 to trigger the archive path
    _write_configs(tmp_path, {
        "current_split": "01-foundation",
        "completed_splits": [],
        "split_01_sections": [
            {"name": "01-setup", "status": "complete", "commit": "abc123"},
        ],
        "sections": [
            {"name": "01-lessons", "status": "complete"},
        ],
    })

    result = archive_split(tmp_path, "02-course-platform")

    assert result["success"] is True
    assert result["skipped"] is True
    assert "already exists" in result["message"]

    # Config not modified
    config = _read_build_config(tmp_path)
    assert len(config["split_01_sections"]) == 1  # Original, not overwritten


def test_archive_split_no_current_split(tmp_path):
    """Fails gracefully when current_split is not set."""
    _write_configs(tmp_path, {
        "sections": [{"name": "01-setup", "status": "complete"}],
    })

    result = archive_split(tmp_path, "02-next")
    assert result["success"] is False
    assert "current_split" in result["error"]


def test_archive_split_no_sections(tmp_path):
    """Fails gracefully when there are no sections to archive."""
    _write_configs(tmp_path, {
        "current_split": "01-foundation",
        "completed_splits": [],
        "sections": [],
    })

    result = archive_split(tmp_path, "02-next")
    assert result["success"] is False
    assert "No sections" in result["error"]


def test_archive_split_preserves_other_config_keys(tmp_path):
    """Other build config keys are not lost during archiving."""
    _write_configs(tmp_path, {
        "current_split": "01-foundation",
        "completed_splits": [],
        "sections": [
            {"name": "01-setup", "status": "complete", "commit": "abc"},
        ],
        "some_other_key": "preserved",
        "build_started_at": "2026-03-30T10:00:00Z",
    })

    archive_split(tmp_path, "02-course-platform")

    config = _read_build_config(tmp_path)
    assert config["some_other_key"] == "preserved"
    assert config["build_started_at"] == "2026-03-30T10:00:00Z"


def test_archive_split_multi_digit_prefix(tmp_path):
    """Handles split names with multi-digit prefixes like 10-payments."""
    _write_configs(tmp_path, {
        "current_split": "10-payments",
        "completed_splits": ["01-foundation", "02-course-platform"],
        "split_01_sections": [{"name": "01-a", "status": "complete"}],
        "split_02_sections": [{"name": "01-b", "status": "complete"}],
        "sections": [
            {"name": "01-stripe", "status": "complete", "commit": "xyz"},
        ],
    })

    result = archive_split(tmp_path, "11-crm")

    assert result["success"] is True
    assert result["archived_key"] == "split_10_sections"
    assert result["current_split"] == "11-crm"
    assert "10-payments" in result["completed_splits"]

    config = _read_build_config(tmp_path)
    assert len(config["split_10_sections"]) == 1
    # Previous archives untouched
    assert len(config["split_01_sections"]) == 1
    assert len(config["split_02_sections"]) == 1
