#!/usr/bin/env python3
"""Resolve ``(project_root, session_id)`` for the multi-session phase hooks.

The v2 phase-session hooks — ``phase_session_start`` / ``phase_session_stop`` /
``phase_user_prompt_validate`` — historically read ``SHIPWRIGHT_PROJECT_ROOT`` /
``SHIPWRIGHT_SESSION_ID`` from process env vars that **no launcher ever sets**.
The run launch card is a bare ``claude --session-id … '/<phase>'`` with no env
exports, and ``capture_session_id`` emits ``PROJECT_ROOT`` only as
``additionalContext`` text + writes ``SESSION_ID`` to ``CLAUDE_ENV_FILE`` —
neither reaches a sibling hook's ``os.environ`` (ADR-092/097 recorded the same
platform fact for the bloat + bootstrap hooks). The whole v2 claim/validate/
complete lifecycle therefore silently no-op'd (deep-audit 2026-06-10 F1).

This module follows the bloat/bootstrap hooks: resolve identity from the hook
**stdin payload** (which always carries ``session_id`` + ``cwd``) with a
``resolve_project_root()`` fallback. It additionally consults the payload ``cwd``
directly (``capture_session_id`` calls bare ``resolve_project_root()``) because a
hook's process cwd is the dir Claude launched in. It is the single tested unit the
three hooks share so the resolution can't drift between them.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Optional

# shared/scripts on sys.path so ``lib.project_root`` resolves regardless of the
# importing hook's own path wiring (this file lives at shared/scripts/lib/).
_SHARED_SCRIPTS = Path(__file__).resolve().parents[1]  # shared/scripts
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

from lib.project_root import is_shipwright_project, resolve_project_root  # noqa: E402


def read_hook_payload(stream=None) -> dict:
    """Read + parse the hook's stdin JSON payload. Returns ``{}`` on any error.

    Never raises — a hook must degrade to standalone, not crash session
    shutdown/startup. A non-object payload (array / scalar) is treated as empty.
    """
    stream = sys.stdin if stream is None else stream
    try:
        raw = stream.read()
    except (OSError, ValueError):
        return {}
    if not raw or not str(raw).strip():
        return {}
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def resolve_session_id(payload: dict) -> Optional[str]:
    """Session id from the payload (canonical), env fallback, else ``None``.

    ``session_id`` is present on every Claude Code hook event; the
    ``SHIPWRIGHT_SESSION_ID`` env fallback covers an explicitly-exported run.
    """
    if isinstance(payload, dict):
        sid = payload.get("session_id")
        if isinstance(sid, str) and sid.strip():
            return sid.strip()
    env = (os.environ.get("SHIPWRIGHT_SESSION_ID") or "").strip()
    return env or None


def resolve_project_root_from_payload(payload: dict) -> Optional[Path]:
    """Resolve the Shipwright project root for a phase hook.

    Priority:
      1. ``SHIPWRIGHT_PROJECT_ROOT`` env var, when it points at a real Shipwright
         project (explicit override / back-compat).
      2. The payload's ``cwd`` (Claude Code's working dir), when it is itself a
         Shipwright project — the launch card runs ``claude`` from the project
         root, so this is the common path once the env vars are gone.
      3. ``resolve_project_root()`` — env → ``Path.cwd()`` → single managed
         subdir (monorepo-subdir layout). An ambiguous multi-project parent
         raises ``ValueError`` there → ``None`` here (degrade to standalone,
         never crash the hook).

    Note ``resolve_project_root`` returns ``Path.cwd()`` as a last resort, so a
    non-project cwd still yields a *path*; the calling hook then no-ops because
    ``shipwright_run_config.json`` is absent there. ``None`` is returned only
    when the resolver itself raised on ambiguity.
    """
    # 1. Explicit env override (only honoured if it is a real project). This
    #    trusts the env over the live payload cwd — matching resolve_project_root's
    #    framework-wide precedence; a stale var pointing at a *different* managed
    #    project is defused downstream because its phase_tasks[] won't carry this
    #    session's UUID (→ standalone).
    env_val = (os.environ.get("SHIPWRIGHT_PROJECT_ROOT") or "").strip()
    if env_val:
        p = Path(env_val)
        if p.is_dir() and is_shipwright_project(p):
            return p.resolve()
    # 2. Payload cwd, if it is a Shipwright project.
    if isinstance(payload, dict):
        cwd = payload.get("cwd")
        if isinstance(cwd, str) and cwd.strip():
            p = Path(cwd.strip())
            if p.is_dir() and is_shipwright_project(p):
                return p.resolve()
    # 3. Resolver fallback (env → Path.cwd() → single managed subdir).
    try:
        return resolve_project_root()
    except ValueError:
        return None


def resolve_hook_context(stream=None):
    """Read the hook stdin payload and resolve ``(project_root, session_id)``.

    The single entrypoint each phase hook calls from ``main()``. Returns
    ``(project_root_or_None, session_id_or_None)``; the hooks treat either
    ``None`` as standalone and exit 0.
    """
    payload = read_hook_payload(stream)
    return (
        resolve_project_root_from_payload(payload),
        resolve_session_id(payload),
    )
