"""Tests for triage_add.py's --launch-payload / --no-launch-payload surface.

iterate-2026-08-05-triage-launch-payload-cli. Split out of
test_triage_add_cli.py (bloat baseline) — see that file for the rest of
triage_add.py's coverage (--fr-id, general validation, schema parity).

Covers:
- _resolve_launch_payload pure-helper: default / override / opt-out / blank-rejection
- CLI-level: default applied + stderr note, explicit override, --no-launch-payload
  opt-out, mutual exclusion (argparse exit 2), blank rejection (exit 1)
- Every CLI-level case round-trips through read_all_items, not just stdout JSON
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# Wire up shared/scripts so triage_add can be imported as a module.
_SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from tools import triage_add  # noqa: E402
from triage import read_all_items  # noqa: E402


# ---------------------------------------------------------------------------
# Pure helper: _resolve_launch_payload
# ---------------------------------------------------------------------------


def test_resolve_launch_payload_defaults_when_omitted():
    """Omitting both flags → the manual-card default, used_default=True."""
    value, used_default = triage_add._resolve_launch_payload(
        None, no_launch_payload=False
    )
    assert value == triage_add.DEFAULT_LAUNCH_PAYLOAD
    assert used_default is True


def test_resolve_launch_payload_explicit_value_overrides_default():
    """--launch-payload VALUE wins verbatim; used_default=False."""
    value, used_default = triage_add._resolve_launch_payload(
        "/shipwright-security", no_launch_payload=False
    )
    assert value == "/shipwright-security"
    assert used_default is False


def test_resolve_launch_payload_no_launch_payload_forces_none():
    """--no-launch-payload → None regardless of the manual-card default."""
    value, used_default = triage_add._resolve_launch_payload(
        None, no_launch_payload=True
    )
    assert value is None
    assert used_default is False


def test_resolve_launch_payload_rejects_blank():
    """A blank --launch-payload is ambiguous with 'no payload' — rejected.

    The operator must say --no-launch-payload instead, so a card with
    genuinely no launch command stays distinguishable from a typo.
    """
    with pytest.raises(ValueError, match="--no-launch-payload"):
        triage_add._resolve_launch_payload("   ", no_launch_payload=False)
    with pytest.raises(ValueError, match="--no-launch-payload"):
        triage_add._resolve_launch_payload("", no_launch_payload=False)


# ---------------------------------------------------------------------------
# CLI level
# ---------------------------------------------------------------------------


def test_main_defaults_launch_payload_when_omitted(tmp_path: Path, capsys: pytest.CaptureFixture):
    """Omitting --launch-payload/--no-launch-payload → the manual-card default.

    Nearly every board item is later worked via /shipwright-iterate, so the
    default is explicit (a documented constant + a printed note) rather than
    silently leaving `launchPayload` null the way every card produced by
    this CLI did before this fix.
    """
    project_root = tmp_path
    (project_root / ".shipwright").mkdir()

    exit_code = triage_add.main([
        "--project-root", str(project_root),
        "--title", "Manual card, no launch payload given",
        "--detail", "...",
        "--severity", "medium",
        "--kind", "improvement",
        "--source", "manual",
    ])

    assert exit_code == 0
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["launchPayload"] == triage_add.DEFAULT_LAUNCH_PAYLOAD
    # Explicit-not-silent: the operator is told a default was applied.
    assert "defaulting to" in captured.err

    items = read_all_items(project_root)
    assert items[0]["launchPayload"] == triage_add.DEFAULT_LAUNCH_PAYLOAD


def test_main_launch_payload_override(tmp_path: Path, capsys: pytest.CaptureFixture):
    """--launch-payload VALUE persists verbatim and skips the default note."""
    project_root = tmp_path
    (project_root / ".shipwright").mkdir()

    exit_code = triage_add.main([
        "--project-root", str(project_root),
        "--title", "Manual card with explicit payload",
        "--detail", "...",
        "--severity", "high",
        "--kind", "bug",
        "--source", "manual",
        "--launch-payload", "/shipwright-security",
    ])

    assert exit_code == 0
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["launchPayload"] == "/shipwright-security"
    assert "defaulting to" not in captured.err

    items = read_all_items(project_root)
    assert items[0]["launchPayload"] == "/shipwright-security"


def test_main_no_launch_payload_flag_persists_null(tmp_path: Path, capsys: pytest.CaptureFixture):
    """--no-launch-payload skips the default; card stays legal, launchPayload=None."""
    project_root = tmp_path
    (project_root / ".shipwright").mkdir()

    exit_code = triage_add.main([
        "--project-root", str(project_root),
        "--title", "Manual card with no sensible launch command",
        "--detail", "...",
        "--severity", "low",
        "--kind", "compliance",
        "--source", "manual",
        "--no-launch-payload",
    ])

    assert exit_code == 0
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["launchPayload"] is None
    assert "defaulting to" not in captured.err

    items = read_all_items(project_root)
    assert items[0]["launchPayload"] is None


def test_main_launch_payload_and_no_launch_payload_are_mutually_exclusive(tmp_path: Path):
    """Passing both flags together is an argparse error (exit 2), nothing written."""
    project_root = tmp_path
    (project_root / ".shipwright").mkdir()

    with pytest.raises(SystemExit) as exc_info:
        triage_add.main([
            "--project-root", str(project_root),
            "--title", "conflicting flags",
            "--severity", "low",
            "--kind", "bug",
            "--source", "manual",
            "--launch-payload", "/shipwright-security",
            "--no-launch-payload",
        ])
    assert exc_info.value.code == 2
    assert read_all_items(project_root) == []


def test_main_rejects_blank_launch_payload(tmp_path: Path, capsys: pytest.CaptureFixture):
    """--launch-payload '   ' is ambiguous with 'no payload' — rejected, nothing written."""
    project_root = tmp_path
    (project_root / ".shipwright").mkdir()

    exit_code = triage_add.main([
        "--project-root", str(project_root),
        "--title", "Should not be written",
        "--severity", "high",
        "--kind", "bug",
        "--source", "manual",
        "--launch-payload", "   ",
    ])

    assert exit_code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["success"] is False
    assert payload["error"] == "invalid_launch_payload"

    items = read_all_items(project_root)
    assert items == []
