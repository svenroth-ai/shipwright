#!/usr/bin/env python3
"""Tests for plugin_sync_reminder_on_stop.py (SP4 Stop reminder hook).

Focus (iterate-2026-06-13-triage-not-current-work): re-syncing the plugin cache
is a **routine "do it now" maintenance step**, not a deferred follow-up — so the
hook surfaces a once-per-session Stop-block reminder (the "now" surface) and
files **NO triage item**. Triage is for genuine "later" backlog items; the board
/ events log tracks the current run. The previous durable
``source="plugin-sync"`` triage append was removed because it tracked the
current run's own work (it had accreted 19 duplicate items in the live backlog).

The reminder banner + once-per-session sentinel still key off the worktree root
(the live SDLC context). The ``test_no_triage_*`` cases are regression guards
that the append path stays gone.
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

_HOOK_PATH = (
    Path(__file__).resolve().parent.parent
    / "scripts"
    / "hooks"
    / "plugin_sync_reminder_on_stop.py"
)
_SPEC = importlib.util.spec_from_file_location(
    "plugin_sync_reminder_on_stop", _HOOK_PATH
)
psr = importlib.util.module_from_spec(_SPEC)
sys.modules["plugin_sync_reminder_on_stop"] = psr
_SPEC.loader.exec_module(psr)


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------


def _git(args: list[str], cwd: Path) -> str:
    """Run a git command in ``cwd``; return stripped stdout (raises on error)."""
    res = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=True,
    )
    return res.stdout.strip()


def _make_monorepo(root: Path) -> None:
    """Drop the monorepo marker so ``is_monorepo`` returns True for ``root``."""
    (root / "scripts").mkdir(parents=True, exist_ok=True)
    (root / "scripts" / "update-marketplace.sh").write_text(
        "#!/bin/bash\n", encoding="utf-8"
    )


def _init_monorepo_git(root: Path) -> None:
    """Init a git repo that is also a Shipwright monorepo, with one commit.

    The monorepo marker is committed so a linked worktree (a checkout of HEAD)
    also satisfies ``is_monorepo``.
    """
    root.mkdir(parents=True, exist_ok=True)
    _git(["init"], root)
    _git(["config", "user.email", "test@example.com"], root)
    _git(["config", "user.name", "Test"], root)
    _git(["config", "commit.gpgsign", "false"], root)
    _make_monorepo(root)
    _git(["add", "."], root)
    _git(["commit", "-m", "seed"], root)


def _write_marker(project_root: Path, session_id: str, rel_paths: list[str]) -> None:
    """Write the plugin-edit marker that ``mark_plugin_edit`` would have written."""
    locks = project_root / ".shipwright" / "locks"
    locks.mkdir(parents=True, exist_ok=True)
    marker = locks / f"plugin_edit_pending.{session_id}.json"
    marker.write_text(
        json.dumps({"sid": session_id, "paths": rel_paths}), encoding="utf-8"
    )


def _all_triage_appends(root: Path) -> list[dict]:
    """Every ``append`` record across BOTH triage logs under ``root``.

    Covers the tracked ``triage.jsonl`` and the gitignored
    ``triage.outbox.jsonl`` buffer, so a regression that re-introduces an
    append on EITHER channel is caught.
    """
    items: list[dict] = []
    for filename in ("triage.jsonl", "triage.outbox.jsonl"):
        path = root / ".shipwright" / filename
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("event") == "append":
                items.append(rec)
    return items


# ----------------------------------------------------------------------
# Sanity coverage
# ----------------------------------------------------------------------


def test_build_reminder_lists_paths():
    """The reminder body enumerates edited paths + the sync commands."""
    body = psr.build_reminder(["a.py", "b.py"])
    assert "a.py" in body
    assert "b.py" in body
    assert "update-marketplace.sh" in body


def test_build_reminder_does_not_mention_triage():
    """The reminder no longer claims a triage item was filed (none is)."""
    body = psr.build_reminder(["a.py"]).lower()
    assert "triage" not in body


def test_emit_triage_helper_is_gone():
    """The durable triage producer was removed at the source (AC1)."""
    assert not hasattr(psr, "_emit_triage")


def test_run_noops_outside_monorepo(tmp_path):
    """No marketplace script → not a plugin-dev monorepo → silent pass."""
    _write_marker(tmp_path, "sid", ["plugins/x/skills/x/SKILL.md"])
    assert psr.run(project_root=tmp_path, session_id="sid") == ""


def test_run_noops_without_pending_edits(tmp_path):
    """Monorepo but no marker → nothing to remind about → silent pass."""
    _make_monorepo(tmp_path)
    assert psr.run(project_root=tmp_path, session_id="sid") == ""


def test_reminder_fires_but_no_triage_non_git(tmp_path):
    """Non-git monorepo: the reminder fires; NO triage item is written (AC1)."""
    _make_monorepo(tmp_path)
    _write_marker(tmp_path, "sid", ["plugins/x/skills/x/SKILL.md"])

    out = psr.run(project_root=tmp_path, session_id="sid")

    # The "do it now" surface still fires...
    assert "PLUGIN-CACHE REMINDER" in out
    payload = json.loads(out)
    assert payload["decision"] == "block"
    # ...and nothing lands in the backlog.
    assert _all_triage_appends(tmp_path) == []


def test_reminder_fires_once_per_session(tmp_path):
    """Second Stop in the same session stays silent (block-once, never loops)."""
    _make_monorepo(tmp_path)
    _write_marker(tmp_path, "sid", ["plugins/x/skills/x/SKILL.md"])
    first = psr.run(project_root=tmp_path, session_id="sid")
    second = psr.run(project_root=tmp_path, session_id="sid")
    assert "PLUGIN-CACHE REMINDER" in first
    assert second == ""
    assert _all_triage_appends(tmp_path) == []


# ----------------------------------------------------------------------
# Integration (cross_component): real git + linked worktree, hook end-to-end
# ----------------------------------------------------------------------


def test_integration_worktree_reminder_no_triage_anywhere(tmp_path):
    """category:integration — the Stop hook composes with the triage store
    WITHOUT polluting it, end-to-end against a real git monorepo + worktree.

    Proves the hook + triage-producer machinery compose after the producer was
    removed: from inside a real linked iterate worktree, ``run()`` (a) surfaces
    the block-once reminder, (b) writes the once-per-session sentinel in the
    worktree, and (c) appends NOTHING to EITHER triage log in EITHER the
    worktree or the main repo (the durable ``resolve_main_repo_root`` redirect
    is gone with the producer).
    """
    main_root = tmp_path / "main"
    _init_monorepo_git(main_root)
    worktree_root = tmp_path / ".worktrees" / "iter-slug"
    worktree_root.parent.mkdir(parents=True, exist_ok=True)
    _git(
        ["worktree", "add", "-b", "iterate/iter-slug", str(worktree_root), "HEAD"],
        main_root,
    )

    try:
        # The worktree is the live SDLC context: the plugin-edit marker is
        # written there (read_paths reads project_root).
        _write_marker(worktree_root, "wt-sid", ["plugins/x/skills/x/SKILL.md"])

        out = psr.run(project_root=worktree_root, session_id="wt-sid")

        # The reminder banner still fires (banner is worktree-keyed)...
        assert "PLUGIN-CACHE REMINDER" in out
        # ...and the once-per-session sentinel stays in the worktree.
        assert (
            worktree_root
            / ".shipwright"
            / "locks"
            / "plugin_sync_reminded.wt-sid"
        ).exists()

        # No triage append anywhere — not the main repo, not the worktree,
        # not the tracked log, not the outbox.
        assert _all_triage_appends(main_root) == []
        assert _all_triage_appends(worktree_root) == []
    finally:
        try:
            _git(["worktree", "remove", "--force", str(worktree_root)], main_root)
        except subprocess.CalledProcessError:
            pass
