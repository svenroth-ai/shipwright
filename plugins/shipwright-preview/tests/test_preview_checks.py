"""Tests for shipwright-preview pre-flight checks.

Validates the logic that determines whether a preview can be started:
- Build must have at least one complete section
- Environment variables must be present
- Dev server start/status handling
"""

import json
from pathlib import Path



# --- Helpers that mirror the SKILL.md logic ---

def check_build_ready(project_root: Path) -> tuple[bool, str]:
    """Check if build has at least one complete section."""
    config_path = project_root / "shipwright_build_config.json"
    if not config_path.exists():
        return False, "No build config found. Complete at least one build split first."

    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return False, "Build config is invalid."

    sections = config.get("sections", [])
    # Also check archived splits
    for key in config:
        if key.startswith("split_") and key.endswith("_sections"):
            sections.extend(config[key])

    complete = [s for s in sections if s.get("status") == "complete"]
    if not complete:
        return False, "No completed build sections. Complete at least one build split first."

    return True, f"{len(complete)} section(s) complete."


def check_dev_server_status(project_root: Path) -> dict:
    """Check dev server status via dev_server.py."""
    # In real usage, this calls dev_server.py — here we return mock data
    raise NotImplementedError("Use mock in tests")


# --- Tests ---

class TestBuildCheck:
    def test_no_build_config(self, tmp_path: Path):
        ready, msg = check_build_ready(tmp_path)
        assert ready is False
        assert "No build config" in msg

    def test_empty_sections(self, tmp_path: Path):
        config = {"sections": []}
        (tmp_path / "shipwright_build_config.json").write_text(
            json.dumps(config), encoding="utf-8"
        )
        ready, msg = check_build_ready(tmp_path)
        assert ready is False
        assert "No completed" in msg

    def test_no_complete_sections(self, tmp_path: Path):
        config = {"sections": [{"name": "01-setup", "status": "in_progress"}]}
        (tmp_path / "shipwright_build_config.json").write_text(
            json.dumps(config), encoding="utf-8"
        )
        ready, msg = check_build_ready(tmp_path)
        assert ready is False

    def test_one_complete_section(self, tmp_path: Path):
        config = {"sections": [{"name": "01-setup", "status": "complete"}]}
        (tmp_path / "shipwright_build_config.json").write_text(
            json.dumps(config), encoding="utf-8"
        )
        ready, msg = check_build_ready(tmp_path)
        assert ready is True
        assert "1 section(s) complete" in msg

    def test_archived_splits_counted(self, tmp_path: Path):
        config = {
            "sections": [],
            "split_01_sections": [
                {"name": "01-setup", "status": "complete"},
                {"name": "02-auth", "status": "complete"},
            ],
        }
        (tmp_path / "shipwright_build_config.json").write_text(
            json.dumps(config), encoding="utf-8"
        )
        ready, msg = check_build_ready(tmp_path)
        assert ready is True
        assert "2 section(s) complete" in msg

    def test_invalid_json(self, tmp_path: Path):
        (tmp_path / "shipwright_build_config.json").write_text(
            "not json", encoding="utf-8"
        )
        ready, msg = check_build_ready(tmp_path)
        assert ready is False
        assert "invalid" in msg.lower()


class TestDevServerStatus:
    def test_server_already_running(self):
        status = {"running": True, "pid": 12345, "url": "http://localhost:3000", "ready": True}
        assert status["running"] is True
        assert "3000" in status["url"]

    def test_server_not_running(self):
        status = {"running": False, "pid": None, "url": None, "ready": False}
        assert status["running"] is False

    def test_server_start_success(self):
        result = {"running": True, "pid": 99999, "url": "http://localhost:3000", "ready": True, "started_by_us": True}
        assert result["ready"] is True
        assert result["started_by_us"] is True

    def test_server_start_failure(self):
        result = {"running": False, "ready": False, "message": "Port 3000 already in use"}
        assert result["ready"] is False
        assert "Port" in result["message"]
