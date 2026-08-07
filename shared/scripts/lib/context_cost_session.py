"""Session/worktree resolution for the context-cost meter's writer + readers.

Split out of ``context_cost_core.py``, which had reached its 300-LOC ceiling
(same reasoning as ``phase_quality/_run_id.py``'s split out of
``_resolution.py``: a one-way, acyclic edge — this module has no dependency
back on ``context_cost_core``). ``context_cost_core`` re-exports both names,
so every existing ``context_cost_core.resolve_session_id`` /
``.resolve_active_project_root`` caller is unchanged.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

__all__ = ["resolve_session_id", "resolve_active_project_root"]


def resolve_session_id(payload: dict | None = None) -> str | None:
    """Per-session key for a hook/statusline subprocess (payload → env → None).

    Payload's ``session_id`` first, ``SHIPWRIGHT_SESSION_ID`` only as
    fallback — the OPPOSITE precedence from a plain Bash-tool-invoked script
    (``finalize_iterate.py``, ``estimate_context_pressure.py``), which has no
    stdin payload at all and uses the env var directly. A subprocess Claude
    Code spawns directly for a ``Stop`` or ``statusLine.command`` firing does
    NOT reliably inherit that env var — only a child of the assistant's own
    Bash tool does, via ``CLAUDE_ENV_FILE`` (see ``capture_session_id.py``).
    This is the documented, already-once-fixed failure class in
    ``bloat_gate_on_stop.py``'s own ``_session_id`` docstring: env-first
    pooled every session into one shared ``*.unknown.json`` file (fixed
    2026-05-29) because the env var was unset in that exact process class.
    Every writer/reader sharing this process class (the ``Stop`` hook and the
    statusline) must call this same function so they can never diverge.

    Returns ``None``, not a literal placeholder string, when NEITHER source
    has a real id — a fixed fallback like ``"unknown"`` would reintroduce
    that exact pooling bug for every caller that happens to hit this branch
    simultaneously, in the precise unreliable-hook-environment case this
    whole payload-first design exists to route around (external-review
    finding, iterate-2026-08-07-context-cost-meter). Every caller of this
    function already treats a falsy session id as "skip" — the writer's
    ``session_summary_path`` returns ``None`` for a non-string id, and the
    statusline/summary readers degrade to their no-data placeholder — so
    ``None`` here composes with existing guards rather than needing new ones.
    """
    if isinstance(payload, dict):
        sid = payload.get("session_id")
        if isinstance(sid, str) and sid.strip():
            return sid.strip()
    sid = (os.environ.get("SHIPWRIGHT_SESSION_ID") or "").strip()
    return sid or None


def resolve_active_project_root(cwd: Path, session_id: str | None) -> Path:
    """Prefer this session's active iterate worktree, else the normal resolver.

    A ``Stop``-subprocess's cwd is the MAIN repo even while an iterate runs
    in a linked worktree (``iterate_stop_finalize.py``'s own
    ``_active_worktree_root`` docstring), and ``SHIPWRIGHT_PROJECT_ROOT``
    never reaches this process class (``capture_session_id.py`` writes only
    ``SHIPWRIGHT_SESSION_ID`` into ``CLAUDE_ENV_FILE``). Without checking the
    per-session run pointer first, ``track_context_cost.py`` would write to
    ``<main>/.shipwright/compliance/context-cost/`` while ``finalize_iterate.
    py``'s F5b fold reads from the run's WORKTREE (B1a: ``{project_root}``
    for the rest of the run is the worktree the setup helper returned) —
    missing every write silently (doubt-review finding,
    iterate-2026-08-07-context-cost-meter).

    Same validation as ``iterate_stop_finalize._active_worktree_root``
    (pointer resolves to a live directory, contained under the main repo,
    with a ``.git`` entry) so a poisoned or stale pointer can never redirect
    this write to an unrelated tree — deliberately re-checked here rather
    than imported, since that function lives in a plugin-specific hook file
    and this is a shared, plugin-agnostic module.
    """
    if session_id:
        try:
            from lib.worktree_isolation import main_repo_root, read_run_pointer  # noqa: PLC0415

            main_root = main_repo_root(cwd)
            pointer = read_run_pointer(main_root, session_id) or {}
            worktree_str = pointer.get("worktree_path", "")
            if worktree_str:
                worktree = Path(worktree_str).resolve()
                if worktree.is_dir() and (worktree / ".git").exists():
                    worktree.relative_to(main_root.resolve())  # containment guard
                    return worktree
        except Exception:  # noqa: BLE001 — best-effort, falls through below
            pass
    try:
        from lib.project_root import resolve_project_root  # noqa: PLC0415

        return resolve_project_root()
    except ValueError:
        return cwd
