"""WP9 (2026-06-10 deep audit) — F31 control-char sanitizer + F29 outbox CLI.

F31 (SECURITY): ``_strip_control_chars`` was wired only to ``launchPayload``;
``title``/``detail`` got only ``_escape_md`` (pipe/newline). An
attacker-influenceable GitHub workflow name / branch is interpolated raw into
the action-unit title, so a terminal escape landed in ``triage_inbox.md`` and
``triage_cli list`` output (executed when an operator views it in a TTY). The
fix wires the stripper into title/detail/evidence in both render surfaces and
also strips the C1 range (0x80-0x9F) per the external plan review.

F29: ``triage_promote.promote``/``dismiss`` pre-checked only the TRACKED file,
so D1 outbox-only items (idle-main background producer appends, pre-sweep) were
listable but raised FileNotFoundError on promote/dismiss. The pre-check is
relaxed to tracked-OR-outbox (mirrors ``triage.mark_status``).

Lives in its own module to keep the existing (grandfathered / at-limit) suites
under the bloat LOC guideline.
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

from triage import (  # noqa: E402
    _append_line,
    _FileLock,
    _lock_path,
    _outbox_path,
    _triage_path,
    append_triage_item,
    read_all_items,
)
from tools.triage_promote import dismiss, promote  # noqa: E402

AGGREGATOR = _WORKTREE / "shared" / "scripts" / "tools" / "aggregate_triage.py"
TRIAGE_CLI = _WORKTREE / "shared" / "scripts" / "tools" / "triage_cli.py"
TRIAGE_MD = Path(".shipwright") / "agent_docs" / "triage_inbox.md"


@pytest.fixture
def project(tmp_path: Path) -> Path:
    return tmp_path


def _run_aggregator(project_root: Path, now: str = "2026-06-12T00:00:00Z") -> str:
    result = subprocess.run(
        [sys.executable, str(AGGREGATOR), "--project-root", str(project_root),
         "--now", now],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, (
        f"aggregator exit {result.returncode}\nstdout:{result.stdout}\nstderr:{result.stderr}"
    )
    return (project_root / TRIAGE_MD).read_text(encoding="utf-8")


def _run_cli(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(TRIAGE_CLI), *args],
        capture_output=True, text=True, check=False,
    )


# --------------------------------------------------------------------------
# F31 — title/detail/evidence control-char stripping in triage_inbox.md
# --------------------------------------------------------------------------

def test_aggregator_strips_control_chars_from_title_and_detail(project: Path) -> None:
    """C0/DEL terminal escapes in title/detail must NOT survive into the file."""
    evil_title = "Deploy \x1b[2Jcleared\x07 \x1b]2;hijack\x07branch"
    evil_detail = "from PR \x1b[31mred\x1b[0m \x07bell"
    append_triage_item(
        project, source="github", severity="high", kind="bug",
        title=evil_title, detail=evil_detail, dedup_key="gh-ci:evil",
    )
    md = _run_aggregator(project)
    assert "\x1b" not in md, "ESC survived into triage_inbox.md (title/detail)"
    assert "\x07" not in md, "BEL survived into triage_inbox.md (title/detail)"
    assert "Deploy" in md and "cleared" in md and "hijack" in md and "red" in md


def test_aggregator_strips_c1_control_chars(project: Path) -> None:
    """External plan review (Gemini HIGH): C1 controls (0x80-0x9F) include
    single-byte terminal sequences (0x9B = CSI) a TTY executes — a blanket
    'preserve >= 0x80' left the injection hole open."""
    evil_title = "Deploy \x9b2Jcsi \x84index branch"  # 0x9B CSI, 0x84 IND
    append_triage_item(
        project, source="github", severity="high", kind="bug",
        title=evil_title, detail="d\x9bmore", dedup_key="gh-ci:c1",
    )
    md = _run_aggregator(project)
    assert "\x9b" not in md, "C1 CSI survived into triage_inbox.md"
    assert "\x84" not in md, "C1 IND survived into triage_inbox.md"
    assert "Deploy" in md and "csi" in md and "branch" in md


def test_aggregator_title_detail_preserve_non_ascii(project: Path) -> None:
    """The control-char strip must NOT eat legitimate non-ASCII (>= 0xA0)."""
    append_triage_item(
        project, source="github", severity="high", kind="bug",
        title="Müller — 日本語 fix", detail="café résumé", dedup_key="gh-ci:unicode",
    )
    md = _run_aggregator(project)
    assert "Müller" in md and "日本語" in md and "café résumé" in md


# --------------------------------------------------------------------------
# F31 — title control-char stripping in `triage_cli list`
# --------------------------------------------------------------------------

def test_cli_list_strips_control_chars_from_title(project: Path) -> None:
    evil_title = "Deploy \x1b[2Jcleared\x07 \x1b]2;hijack\x07branch"
    append_triage_item(
        project, source="github", severity="high", kind="bug",
        title=evil_title, detail="d", dedup_key="gh-ci:evil",
    )
    result = _run_cli(["--project-root", str(project), "list"])
    assert result.returncode == 0, result.stderr
    assert "\x1b" not in result.stdout, "ESC survived into triage_cli list (title)"
    assert "\x07" not in result.stdout, "BEL survived into triage_cli list (title)"
    assert "Deploy" in result.stdout and "cleared" in result.stdout
    assert "hijack" in result.stdout


def test_cli_list_strips_c1_control_chars_from_title(project: Path) -> None:
    append_triage_item(
        project, source="github", severity="high", kind="bug",
        title="Deploy \x9b2Jcsi branch", detail="d", dedup_key="gh-ci:c1cli",
    )
    result = _run_cli(["--project-root", str(project), "list"])
    assert result.returncode == 0, result.stderr
    assert "\x9b" not in result.stdout, "C1 CSI survived into triage_cli list"
    assert "Deploy" in result.stdout and "branch" in result.stdout


# --------------------------------------------------------------------------
# F29 — outbox-only items promotable / dismissable (lib + CLI)
# --------------------------------------------------------------------------

def _outbox_only_item(project: Path) -> str:
    """Append to the gitignored outbox WITHOUT creating the tracked store
    (mirrors an idle-main background producer pre-sweep)."""
    item_id = append_triage_item(
        project, source="github", severity="high", kind="bug",
        title="outbox-only", detail="d", dedup_key="gh:outbox-only",
        to_outbox=True,
    )
    assert not _triage_path(project).exists()
    assert _outbox_path(project).exists()
    return item_id


def test_promote_outbox_only_item(project: Path) -> None:
    item_id = _outbox_only_item(project)
    result = promote(project, item_id=item_id, task_ref="EXT:linear-ENG-9")
    assert result["newStatus"] == "promoted"
    [item] = read_all_items(project)
    assert item["id"] == item_id and item["status"] == "promoted"
    assert item["promotedTaskId"] == "EXT:linear-ENG-9"


def test_dismiss_outbox_only_item(project: Path) -> None:
    item_id = _outbox_only_item(project)
    result = dismiss(project, item_id=item_id, reason="notRelevant")
    assert result["newStatus"] == "dismissed"
    [item] = read_all_items(project)
    assert item["id"] == item_id and item["status"] == "dismissed"
    assert item["statusReason"] == "notRelevant"


def test_promote_still_raises_filenotfound_when_neither_store_exists(project: Path) -> None:
    """The relaxed pre-check must still fail when NEITHER store exists."""
    with pytest.raises(FileNotFoundError):
        promote(project, item_id="trg-12345678", task_ref="EXT:x")


def test_dismiss_still_raises_filenotfound_when_neither_store_exists(project: Path) -> None:
    with pytest.raises(FileNotFoundError):
        dismiss(project, item_id="trg-12345678", reason="x")


def test_promote_outbox_only_unknown_id_raises_keyerror(project: Path) -> None:
    """Outbox exists but the id isn't in it → KeyError, not FileNotFoundError."""
    _outbox_only_item(project)
    with pytest.raises(KeyError):
        promote(project, item_id="trg-deadbeef", task_ref="EXT:x")


