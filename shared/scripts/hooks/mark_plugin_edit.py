#!/usr/bin/env python3
"""PostToolUse hook (SP4): mark plugin-side edits for the Stop reminder.

When a Write/Edit touches a plugin-side file, record its repo-relative path in a
session marker. ``plugin_sync_reminder_on_stop.py`` reads the marker at Stop and
surfaces the ``update-marketplace.sh`` / ``check_plugin_cache_sync.py`` reminder.

This is the PostToolUse half of a PostToolUse→Stop wave, exactly analogous to
A.foundation A3's ``check_file_size.py`` (PostToolUse) + ``bloat_gate_on_stop.py``
(Stop). Registered in all 12 hooks-bearing plugins; fires per plugin per
Write|Edit, so the marker write is set-idempotent and atomic.

**Monorepo-scoped.** The cache-drift problem only exists when developing
Shipwright ITSELF, so this hook no-ops unless ``scripts/update-marketplace.sh``
is present (the monorepo marker). End-user projects — which also have a
``shipwright_run_config.json`` but no such script — never see the reminder
(CLAUDE.md: end-users "do NOT need this step").

"Plugin-side" = anything ``scripts/update-marketplace.sh`` syncs into the runtime
cache AND that the runtime loads: under ``plugins/`` or under ``shared/`` (minus
``shared/tests/``, which is not loaded at runtime), or any ``SKILL.md``. The
session id comes from the hook stdin payload (env ``SHIPWRIGHT_SESSION_ID`` is
not reliably set in Python hook processes).

Adapted-pattern: obra/superpowers writing-skills meta-skill (MIT, © Jesse
Vincent), retargeted to the Shipwright plugin-cache-drift problem.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

_MARKER_PREFIX = "plugin_edit_pending"
_MONOREPO_MARKER = ("scripts", "update-marketplace.sh")
# Fallback only — the canonical strip is bloat_baseline.strip_worktree_prefix.
_WORKTREE_PREFIX_FALLBACK = re.compile(r"^\.worktrees/[^/]+/")


def _resolve_project_root() -> Path:
    try:
        scripts_dir = str(Path(__file__).resolve().parent.parent)
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)
        from lib.project_root import resolve_project_root  # noqa: PLC0415

        return resolve_project_root()
    except (ImportError, ValueError):
        env_root = os.environ.get("SHIPWRIGHT_PROJECT_ROOT")
        return Path(env_root) if env_root else Path.cwd()


def _session_id(payload: object = None) -> str:
    if isinstance(payload, dict):
        sid = payload.get("session_id")
        if isinstance(sid, str) and sid.strip():
            return sid.strip()
    return (os.environ.get("SHIPWRIGHT_SESSION_ID") or "").strip() or "unknown"


def is_monorepo(root: Path) -> bool:
    """True only for the Shipwright plugin-dev monorepo (cache-drift applies)."""
    return (root.joinpath(*_MONOREPO_MARKER)).is_file()


def _strip_worktree_prefix(rel: str) -> str:
    """Strip a leading ``.worktrees/<slug>/`` (reuse the shared bloat helper).

    Hooks run with cwd = MAIN repo root, so ``_relativize`` yields
    ``.worktrees/<slug>/plugins/…`` for the dominant (worktree) iterate edit
    path. The sibling ``check_file_size.py`` got this strip (ADR-126); this hook
    did not (F6), so ``is_plugin_side`` saw the prefix and returned False — the
    plugin-cache-sync reminder never fired for worktree edits. Falls back to a
    local regex if the shared helper can't be imported.
    """
    try:
        scripts_dir = str(Path(__file__).resolve().parent.parent)
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)
        from lib.bloat_baseline import strip_worktree_prefix  # noqa: PLC0415

        return strip_worktree_prefix(rel)
    except (ImportError, ValueError):
        return _WORKTREE_PREFIX_FALLBACK.sub("", rel.replace("\\", "/"), count=1)


def is_plugin_side(rel: str) -> bool:
    """``True`` if a repo-relative path is synced to the runtime cache.

    Under ``plugins/`` or ``shared/`` (excluding ``shared/tests/``), or any file
    named ``SKILL.md``. A leading ``.worktrees/<slug>/`` is stripped first (F6),
    so worktree-relative edits classify identically to main-tree edits.
    """
    rel = (rel or "").replace("\\", "/").lstrip("/")
    if not rel:
        return False
    rel = _strip_worktree_prefix(rel)
    if Path(rel).name == "SKILL.md":
        return True
    if rel.startswith("plugins/"):
        return True
    if rel.startswith("shared/") and not rel.startswith("shared/tests/"):
        return True
    return False


def _relativize(file_path: str, project_root: Path) -> str | None:
    """Repo-relative POSIX path, or ``None`` if outside the project.

    Relative inputs are resolved against ``project_root`` first, so a
    ``../../escape/SKILL.md`` resolves outside the root and returns ``None``
    rather than slipping past ``is_plugin_side``.
    """
    if not file_path:
        return None
    p = Path(file_path)
    try:
        if not p.is_absolute():
            p = project_root / p
        return p.resolve().relative_to(project_root.resolve()).as_posix()
    except (ValueError, OSError):
        return None


def marker_path(project_root: Path, session_id: str) -> Path:
    return project_root / ".shipwright" / "locks" / f"{_MARKER_PREFIX}.{session_id}.json"


def read_paths(project_root: Path, session_id: str) -> list[str]:
    mp = marker_path(project_root, session_id)
    if not mp.is_file():
        return []
    try:
        doc = json.loads(mp.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    paths = doc.get("paths") if isinstance(doc, dict) else None
    return [p for p in paths if isinstance(p, str)] if isinstance(paths, list) else []


def add_path(project_root: Path, session_id: str, rel: str) -> None:
    """Append ``rel`` to the session marker (set-idempotent, atomic, best-effort).

    Atomic temp-file + ``os.replace`` so a concurrent reader never sees a torn
    file under ~12× concurrent PostToolUse firings (mirrors check_file_size.py's
    ``_atomic_write_marker``). Concurrent firings for one edit all carry the same
    ``rel`` and short-circuit on the set check, so lost updates are benign.
    """
    mp = marker_path(project_root, session_id)
    try:
        existing = read_paths(project_root, session_id)
        if rel in existing:
            return
        existing.append(rel)
        scripts_dir = str(Path(__file__).resolve().parent.parent)
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)
        from lib.atomic_write import durable_atomic_write  # noqa: PLC0415
        durable_atomic_write(mp, json.dumps({"sid": session_id, "paths": existing}))
    except OSError as exc:
        print(f"mark_plugin_edit: marker write failed ({exc!r})", file=sys.stderr)


def run(*, project_root: Path, session_id: str, file_path: str) -> bool:
    """Mark a plugin-side edit. Returns ``True`` if recorded.

    No-ops outside the Shipwright plugin-dev monorepo (``is_monorepo``).
    """
    if not is_monorepo(project_root):
        return False
    rel = _relativize(file_path, project_root)
    if rel is None or not is_plugin_side(rel):
        return False
    add_path(project_root, session_id, rel)
    return True


def _extract_file_path(payload: object) -> str:
    if not isinstance(payload, dict):
        return ""
    ti = payload.get("tool_input")
    if isinstance(ti, dict):
        fp = ti.get("file_path") or ti.get("path") or ti.get("notebook_path")
        if isinstance(fp, str):
            return fp
    return ""


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:  # noqa: BLE001
        return 0
    run(
        project_root=_resolve_project_root(),
        session_id=_session_id(payload),
        file_path=_extract_file_path(payload),
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001
        print(f"mark_plugin_edit: unexpected error ({exc!r}) — fail-open", file=sys.stderr)
        sys.exit(0)
