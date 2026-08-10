"""Tests for `triage_cli.py`'s `amend` subcommand (AC9, iterate-2026-08-08-triage-amend-event).

Human-only, via the CLI — the operator's own scoping decision. `by` is always
the fixed `cli` label; there is deliberately no `--by` flag.
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

from triage import append_triage_item, read_all_items  # noqa: E402

TRIAGE_CLI = _WORKTREE / "shared" / "scripts" / "tools" / "triage_cli.py"


def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(TRIAGE_CLI), *args],
        capture_output=True, text=True, check=False,
    )


@pytest.fixture
def project(tmp_path: Path) -> Path:
    return tmp_path


@pytest.fixture
def item_id(project: Path) -> str:
    return append_triage_item(
        project, source="manual", severity="low", kind="bug",
        title="original title", detail="original detail",
    )


def test_amend_positional_id_happy_path(project: Path, item_id: str) -> None:
    result = _run([
        "--project-root", str(project),
        "amend", item_id, "--title", "corrected title", "--severity", "critical",
    ])
    assert result.returncode == 0, (
        f"exit {result.returncode}\nstderr: {result.stderr}\nstdout: {result.stdout}"
    )
    item = next(i for i in read_all_items(project) if i["id"] == item_id)
    assert item["title"] == "corrected title"
    assert item["severity"] == "critical"
    assert item["suggestedPriority"] == "P0"
    assert item["amendedBy"] == "cli"
    assert "title" in result.stderr and "severity" in result.stderr
    # No git repo here at all, so it lands tracked — no outbox note (contrast
    # with test_amend_on_idle_main_notes_it_landed_in_the_outbox below).
    assert "buffered in the local outbox" not in result.stderr, result.stderr


def test_amend_only_a_single_field_leaves_the_rest_untouched(project: Path, item_id: str) -> None:
    result = _run(["--project-root", str(project), "amend", item_id, "--detail", "just the detail"])
    assert result.returncode == 0, result.stderr
    item = next(i for i in read_all_items(project) if i["id"] == item_id)
    assert item["detail"] == "just the detail"
    assert item["title"] == "original title"


def test_amend_exits_2_on_contentless_call(project: Path, item_id: str) -> None:
    result = _run(["--project-root", str(project), "amend", item_id])
    assert result.returncode == 2
    assert "amend must set at least one of" in result.stderr


def test_amend_exits_4_on_unknown_id(project: Path) -> None:
    append_triage_item(
        project, source="manual", severity="low", kind="bug", title="t", detail="d",
    )
    result = _run(["--project-root", str(project), "amend", "trg-deadbeef", "--title", "x"])
    assert result.returncode == 4
    assert "not found" in result.stderr.lower()


def test_amend_rejects_an_unknown_severity_via_argparse_choices(project: Path, item_id: str) -> None:
    result = _run(["--project-root", str(project), "amend", item_id, "--severity", "urgent"])
    assert result.returncode == 2
    assert "invalid choice" in result.stderr


def _git(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True, text=True)


def test_amend_on_idle_main_notes_it_landed_in_the_outbox(tmp_path: Path) -> None:
    """Stage-3 doubt review, finding 1: delivery-visibility parity for `amend`
    is deferred scope (AC15), so the CLI's own success message is the only
    signal an operator gets that a correction hasn't reached any branch yet —
    it must say so on idle main (origin + default branch), where every write
    routes to the gitignored outbox."""
    _git(["init"], tmp_path)
    _git(["config", "user.email", "t@t.t"], tmp_path)
    _git(["config", "user.name", "t"], tmp_path)
    _git(["commit", "--allow-empty", "-m", "init"], tmp_path)
    _git(["branch", "-M", "main"], tmp_path)
    _git(["remote", "add", "origin", str(tmp_path.parent / "origin-throwaway")], tmp_path)

    item_id = append_triage_item(
        tmp_path, source="manual", severity="low", kind="bug", title="t", detail="d",
    )
    result = _run(["--project-root", str(tmp_path), "amend", item_id, "--title", "corrected"])

    assert result.returncode == 0, result.stderr
    assert "buffered in the local outbox" in result.stderr, result.stderr