def test_promote_id_present_only_in_tracked_with_outbox_present(project: Path) -> None:
    """Lookup matrix (external review): both stores exist, id ONLY in tracked.
    Promote must still resolve it (no regression of the tracked-only path)."""
    append_triage_item(
        project, source="github", severity="low", kind="bug",
        title="bg-outbox", detail="d", dedup_key="gh:bg", to_outbox=True,
    )
    tracked_id = append_triage_item(
        project, source="phaseQuality", severity="high", kind="bug",
        title="tracked", detail="d",
    )
    assert promote(project, item_id=tracked_id, task_ref="EXT:t-1")["newStatus"] == "promoted"


def test_promote_dual_presence_resolves_via_mark_status(project: Path) -> None:
    """Dual-presence (external review): the SAME id in BOTH stores must promote
    following the residence/precedence the library contract (mark_status)
    defines — promote delegates the write, so no new precedence here."""
    import json as _json

    item_id = append_triage_item(
        project, source="github", severity="high", kind="bug",
        title="dual", detail="d", dedup_key="gh:dual",
    )
    tracked_lines = _triage_path(project).read_text(encoding="utf-8").splitlines()
    append_line = next(
        ln for ln in tracked_lines
        if ln.strip() and _json.loads(ln).get("event") == "append"
    )
    with _FileLock(_lock_path(project)):
        _append_line(project, append_line + "\n", to_outbox=True)
    result = promote(project, item_id=item_id, task_ref="EXT:dual-1")
    assert result["newStatus"] == "promoted"
    items = [it for it in read_all_items(project) if it.get("id") == item_id]
    assert len(items) == 1 and items[0]["status"] == "promoted"


def test_cli_promote_outbox_only_item(project: Path) -> None:
    item_id = _outbox_only_item(project)
    result = _run_cli(["--project-root", str(project), "promote", item_id,
                       "--task-ref", "EXT:linear-ENG-9"])
    assert result.returncode == 0, (
        f"exit {result.returncode}\nstderr: {result.stderr}\nstdout: {result.stdout}"
    )
    [item] = read_all_items(project)
    assert item["status"] == "promoted" and item["promotedTaskId"] == "EXT:linear-ENG-9"


def test_cli_dismiss_outbox_only_item(project: Path) -> None:
    item_id = _outbox_only_item(project)
    result = _run_cli(["--project-root", str(project), "dismiss", item_id,
                       "--reason", "notRelevant"])
    assert result.returncode == 0, result.stderr
    [item] = read_all_items(project)
    assert item["status"] == "dismissed" and item["statusReason"] == "notRelevant"
