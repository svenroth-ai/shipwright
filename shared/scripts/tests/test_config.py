"""Tests for shared config utilities."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.config import collect_all_build_sections


def test_collect_all_build_sections_multi_split(tmp_path):
    """Reads archived split_NN_sections + current sections."""
    (tmp_path / "shipwright_project_config.json").write_text(json.dumps({
        "splits": [
            {"name": "01-auth", "status": "complete"},
            {"name": "02-dashboard", "status": "in_progress"},
        ],
    }), encoding="utf-8")
    (tmp_path / "shipwright_build_config.json").write_text(json.dumps({
        "current_split": "02-dashboard",
        "completed_splits": ["01-auth"],
        "split_01_sections": [
            {"name": "01-login", "status": "complete", "commit": "aaa"},
            {"name": "02-rbac", "status": "complete", "commit": "bbb"},
        ],
        "sections": [
            {"name": "01-widgets", "status": "complete", "commit": "ccc"},
            {"name": "02-charts", "status": "pending"},
        ],
    }), encoding="utf-8")

    result = collect_all_build_sections(tmp_path)
    assert len(result["archived"]) == 2
    assert len(result["current"]) == 2
    assert len(result["all"]) == 4
    assert result["current_split"] == "02-dashboard"
    assert result["completed_splits"] == ["01-auth"]
    assert result["total_splits"] == 2


def test_collect_all_build_sections_single_split(tmp_path):
    """Single split with no archived sections."""
    (tmp_path / "shipwright_project_config.json").write_text(json.dumps({
        "splits": [{"name": "01-auth", "status": "in_progress"}],
    }), encoding="utf-8")
    (tmp_path / "shipwright_build_config.json").write_text(json.dumps({
        "current_split": "01-auth",
        "sections": [
            {"name": "01-login", "status": "complete", "commit": "aaa"},
        ],
    }), encoding="utf-8")

    result = collect_all_build_sections(tmp_path)
    assert len(result["archived"]) == 0
    assert len(result["current"]) == 1
    assert len(result["all"]) == 1
    assert result["total_splits"] == 1


def test_collect_all_build_sections_no_config(tmp_path):
    """No configs at all — returns empty state."""
    result = collect_all_build_sections(tmp_path)
    assert result["archived"] == []
    assert result["current"] == []
    assert result["all"] == []
    assert result["current_split"] == ""
    assert result["total_splits"] == 0
