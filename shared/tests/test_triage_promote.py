"""AC-7 tests for triage_promote CLI.

Covers:
- happy path (triage → promoted, promotedTaskId recorded)
- missing item id → exit 3 / KeyError
- missing file → exit 4 / FileNotFoundError
- non-triage source state (dismissed, snoozed, promoted) → exit 2 / ValueError
- task-ref sanitization (newline, tab, control char, too long, empty) → exit 2
- CLI smoke (subprocess)
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

_WORKTREE = Path(__file__).resolve().parents[2]
_SHARED_SCRIPTS = _WORKTREE / "shared" / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

from triage import append_triage_item, mark_status, read_all_items  # noqa: E402
from tools.triage_promote import (  # noqa: E402
    dismiss,
    promote,
    sanitize_reason,
    sanitize_task_ref,
)

PROMOTE_CLI = _WORKTREE / "shared" / "scripts" / "tools" / "triage_promote.py"


@pytest.fixture
def project(tmp_path: Path) -> Path:
    return tmp_path


@pytest.fixture
def triage_item(project: Path) -> str:
    return append_triage_item(
        project, source="phaseQuality", severity="high", kind="bug",
        title="t", detail="d",
    )


# --- sanitize_task_ref --------------------------------------------------

def test_sanitize_accepts_normal_ref() -> None:
    assert sanitize_task_ref("EXT:linear-ENG-123") == "EXT:linear-ENG-123"


def test_sanitize_strips_whitespace() -> None:
    assert sanitize_task_ref("  EXT:asana-1  ") == "EXT:asana-1"


def test_sanitize_rejects_empty() -> None:
    with pytest.raises(ValueError, match="empty"):
        sanitize_task_ref("")
    with pytest.raises(ValueError, match="empty"):
        sanitize_task_ref("   ")


def test_sanitize_rejects_newline() -> None:
    with pytest.raises(ValueError, match="control character"):
        sanitize_task_ref("EXT:linear-1\nmalicious")


def test_sanitize_rejects_tab() -> None:
    with pytest.raises(ValueError, match="control character"):
        sanitize_task_ref("EXT:\t1")


def test_sanitize_rejects_control_char() -> None:
    with pytest.raises(ValueError, match="control character"):
        sanitize_task_ref("EXT:\x00bad")
    with pytest.raises(ValueError, match="control character"):
        sanitize_task_ref("EXT:\x7Fdel")


def test_sanitize_rejects_too_long() -> None:
    with pytest.raises(ValueError, match="too long"):
        sanitize_task_ref("X" * 201)


def test_sanitize_accepts_at_limit() -> None:
    # 200 chars OK
    assert sanitize_task_ref("X" * 200) == "X" * 200


# --- promote() happy path ----------------------------------------------

def test_promote_happy_path(project: Path, triage_item: str) -> None:
    result = promote(
        project, item_id=triage_item, task_ref="EXT:linear-ENG-7",
    )
    assert result == {
        "id": triage_item,
        "previousStatus": "triage",
        "newStatus": "promoted",
        "promotedTaskId": "EXT:linear-ENG-7",
    }

    [item] = read_all_items(project)
    assert item["status"] == "promoted"
    assert item["promotedTaskId"] == "EXT:linear-ENG-7"
    assert item["statusReason"] == "manualPromote"


def test_promote_with_reason(project: Path, triage_item: str) -> None:
    promote(
        project, item_id=triage_item, task_ref="EXT:asana-1",
        reason="urgent — Q2 release blocker",
    )
    [item] = read_all_items(project)
    assert item["statusReason"] == "urgent — Q2 release blocker"


# --- promote() error paths ---------------------------------------------

def test_promote_missing_item_raises_keyerror(project: Path) -> None:
    # File exists (item was appended) but the id we ask about doesn't match.
    append_triage_item(
        project, source="phaseQuality", severity="high", kind="bug",
        title="t", detail="d",
    )
    with pytest.raises(KeyError):
        promote(project, item_id="trg-deadbeef", task_ref="EXT:x")


def test_promote_missing_file_raises_filenotfound(project: Path) -> None:
    # No triage.jsonl at all.
    with pytest.raises(FileNotFoundError):
        promote(project, item_id="trg-12345678", task_ref="EXT:x")


def test_promote_rejects_dismissed_source_state(
    project: Path, triage_item: str,
) -> None:
    mark_status(project, triage_item, new_status="dismissed", by="user",
                reason="known-fp")
    with pytest.raises(ValueError, match="only `triage` is"):
        promote(project, item_id=triage_item, task_ref="EXT:x")


def test_promote_rejects_already_promoted(
    project: Path, triage_item: str,
) -> None:
    promote(project, item_id=triage_item, task_ref="EXT:first")
    with pytest.raises(ValueError, match="only `triage` is"):
        promote(project, item_id=triage_item, task_ref="EXT:second")


def test_promote_rejects_snoozed(project: Path, triage_item: str) -> None:
    mark_status(project, triage_item, new_status="snoozed", by="user")
    with pytest.raises(ValueError, match="only `triage` is"):
        promote(project, item_id=triage_item, task_ref="EXT:x")


def test_promote_rejects_invalid_task_ref(
    project: Path, triage_item: str,
) -> None:
    with pytest.raises(ValueError, match="control character"):
        promote(project, item_id=triage_item, task_ref="EXT:x\nbad")


# --- CLI smoke ----------------------------------------------------------

def _run_cli(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(PROMOTE_CLI), *args],
        capture_output=True, text=True, check=False,
    )


def test_cli_happy_path(project: Path, triage_item: str) -> None:
    result = _run_cli([
        "--project-root", str(project),
        "--id", triage_item,
        "--task-ref", "EXT:linear-ENG-12",
    ])
    assert result.returncode == 0, (
        f"exit {result.returncode}\nstderr: {result.stderr}\nstdout: {result.stdout}"
    )
    [item] = read_all_items(project)
    assert item["status"] == "promoted"
    assert item["promotedTaskId"] == "EXT:linear-ENG-12"


def test_cli_exits_2_on_bad_task_ref(project: Path, triage_item: str) -> None:
    result = _run_cli([
        "--project-root", str(project),
        "--id", triage_item,
        "--task-ref", "EXT:has\ttab",
    ])
    assert result.returncode == 2
    assert "control character" in result.stderr


def test_cli_exits_2_on_non_triage_state(
    project: Path, triage_item: str,
) -> None:
    mark_status(project, triage_item, new_status="dismissed", by="user")
    result = _run_cli([
        "--project-root", str(project),
        "--id", triage_item,
        "--task-ref", "EXT:x",
    ])
    assert result.returncode == 2


def test_cli_exits_3_on_unknown_id(project: Path, triage_item: str) -> None:
    result = _run_cli([
        "--project-root", str(project),
        "--id", "trg-00000000",
        "--task-ref", "EXT:x",
    ])
    assert result.returncode == 3


def test_cli_exits_4_on_missing_file(project: Path) -> None:
    result = _run_cli([
        "--project-root", str(project),
        "--id", "trg-deadbeef",
        "--task-ref", "EXT:x",
    ])
    assert result.returncode == 4
    assert "not initialised" in result.stderr


# ---------------------------------------------------------------------------
# dismiss() library helper — added in iterate-2026-05-20-triage-launch-surface
# Mirrors promote() shape; called by the new triage_cli.py and by future
# WebUI Triage tab. Lives alongside promote() so the CLI parity story
# (AC-11) holds without sys.path gymnastics.
# ---------------------------------------------------------------------------


# --- sanitize_reason ----------------------------------------------------

def test_sanitize_reason_accepts_normal() -> None:
    assert sanitize_reason("known false positive") == "known false positive"


def test_sanitize_reason_strips_whitespace() -> None:
    assert sanitize_reason("  notRelevant  ") == "notRelevant"


def test_sanitize_reason_rejects_empty() -> None:
    with pytest.raises(ValueError, match="empty"):
        sanitize_reason("")
    with pytest.raises(ValueError, match="empty"):
        sanitize_reason("   ")


def test_sanitize_reason_rejects_newline() -> None:
    with pytest.raises(ValueError, match="control character"):
        sanitize_reason("notRelevant\nmore")


def test_sanitize_reason_rejects_too_long() -> None:
    with pytest.raises(ValueError, match="too long"):
        sanitize_reason("X" * 501)


def test_sanitize_reason_accepts_at_limit() -> None:
    # 500 chars OK (longer than task_ref since reasons can be more prose).
    assert sanitize_reason("X" * 500) == "X" * 500


# --- dismiss() happy path ----------------------------------------------

def test_dismiss_happy_path(project: Path, triage_item: str) -> None:
    result = dismiss(
        project, item_id=triage_item, reason="notRelevant",
    )
    assert result == {
        "id": triage_item,
        "previousStatus": "triage",
        "newStatus": "dismissed",
        "reason": "notRelevant",
    }

    [item] = read_all_items(project)
    assert item["status"] == "dismissed"
    assert item["statusReason"] == "notRelevant"


def test_dismiss_records_by_actor(project: Path, triage_item: str) -> None:
    dismiss(project, item_id=triage_item, reason="known-fp", by="cli")
    [item] = read_all_items(project)
    assert item["statusBy"] == "cli"


# --- dismiss() error paths ---------------------------------------------

def test_dismiss_missing_item_raises_keyerror(project: Path) -> None:
    append_triage_item(
        project, source="phaseQuality", severity="high", kind="bug",
        title="t", detail="d",
    )
    with pytest.raises(KeyError):
        dismiss(project, item_id="trg-deadbeef", reason="x")


def test_dismiss_missing_file_raises_filenotfound(project: Path) -> None:
    with pytest.raises(FileNotFoundError):
        dismiss(project, item_id="trg-12345678", reason="x")


def test_dismiss_rejects_already_dismissed(
    project: Path, triage_item: str,
) -> None:
    mark_status(project, triage_item, new_status="dismissed", by="user")
    with pytest.raises(ValueError, match="only `triage` is"):
        dismiss(project, item_id=triage_item, reason="x")


def test_dismiss_rejects_promoted(project: Path, triage_item: str) -> None:
    promote(project, item_id=triage_item, task_ref="EXT:foo")
    with pytest.raises(ValueError, match="only `triage` is"):
        dismiss(project, item_id=triage_item, reason="x")


def test_dismiss_rejects_invalid_reason(
    project: Path, triage_item: str,
) -> None:
    with pytest.raises(ValueError, match="control character"):
        dismiss(project, item_id=triage_item, reason="bad\nreason")


# --- promote() — reason sanitization (code review MED #3) ---------------

def test_promote_rejects_invalid_reason(
    project: Path, triage_item: str,
) -> None:
    """A control-char-bearing reason on promote must be rejected, matching
    the dismiss path (code review MED #3 of iterate-2026-05-20)."""
    with pytest.raises(ValueError, match="control character"):
        promote(
            project, item_id=triage_item,
            task_ref="EXT:foo", reason="bad\nreason",
        )


def test_promote_rejects_too_long_reason(
    project: Path, triage_item: str,
) -> None:
    with pytest.raises(ValueError, match="too long"):
        promote(
            project, item_id=triage_item,
            task_ref="EXT:foo", reason="X" * 501,
        )


def test_promote_default_reason_when_none_passed(
    project: Path, triage_item: str,
) -> None:
    """Backward-compat: passing reason=None still yields 'manualPromote'."""
    promote(project, item_id=triage_item, task_ref="EXT:foo", reason=None)
    [item] = read_all_items(project)
    assert item["statusReason"] == "manualPromote"


def test_promote_strips_whitespace_in_reason(
    project: Path, triage_item: str,
) -> None:
    promote(
        project, item_id=triage_item,
        task_ref="EXT:foo", reason="  urgent — Q2 release  ",
    )
    [item] = read_all_items(project)
    assert item["statusReason"] == "urgent — Q2 release"
