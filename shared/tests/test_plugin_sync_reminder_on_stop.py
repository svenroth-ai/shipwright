#!/usr/bin/env python3
"""Tests for plugin_sync_reminder_on_stop.py (SP4 Stop reminder hook).

Focus: the durable ``source="plugin-sync"`` triage item is an append-only
AUDIT trail and must survive ``git worktree remove`` after a /shipwright-iterate
PR merges. From inside an iterate worktree ``project_root`` is the worktree
root, whose ``.shipwright/triage.jsonl`` is gitignored + discarded on cleanup —
so the append is redirected to the MAIN repo via ``resolve_main_repo_root``. The
reminder banner + once-per-session sentinel still key off the worktree root.
(iterate-2026-05-31-plugin-sync-triage-main-repo)
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


def _read_triage_items(root: Path) -> list[dict]:
    """Return the ``append`` events from ``root``'s triage store (tolerant)."""
    path = root / ".shipwright" / "triage.jsonl"
    if not path.exists():
        return []
    items: list[dict] = []
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


def _plugin_sync_items(root: Path) -> list[dict]:
    """plugin-sync ``append`` items in ``root``'s triage store."""
    return [r for r in _read_triage_items(root) if r.get("source") == "plugin-sync"]


# ----------------------------------------------------------------------
# Sanity coverage
# ----------------------------------------------------------------------


def test_build_reminder_lists_paths():
    """The reminder body enumerates edited paths + the sync commands."""
    body = psr.build_reminder(["a.py", "b.py"])
    assert "a.py" in body
    assert "b.py" in body
    assert "update-marketplace.sh" in body


def test_run_noops_outside_monorepo(tmp_path):
    """No marketplace script → not a plugin-dev monorepo → silent pass."""
    _write_marker(tmp_path, "sid", ["plugins/x/skills/x/SKILL.md"])
    assert psr.run(project_root=tmp_path, session_id="sid") == ""


def test_run_noops_without_pending_edits(tmp_path):
    """Monorepo but no marker → nothing to remind about → silent pass."""
    _make_monorepo(tmp_path)
    assert psr.run(project_root=tmp_path, session_id="sid") == ""


def test_triage_item_emitted_non_git_fallback(tmp_path):
    """Non-git monorepo root: resolve_main_repo_root is None → fallback writes
    the triage item next to ``project_root`` (plain-checkout/legacy behaviour)."""
    _make_monorepo(tmp_path)
    _write_marker(tmp_path, "sid", ["plugins/x/skills/x/SKILL.md"])

    out = psr.run(project_root=tmp_path, session_id="sid")

    assert "PLUGIN-CACHE REMINDER" in out
    items = _plugin_sync_items(tmp_path)
    assert len(items) == 1
    assert items[0]["dedupKey"] == "plugin-sync:cache-drift"


# ----------------------------------------------------------------------
# Worktree-awareness regression — the durable triage item lands in MAIN repo
# ----------------------------------------------------------------------


def test_triage_item_written_to_main_repo_from_worktree(tmp_path):
    """From inside an iterate worktree, the triage item lands in the MAIN log.

    Regression guard: ``_emit_triage`` previously appended to
    ``project_root/.shipwright/triage.jsonl`` where ``project_root`` is the
    worktree root — a gitignored, throwaway log discarded by
    ``git worktree remove``. The durable audit item must instead be written to
    the main repo via ``resolve_main_repo_root``.
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

        # Durable audit item lives in the MAIN repo log...
        main_items = _plugin_sync_items(main_root)
        assert len(main_items) == 1
        assert main_items[0]["dedupKey"] == "plugin-sync:cache-drift"
        # ...and NOT in the throwaway worktree log.
        assert _plugin_sync_items(worktree_root) == []
    finally:
        try:
            _git(["worktree", "remove", "--force", str(worktree_root)], main_root)
        except subprocess.CalledProcessError:
            pass
