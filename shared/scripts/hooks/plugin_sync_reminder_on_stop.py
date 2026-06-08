#!/usr/bin/env python3
"""Stop hook (SP4): remind to re-sync the plugin cache after plugin-side edits.

Reads the session marker written by ``mark_plugin_edit.py``. If plugin-side files
were edited this session, surface a one-time reminder to run
``scripts/update-marketplace.sh`` + ``scripts/check_plugin_cache_sync.py``, AND
append an idempotent ``source="plugin-sync"`` triage item to the **durable
main-repo log** (worktree-aware — see ``_emit_triage``) so the follow-up
survives the session AND ``git worktree remove`` (mirrors the drift/audit
producers).

Design (user-confirmed 2026-05-29): **block once per session**, never
block-until-green. Block-until-green hard-loops when you've edited-but-not-pushed
or the cache is absent (CI). Block-once "surfaces a reminder" (the operative
acceptance wording) without ever bricking the agent; the triage item is the
durable handle. A ``plugin_sync_reminded.<sid>`` sentinel makes the reminder
fire exactly once even though this hook is registered in all 12 hooks-bearing
plugins. Monorepo-scoped (``mark_plugin_edit.is_monorepo``) so end-user projects
never see it. Session id comes from the hook stdin payload.

Output schema (Stop): pass-path = empty stdout; block-path = top-level
``{"decision":"block","reason":...}`` — NO ``hookSpecificOutput`` wrapper
(Stop schema, refreshed 2026-05-25; see bloat_gate_on_stop.py).
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

_HOOKS_DIR = Path(__file__).resolve().parent
if str(_HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(_HOOKS_DIR))

import mark_plugin_edit as mpe  # noqa: E402

_REMINDED_PREFIX = "plugin_sync_reminded"


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


def build_reminder(rel_paths: list[str]) -> str:
    """Compose the Stop-block reminder body."""
    sample = "\n".join(f"  - {p}" for p in rel_paths[:10])
    more = f"\n  … and {len(rel_paths) - 10} more" if len(rel_paths) > 10 else ""
    return (
        "================================================================\n"
        "  SHIPWRIGHT PLUGIN-CACHE REMINDER\n"
        "================================================================\n\n"
        "You edited plugin-side files this session:\n"
        f"{sample}{more}\n\n"
        "Changes under plugins/* and shared/* do NOT auto-sync to the runtime\n"
        "cache at ~/.claude/plugins/cache/shipwright/. Until you sync, the fixes\n"
        "land in the repo but never reach the running plugins.\n\n"
        "Before you consider this done:\n"
        "  1. git push          (the marketplace clone tracks origin/main)\n"
        "  2. bash scripts/update-marketplace.sh\n"
        "  3. uv run scripts/check_plugin_cache_sync.py --strict\n\n"
        "See shared/prompts/writing-plugin.md for the full plugin-maintenance\n"
        "checklist. This reminder fires once per session; a triage item has\n"
        "been filed so it survives. Spirit over letter.\n"
        "================================================================"
    )


def _claim_reminded(project_root: Path, session_id: str) -> bool:
    """Atomically claim the once-per-session reminder slot."""
    locks = project_root / ".shipwright" / "locks"
    try:
        locks.mkdir(parents=True, exist_ok=True)
        sentinel = locks / f"{_REMINDED_PREFIX}.{session_id}"
        fd = os.open(str(sentinel), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        os.close(fd)
        return True
    except FileExistsError:
        return False
    except OSError:
        return True  # fail-open toward reminding


def _emit_triage(project_root: Path, rel_paths: list[str]) -> None:
    """Append an idempotent plugin-sync triage item (best-effort).

    The triage backlog is a continuously-curated, repo-global follow-up store
    curated against the **main** tree (operators dismiss/promote via the WebUI;
    background producers append on main) — unlike ``events.jsonl``, a per-iterate
    work record F5b writes once per worktree. So a plugin-sync follow-up belongs
    in the durable MAIN-repo log: from inside a ``/shipwright-iterate`` worktree
    ``project_root`` is the worktree root, so the append is redirected to main
    via ``resolve_main_repo_root`` (mirrors ``tools/write_decision_drop.py``).

    NOTE (campaign ``2026-06-05-track-triage-jsonl``, C1/C2): ``triage.jsonl`` is
    now **git-tracked**, not gitignored. The redirect is an *intentional* routing
    choice for a main-tree-curated backlog — **not** a "the worktree copy is
    gitignored + discarded on cleanup" workaround (that premise is now false).

    NOTE (campaign ``2026-06-08-triage-outbox-delivery``, D1): this background
    Stop-hook producer now appends with ``to_outbox=True`` — the durable write
    lands in the GITIGNORED per-tree outbox ``.shipwright/triage.outbox.jsonl``,
    NOT the tracked log. That kills main-tree drift at its source (the tracked
    log stays clean on idle main); the D2 sweep folds the outbox into the
    iterate PR branch and GCs it. ``read_all_items`` returns tracked ∪ outbox,
    so the finding is still visible to Python consumers immediately. The
    leak-guard ignores the outbox automatically (gitignored → never in
    ``git status --porcelain``), so no ``_MAIN_TREE_WRITE_EXEMPT`` entry is
    needed for it.

    The banner + once-per-session sentinel still key off the worktree root (the
    live SDLC context); only this durable append redirects.
    ``resolve_main_repo_root`` returns ``None`` for a non-git root, so the
    ``or project_root`` fallback preserves plain-checkout / non-git behaviour.
    """
    try:
        scripts_dir = str(Path(__file__).resolve().parent.parent)
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)
        from triage import append_triage_item_idempotent  # noqa: PLC0415
        from lib.events_log import resolve_main_repo_root  # noqa: PLC0415

        triage_root = resolve_main_repo_root(project_root) or project_root

        append_triage_item_idempotent(
            triage_root,
            source="plugin-sync",
            severity="low",
            kind="maintenance",
            title="Plugin cache may be out of sync after plugin-side edits",
            detail=(
                "Plugin-side files were edited but the runtime plugin cache may "
                "not be re-synced. Run `bash scripts/update-marketplace.sh` then "
                "`uv run scripts/check_plugin_cache_sync.py --strict`. "
                f"Edited (sample): {', '.join(rel_paths[:5])}"
            ),
            dedup_key="plugin-sync:cache-drift",
            match_commit=False,
            window_seconds=None,
            to_outbox=True,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"plugin_sync_reminder: triage emit failed ({exc!r})", file=sys.stderr)


def run(*, project_root: Path, session_id: str) -> str:
    """Return the stdout string to emit (``""`` = pass / stay silent)."""
    if not mpe.is_monorepo(project_root):
        return ""
    rel_paths = mpe.read_paths(project_root, session_id)
    if not rel_paths:
        return ""
    if not _claim_reminded(project_root, session_id):
        return ""  # already reminded this session — never hard-loop
    _emit_triage(project_root, rel_paths)
    return json.dumps({"decision": "block", "reason": build_reminder(rel_paths)})


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:  # noqa: BLE001
        payload = None
    out = run(project_root=_resolve_project_root(), session_id=_session_id(payload))
    if out:
        sys.stdout.write(out + "\n")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001
        # Fail-open: never brick the agent's Stop on an unexpected error.
        print(f"plugin_sync_reminder: unexpected error ({exc!r}) — fail-open", file=sys.stderr)
        sys.exit(0)
