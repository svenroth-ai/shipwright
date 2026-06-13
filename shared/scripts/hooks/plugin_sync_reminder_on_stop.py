#!/usr/bin/env python3
"""Stop hook (SP4): remind to re-sync the plugin cache after plugin-side edits.

Reads the session marker written by ``mark_plugin_edit.py``. If plugin-side files
were edited this session, surface a one-time reminder to run
``scripts/update-marketplace.sh`` + ``scripts/check_plugin_cache_sync.py``.

This hook files **NO triage item** (iterate-2026-06-13-triage-not-current-work).
Re-syncing the plugin cache is a *routine "do it now" maintenance step* that is
part of the current run, not a deferred "later" follow-up — and triage exists to
log things for "later" (the board / events log tracks "now"). The
once-per-session Stop-block reminder IS the "do it now" surface; a durable
backlog item only accreted noise (it had reached 19 duplicate
``source="plugin-sync"`` items in the live backlog).

Design (user-confirmed 2026-05-29): **block once per session**, never
block-until-green. Block-until-green hard-loops when you've edited-but-not-pushed
or the cache is absent (CI). Block-once "surfaces a reminder" (the operative
acceptance wording) without ever bricking the agent. A
``plugin_sync_reminded.<sid>`` sentinel makes the reminder fire exactly once even
though this hook is registered in all 12 hooks-bearing plugins. Monorepo-scoped
(``mark_plugin_edit.is_monorepo``) so end-user projects never see it. Session id
comes from the hook stdin payload.

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
        "checklist. This reminder fires once per session. Spirit over letter.\n"
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


def run(*, project_root: Path, session_id: str) -> str:
    """Return the stdout string to emit (``""`` = pass / stay silent).

    Files NO triage item — the block-once reminder IS the "do it now" surface
    (see module docstring). The plugin-cache re-sync is current-run maintenance,
    not a deferred "later" backlog item.
    """
    if not mpe.is_monorepo(project_root):
        return ""
    rel_paths = mpe.read_paths(project_root, session_id)
    if not rel_paths:
        return ""
    if not _claim_reminded(project_root, session_id):
        return ""  # already reminded this session — never hard-loop
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
