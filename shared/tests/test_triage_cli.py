"""Tests for shared/scripts/tools/triage_cli.py (iterate-2026-05-20-triage-launch-surface).

AC-4 (list), AC-5 (promote), AC-6 (dismiss), AC-11 (parity with
triage_promote.py). Positional-id syntax per review finding #1.

CLI delegates to the library helpers in triage_promote (promote_item /
dismiss_item) — no semantic divergence beyond the `by` field.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

_WORKTREE = Path(__file__).resolve().parents[2]
_SHARED_SCRIPTS = _WORKTREE / "shared" / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

from triage import (  # noqa: E402
    TRIAGE_FILE,
    append_triage_item,
    mark_status,
    read_all_items,
)

TRIAGE_CLI = _WORKTREE / "shared" / "scripts" / "tools" / "triage_cli.py"
TRIAGE_PROMOTE = _WORKTREE / "shared" / "scripts" / "tools" / "triage_promote.py"


def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(TRIAGE_CLI), *args],
        capture_output=True, text=True, check=False,
    )


def _run_promote(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(TRIAGE_PROMOTE), *args],
        capture_output=True, text=True, check=False,
    )


@pytest.fixture
def project(tmp_path: Path) -> Path:
    return tmp_path


@pytest.fixture
def triage_item_with_payload(project: Path) -> str:
    return append_triage_item(
        project, source="github", severity="high", kind="bug",
        title="GitHub security: 12 code-scanning + 4 dependabot (high)",
        detail="Repo acme/foo | code-scanning: 8 high, 4 medium",
        dedup_key="gh-security:acme/foo",
        launch_payload=(
            "/shipwright-security\n\n"
            "Context: 12 code-scanning + 4 dependabot for acme/foo.\n"
            "Live state: https://github.com/acme/foo/security"
        ),
    )


@pytest.fixture
def legacy_item_no_payload(project: Path) -> str:
    return append_triage_item(
        project, source="phaseQuality", severity="high", kind="bug",
        title="Phase-Quality C1 failure", detail="some context",
    )


# ---------------------------------------------------------------------------
# AC-4 — list subcommand
# ---------------------------------------------------------------------------

def test_list_empty_project(project: Path) -> None:
    result = _run(["--project-root", str(project), "list"])
    assert result.returncode == 0, result.stderr
    assert "No open triage items" in result.stdout


def test_list_renders_item_with_payload(
    project: Path, triage_item_with_payload: str,
) -> None:
    result = _run(["--project-root", str(project), "list"])
    assert result.returncode == 0, result.stderr
    assert triage_item_with_payload in result.stdout
    # Header line with severity + dedupKey-derived source
    assert "high" in result.stdout
    assert "gh-security:acme/foo" in result.stdout
    # Fenced payload present
    assert "/shipwright-security" in result.stdout
    assert "Live state:" in result.stdout


def test_list_renders_legacy_item_without_fence(
    project: Path, legacy_item_no_payload: str,
) -> None:
    result = _run(["--project-root", str(project), "list"])
    assert result.returncode == 0
    assert legacy_item_no_payload in result.stdout
    assert "Phase-Quality C1 failure" in result.stdout
    # No fenced payload (legacy producer)
    assert "```" not in result.stdout


def test_list_strips_control_chars_from_payload(project: Path) -> None:
    """Review finding #10: control chars in the payload must not reach stdout.

    A malicious or malformed producer could embed a terminal escape; the
    CLI strips them before printing. Newlines and tabs are preserved.
    """
    bad_payload = "/shipwright-security\n\x1b]2;malicious title\x07normal text"
    append_triage_item(
        project, source="github", severity="high", kind="bug",
        title="t", detail="d", dedup_key="gh-security:acme/foo",
        launch_payload=bad_payload,
    )
    result = _run(["--project-root", str(project), "list"])
    assert result.returncode == 0
    assert "\x1b" not in result.stdout
    assert "\x07" not in result.stdout
    # Visible payload content survives
    assert "/shipwright-security" in result.stdout
    assert "normal text" in result.stdout


def test_list_hides_dismissed_and_promoted_items(
    project: Path, triage_item_with_payload: str,
) -> None:
    """Only open items are listed."""
    mark_status(project, triage_item_with_payload, new_status="dismissed",
                by="x", reason="r")
    result = _run(["--project-root", str(project), "list"])
    assert result.returncode == 0
    assert "No open triage items" in result.stdout


# ---------------------------------------------------------------------------
# AC-5 — promote subcommand (positional id, AC-11 parity)
# ---------------------------------------------------------------------------

def test_promote_positional_id_happy_path(
    project: Path, triage_item_with_payload: str,
) -> None:
    result = _run([
        "--project-root", str(project),
        "promote", triage_item_with_payload,
        "--task-ref", "EXT:linear-ENG-7",
    ])
    assert result.returncode == 0, (
        f"exit {result.returncode}\nstderr: {result.stderr}\nstdout: {result.stdout}"
    )
    [item] = read_all_items(project)
    assert item["status"] == "promoted"
    assert item["promotedTaskId"] == "EXT:linear-ENG-7"
    assert item["statusBy"] == "cli"


def test_promote_exits_2_on_missing_task_ref(
    project: Path, triage_item_with_payload: str,
) -> None:
    """argparse rejects missing required option."""
    result = _run([
        "--project-root", str(project),
        "promote", triage_item_with_payload,
    ])
    assert result.returncode == 2
    assert "task-ref" in result.stderr or "task_ref" in result.stderr


def test_promote_exits_2_on_unknown_id(project: Path) -> None:
    """Unknown id → exit 2 with helpful error per AC-5d."""
    append_triage_item(
        project, source="phaseQuality", severity="low", kind="bug",
        title="t", detail="d",
    )
    result = _run([
        "--project-root", str(project),
        "promote", "trg-deadbeef", "--task-ref", "EXT:x",
    ])
    assert result.returncode == 2
    assert "not found" in result.stderr.lower()


# ---------------------------------------------------------------------------
# AC-6 — dismiss subcommand
# ---------------------------------------------------------------------------

def test_dismiss_positional_id_happy_path(
    project: Path, triage_item_with_payload: str,
) -> None:
    result = _run([
        "--project-root", str(project),
        "dismiss", triage_item_with_payload, "--reason", "notRelevant",
    ])
    assert result.returncode == 0, result.stderr
    [item] = read_all_items(project)
    assert item["status"] == "dismissed"
    assert item["statusReason"] == "notRelevant"
    assert item["statusBy"] == "cli"


def test_dismiss_exits_2_on_missing_reason(
    project: Path, triage_item_with_payload: str,
) -> None:
    result = _run([
        "--project-root", str(project),
        "dismiss", triage_item_with_payload,
    ])
    assert result.returncode == 2


def test_dismiss_exits_2_on_unknown_id(project: Path) -> None:
    append_triage_item(
        project, source="phaseQuality", severity="low", kind="bug",
        title="t", detail="d",
    )
    result = _run([
        "--project-root", str(project),
        "dismiss", "trg-deadbeef", "--reason", "notRelevant",
    ])
    assert result.returncode == 2


# ---------------------------------------------------------------------------
# AC-11 — parity with triage_promote.py
# ---------------------------------------------------------------------------

def _read_status_events(project: Path) -> list[dict]:
    path = project / ".shipwright" / TRIAGE_FILE
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line and json.loads(line).get("event") == "status"
    ]


def test_promote_parity_with_triage_promote_py(tmp_path: Path) -> None:
    """AC-11: triage_cli promote and triage_promote.py emit byte-identical
    status events except for `ts` (clock) and `by` (actor label)."""
    p1 = tmp_path / "via_old"
    p1.mkdir()
    p2 = tmp_path / "via_new"
    p2.mkdir()

    # Seed identical items in both project roots
    item_old = append_triage_item(
        p1, source="phaseQuality", severity="high", kind="bug",
        title="t", detail="d",
    )
    item_new = append_triage_item(
        p2, source="phaseQuality", severity="high", kind="bug",
        title="t", detail="d",
    )

    r1 = _run_promote([
        "--project-root", str(p1), "--id", item_old,
        "--task-ref", "EXT:foo", "--reason", "urgent",
    ])
    r2 = _run([
        "--project-root", str(p2),
        "promote", item_new, "--task-ref", "EXT:foo", "--reason", "urgent",
    ])
    assert r1.returncode == 0, f"old: {r1.stderr}"
    assert r2.returncode == 0, f"new: {r2.stderr}"

    [evt_old] = _read_status_events(p1)
    [evt_new] = _read_status_events(p2)

    for changing in ("ts", "by", "id"):
        evt_old.pop(changing, None)
        evt_new.pop(changing, None)
    assert evt_old == evt_new, (
        f"non-clock/non-actor fields must match exactly:\n"
        f"old: {evt_old}\nnew: {evt_new}"
    )


# ---------------------------------------------------------------------------
# Top-level CLI shape — argparse correctness
# ---------------------------------------------------------------------------

def test_no_subcommand_prints_help_and_exits_2(project: Path) -> None:
    result = _run(["--project-root", str(project)])
    assert result.returncode == 2
    # argparse default behavior — usage on stderr
    assert "usage" in (result.stderr + result.stdout).lower()


def test_invalid_subcommand_exits_2(project: Path) -> None:
    result = _run(["--project-root", str(project), "fix", "trg-foo"])
    assert result.returncode == 2
    assert "invalid choice" in result.stderr.lower() or \
           "fix" in result.stderr.lower()
