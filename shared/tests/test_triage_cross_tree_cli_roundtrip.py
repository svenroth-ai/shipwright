"""Cross-tree decision visibility, through the real `triage_cli.py` subprocess.

Split out of `test_triage_cross_tree_delivery.py` (which covers the library
functions directly) once that file crossed 300 lines — these two tests drive
the **real writers' file shapes** into **real files**, then run the CLI as a
subprocess and parse its stdout, exactly like `test_triage_delivery_roundtrip.py`
does for the outbox case this module extends. See `lib.triage_cross_tree` for
what is under test and why.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

_SHARED = Path(__file__).resolve().parents[1]
_SCRIPTS = _SHARED / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

_CLI = _SCRIPTS / "tools" / "triage_cli.py"


def _j(obj: dict) -> str:
    return json.dumps(obj, separators=(",", ":"))


def _run_cli(project: Path, *args: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(_SCRIPTS)
    return subprocess.run(
        [sys.executable, str(_CLI), "--project-root", str(project), "list", *args],
        capture_output=True, text=True, timeout=120, env=env,
    )


def _make_main(tmp_path: Path) -> Path:
    """A main tree: `.shipwright/` present, `.git` a DIRECTORY (not a file)."""
    main = tmp_path / "main"
    (main / ".shipwright").mkdir(parents=True)
    (main / ".git").mkdir()
    return main


def _make_worktree(main: Path, slug: str, branch: str) -> Path:
    """A linked worktree under `main/.worktrees/<slug>`: `.git` is a FILE naming
    an admin dir whose `HEAD` names `branch` — the real git worktree shape,
    reproduced without an actual git process."""
    wt = main / ".worktrees" / slug
    (wt / ".shipwright").mkdir(parents=True)
    admin = main / ".git" / "worktrees" / slug
    admin.mkdir(parents=True)
    (admin / "HEAD").write_text(f"ref: refs/heads/{branch}\n", encoding="utf-8")
    (wt / ".git").write_text(f"gitdir: {admin}\n", encoding="utf-8")
    return wt


_APPEND = {
    "event": "append", "id": "trg-good0001", "ts": "2026-01-01T00:00:00Z",
    "title": "t", "status": "triage", "severity": "low", "kind": "bug",
    "source": "manual", "detail": "d",
}
_DISMISS = {
    "event": "status", "id": "trg-good0001", "ts": "2026-01-02T00:00:00Z",
    "newStatus": "dismissed", "by": "cli", "reason": "done",
}


def test_cli_list_json_marks_the_item_pending_and_names_the_branch(
    tmp_path: Path,
) -> None:
    main = _make_main(tmp_path)
    (main / ".shipwright" / "triage.jsonl").write_text(
        _j({"v": 1}) + "\n" + _j(_APPEND) + "\n", encoding="utf-8")
    _make_worktree(main, "camp-a", "iterate/camp-a")
    (main / ".worktrees" / "camp-a" / ".shipwright" / "triage.jsonl").write_text(
        _j({"v": 1}) + "\n" + _j(_APPEND) + "\n" + _j(_DISMISS) + "\n",
        encoding="utf-8")

    result = _run_cli(main, "--json")
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)

    # The item is TERMINAL (dismissed), so it is in neither `open` nor
    # `deferred` — a per-row-only branch would repeat the exact "terminal
    # item invisible" defect `undeliveredDecisions` exists to close. The
    # envelope itself must name the branch, not only the human notice.
    assert all(r["id"] != "trg-good0001" for r in payload["open"])
    assert payload["undeliveredDecisions"]["ids"] == ["trg-good0001"]
    assert payload["undeliveredDecisions"]["originBranches"] == {
        "trg-good0001": "iterate/camp-a"}

    human = _run_cli(main)
    assert "trg-good0001" in human.stdout
    assert "iterate/camp-a" in human.stdout
    assert "not committed to any branch yet" in human.stdout
    assert "reached origin" not in human.stdout


def test_cli_list_json_says_plain_dismissed_once_delivered_to_main(
    tmp_path: Path,
) -> None:
    """The report's second test: fully delivered reads clean, no pending marker."""
    main = _make_main(tmp_path)
    (main / ".shipwright" / "triage.jsonl").write_text(
        _j({"v": 1}) + "\n" + _j(_APPEND) + "\n" + _j(_DISMISS) + "\n",
        encoding="utf-8")
    _make_worktree(main, "camp-a", "iterate/camp-a")
    (main / ".worktrees" / "camp-a" / ".shipwright" / "triage.jsonl").write_text(
        _j({"v": 1}) + "\n" + _j(_APPEND) + "\n" + _j(_DISMISS) + "\n",
        encoding="utf-8")

    payload = json.loads(_run_cli(main, "--json").stdout)
    assert payload["undeliveredDecisions"] == {
        "count": 0, "truncated": False, "ids": [], "originBranches": {}}

    human = _run_cli(main)
    assert "not committed to any branch" not in human.stdout
