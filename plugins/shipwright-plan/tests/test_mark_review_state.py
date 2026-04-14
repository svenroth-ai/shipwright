"""Tests for mark-review-state.py script."""

import json
import subprocess
import sys
from pathlib import Path

SCRIPT = str(
    Path(__file__).resolve().parent.parent / "scripts" / "checks" / "mark-review-state.py"
)


def run_mark(args: list[str]) -> tuple[int, dict]:
    result = subprocess.run(
        [sys.executable, SCRIPT] + args,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    payload = json.loads(result.stdout) if result.stdout else {}
    return result.returncode, payload


def test_mark_completed(tmp_planning):
    rc, payload = run_mark([
        "--planning-dir", str(tmp_planning),
        "--status", "completed",
        "--provider", "openrouter",
        "--findings-count", "5",
    ])
    assert rc == 0
    assert payload["success"] is True

    marker = tmp_planning / "external_review_state.json"
    assert marker.exists()
    state = json.loads(marker.read_text(encoding="utf-8"))
    assert state["status"] == "completed"
    assert state["provider"] == "openrouter"
    assert state["findings_count"] == 5
    assert state["self_review_fallback_ran"] is False
    assert state["reason"] is None
    assert "timestamp" in state


def test_mark_skipped_user_opt_out_flags_self_review(tmp_planning):
    rc, payload = run_mark([
        "--planning-dir", str(tmp_planning),
        "--status", "skipped_user_opt_out",
        "--reason", "offline demo",
    ])
    assert rc == 0
    assert payload["success"] is True

    state = json.loads((tmp_planning / "external_review_state.json").read_text(encoding="utf-8"))
    assert state["status"] == "skipped_user_opt_out"
    assert state["reason"] == "offline demo"
    assert state["self_review_fallback_ran"] is True


def test_mark_skipped_config_disabled(tmp_planning):
    rc, _ = run_mark([
        "--planning-dir", str(tmp_planning),
        "--status", "skipped_config_disabled",
    ])
    assert rc == 0
    state = json.loads((tmp_planning / "external_review_state.json").read_text(encoding="utf-8"))
    assert state["status"] == "skipped_config_disabled"
    assert state["self_review_fallback_ran"] is True


def test_mark_rejects_invalid_status(tmp_planning):
    rc, payload = run_mark([
        "--planning-dir", str(tmp_planning),
        "--status", "bogus",
    ])
    assert rc == 2
    assert payload["success"] is False
    assert payload["error"] == "invalid_status"


def test_mark_rejects_missing_planning_dir(tmp_path):
    missing = tmp_path / "does_not_exist"
    rc, payload = run_mark([
        "--planning-dir", str(missing),
        "--status", "completed",
    ])
    assert rc == 2
    assert payload["success"] is False
    assert payload["error"] == "planning_dir_not_found"
