"""Fail-open guard for the compliance PreToolUse ``Bash`` gates.

A PreToolUse ``Bash`` hook fires on EVERY Bash tool call. If the hook *process*
raises an unhandled exception, Claude Code treats the non-zero exit as a block
and the unrelated Bash call (``git add``, a test run, a file read) is
hard-blocked — even though the gate only ever intends to soft-block a deploy /
commit. A crashing *check* must never hard-block work, so both gates route their
entrypoint through :func:`run_failopen`: any unexpected exception is logged
(best-effort) and the hook returns ``0`` (ALLOW).

The deliberate soft-block is the hook's normal ``return 2`` — a value, not an
exception — so it passes through :func:`run_failopen` untouched.

The diagnostic log lives in the **gitignored** ``runtime/`` subdir
(``.shipwright/agent_docs/runtime/hook_errors.log``), NOT beside the tracked
``compliance_overrides.log``: it is high-churn operator diagnostics, never an
audit artifact.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable


def _resolve_log_root(project_root: str | Path | None) -> Path:
    """Best-effort project root for the diagnostic log. Never raises.

    Honors an explicit *project_root*, else ``SHIPWRIGHT_PROJECT_ROOT``, else
    cwd. Deliberately simple and defensive — this runs on the failure path, so
    it must not itself fail (resolving via the full ``lib.project_root`` chain
    could be the very thing that raised)."""
    try:
        if project_root:
            return Path(project_root)
        env = os.environ.get("SHIPWRIGHT_PROJECT_ROOT", "").strip()
        if env:
            return Path(env)
        return Path.cwd()
    except Exception:
        return Path(".")


def log_hook_error(
    hook_name: str,
    exc: BaseException,
    *,
    project_root: str | Path | None = None,
) -> None:
    """Append a one-line FAILOPEN diagnostic to the runtime hook-error log.

    Best-effort: ANY failure here is swallowed. Logging must never re-raise, or
    it would defeat the fail-open guarantee it exists to support.
    """
    try:
        log_dir = _resolve_log_root(project_root) / ".shipwright" / "agent_docs" / "runtime"
        log_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).isoformat()
        summary = repr(exc).replace("\n", " ").replace("\r", " ")[:300]
        line = f"[{ts}] FAILOPEN hook={hook_name} error={summary}\n"
        with open(log_dir / "hook_errors.log", "a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        # Diagnostics are non-essential; the gate must allow regardless.
        pass


def run_failopen(
    hook_name: str,
    main_fn: Callable[[], int],
    *,
    project_root: str | Path | None = None,
) -> int:
    """Run a hook ``main()`` with fail-open semantics.

    Returns ``main_fn()``'s int result (0 = allow, 2 = deliberate soft-block).
    On ANY unexpected :class:`Exception`, logs a warning and returns ``0`` so a
    crashing gate never hard-blocks an unrelated Bash call. A non-int return is
    coerced to ``0`` (allow) defensively.
    """
    try:
        rc = main_fn()
        return rc if isinstance(rc, int) else 0
    except Exception as exc:
        log_hook_error(hook_name, exc, project_root=project_root)
        return 0
