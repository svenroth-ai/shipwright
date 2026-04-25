"""Tests for shared/scripts/checks/mark-review-state.py."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = str(
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "checks"
    / "mark-review-state.py"
)


@pytest.fixture
def tmp_planning(tmp_path):
    """Create a planning directory for marker writes."""
    planning = tmp_path / "planning"
    planning.mkdir()
    return planning


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


# ---- --review-type variants (code | plan | iterate, default) --------------
#
# code  → writes external_code_review_state.json (new marker for the
#         code-review cascade in build/iterate medium+ runs)
# plan  → writes external_review_state.json (existing behavior, explicit)
# iterate → writes external_review_state.json (existing behavior, explicit)
# omitted → writes external_review_state.json (backward-compat default)


def test_mark_review_type_code_writes_distinct_marker(tmp_planning):
    """--review-type code → external_code_review_state.json (NOT external_review_state.json)."""
    rc, payload = run_mark([
        "--planning-dir", str(tmp_planning),
        "--status", "completed",
        "--provider", "openrouter",
        "--review-type", "code",
        "--findings-count", "3",
    ])
    assert rc == 0
    assert payload["success"] is True

    code_marker = tmp_planning / "external_code_review_state.json"
    plan_marker = tmp_planning / "external_review_state.json"
    assert code_marker.exists(), "code review marker file must be written"
    assert not plan_marker.exists(), \
        "plan/iterate marker must NOT be touched when --review-type code"

    state = json.loads(code_marker.read_text(encoding="utf-8"))
    assert state["status"] == "completed"
    assert state["provider"] == "openrouter"
    assert state["findings_count"] == 3
    # Marker payload uses 'review_mode' (NOT 'review_type') to disambiguate
    # from the build dashboard's separate review_type taxonomy.
    assert state["review_mode"] == "code"
    assert "review_type" not in state, \
        "marker must NOT include review_type — that name is reserved for build-side taxonomy"


def test_mark_review_type_omitted_writes_null_review_mode(tmp_planning):
    """No --review-type → marker payload review_mode is null (not 'plan' default)."""
    rc, _ = run_mark([
        "--planning-dir", str(tmp_planning),
        "--status", "completed",
    ])
    assert rc == 0
    state = json.loads(
        (tmp_planning / "external_review_state.json").read_text(encoding="utf-8")
    )
    # Explicit None rather than defaulting to "plan" — avoids mis-attributing
    # legacy iterate-flow callers that don't pass --review-type.
    assert state["review_mode"] is None


def test_mark_review_type_plan_keeps_existing_marker(tmp_planning):
    """Explicit --review-type plan → still writes external_review_state.json."""
    rc, _ = run_mark([
        "--planning-dir", str(tmp_planning),
        "--status", "completed",
        "--review-type", "plan",
    ])
    assert rc == 0
    assert (tmp_planning / "external_review_state.json").exists()
    assert not (tmp_planning / "external_code_review_state.json").exists()


def test_mark_review_type_iterate_keeps_existing_marker(tmp_planning):
    """Explicit --review-type iterate → still writes external_review_state.json."""
    rc, _ = run_mark([
        "--planning-dir", str(tmp_planning),
        "--status", "completed",
        "--review-type", "iterate",
    ])
    assert rc == 0
    assert (tmp_planning / "external_review_state.json").exists()
    assert not (tmp_planning / "external_code_review_state.json").exists()


def test_mark_review_type_omitted_keeps_existing_marker(tmp_planning):
    """No --review-type → backward-compat: writes external_review_state.json."""
    rc, _ = run_mark([
        "--planning-dir", str(tmp_planning),
        "--status", "completed",
    ])
    assert rc == 0
    assert (tmp_planning / "external_review_state.json").exists()
    assert not (tmp_planning / "external_code_review_state.json").exists()


def test_mark_review_type_invalid_value_rejected(tmp_planning):
    """Argparse must reject unknown --review-type values (non-zero exit)."""
    rc, _ = run_mark([
        "--planning-dir", str(tmp_planning),
        "--status", "completed",
        "--review-type", "bogus",
    ])
    assert rc != 0


def test_mark_review_type_code_skipped_user_opt_out(tmp_planning):
    """code marker honors skipped_user_opt_out semantics like the plan/iterate marker."""
    rc, _ = run_mark([
        "--planning-dir", str(tmp_planning),
        "--status", "skipped_user_opt_out",
        "--review-type", "code",
        "--reason", "operator declined external code review",
    ])
    assert rc == 0
    state = json.loads(
        (tmp_planning / "external_code_review_state.json").read_text(encoding="utf-8")
    )
    assert state["status"] == "skipped_user_opt_out"
    assert state["reason"] == "operator declined external code review"
    assert state["self_review_fallback_ran"] is True
