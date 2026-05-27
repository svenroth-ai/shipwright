#!/usr/bin/env python3
"""Iterate Stop hook — runs shared handoff + finalize_iterate as fallback.

Delegates to the shared generate_handoff_on_stop first (preserving
canon-marker skip logic from iterate 12.1), then checks whether
finalize_iterate already ran during this session.  If not, runs it as
a repair pass.

This hook imports modules directly (no subprocess) to avoid stdin
payload forwarding issues (external review Finding 7).
"""

from __future__ import annotations

import io
import json
import os
import sys
from pathlib import Path

def _find_shared_scripts() -> Path:
    """Locate shared/scripts/ by walking up — robust to plugin-layout depth.

    Replaces a hardcoded ``parents[4]`` that silently broke on any change to
    the plugin directory nesting.
    """
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "shared" / "scripts"
        if candidate.is_dir():
            return candidate
    return here.parents[4] / "shared" / "scripts"  # historical fallback


_SHARED_SCRIPTS = _find_shared_scripts()
sys.path.insert(0, str(_SHARED_SCRIPTS))


def _get_latest_run_id(project_root: Path) -> str | None:
    """Return the most recent iterate run_id, or None if no history exists.

    Reads from the merged legacy-array + file-per-iterate store via
    ``lib.iterate_entry.last_iterate_entry``. Falling back silently when
    the store is missing (fresh project, pre-adopt repo) is intentional —
    this function feeds a freshness gate and must never crash.
    """
    try:
        from lib.iterate_entry import last_iterate_entry

        entry = last_iterate_entry(project_root)
    except Exception:
        return None
    if not entry:
        return None
    run_id = entry.get("run_id")
    return run_id if isinstance(run_id, str) else None


def _dashboard_reflects_run_id(project_root: Path, run_id: str) -> bool:
    """Check if build_dashboard.md already contains the current run_id."""
    dashboard = project_root / ".shipwright" / "agent_docs" / "build_dashboard.md"
    if not dashboard.exists():
        return False
    try:
        return run_id in dashboard.read_text(encoding="utf-8")
    except OSError:
        return False


def _active_worktree_root(cwd: Path, session_id: str) -> Path | None:
    """Worktree path of this session's active iterate run, or None.

    The Stop hook runs with cwd at the main repo; an iterate run executes in
    a linked worktree under ``.worktrees/<slug>/``. The per-session run
    pointer written by ``setup_iterate_worktree.py`` maps session_id →
    worktree. Without this, a fallback finalize here would write into the
    main tree — and the leak-guard of any concurrent iterate run would then
    flag a false leak.

    Validation (external review OpenAI #7,
    iterate-2026-05-27-tracked-artifacts-single-producer-and-finalize-sandbox):

    * Pointer must exist and resolve to a directory.
    * Resolved path must be UNDER the main repo's worktree root (rejects
      foreign repos / absolute paths to other clones).
    * Path must be a `.git`-bearing directory (a real worktree).

    Best-effort: returns None on any resolution failure or validation miss.
    """
    if not session_id:
        return None
    try:
        from lib.worktree_isolation import main_repo_root, read_run_pointer

        main_root = main_repo_root(cwd)
        pointer = read_run_pointer(main_root, session_id)
    except Exception:
        return None
    if not pointer:
        return None
    worktree_str = pointer.get("worktree_path", "")
    if not worktree_str:
        return None
    try:
        worktree = Path(worktree_str).resolve()
    except (OSError, RuntimeError):
        return None
    if not worktree.is_dir():
        return None
    # Containment guard: resolved worktree must live under main_root so a
    # poisoned pointer cannot redirect finalize to an unrelated tree.
    try:
        main_root_resolved = main_root.resolve()
        worktree.relative_to(main_root_resolved)
    except (ValueError, OSError):
        return None
    # Must look like a worktree (has a `.git` file/dir).
    if not (worktree / ".git").exists():
        return None
    return worktree


def main() -> int:
    # Consume stdin (hook protocol)
    try:
        json.load(sys.stdin)
    except Exception:
        pass

    # 0. Worktree-aware finalization. Point every downstream resolver at the
    #    active iterate worktree (if any) so a fallback finalize never
    #    dirties the main tree. SHIPWRIGHT_PROJECT_ROOT is honored by
    #    lib.project_root.resolve_project_root.
    #
    #    Resolved worktree is captured into a local so the repair-pass
    #    gate (step 4) can refuse to run when this resolution failed —
    #    the legacy fallback to cwd silently routed finalize writes into
    #    the main tree, bypassing the PR #78 single-producer guarantee
    #    (iterate-2026-05-27-tracked-artifacts-single-producer-and-finalize-sandbox).
    worktree: Path | None = None
    try:
        worktree = _active_worktree_root(
            Path.cwd(), os.environ.get("SHIPWRIGHT_SESSION_ID", "")
        )
        if worktree is not None:
            os.environ["SHIPWRIGHT_PROJECT_ROOT"] = str(worktree)
    except Exception:
        pass

    # 1. Run the shared handoff-on-stop (same as all other plugins)
    try:
        from hooks.generate_handoff_on_stop import main as handoff_main
        # Re-feed empty stdin since we consumed it
        original_stdin = sys.stdin
        sys.stdin = open(os.devnull) if os.name != "nt" else io.StringIO("{}")
        try:
            handoff_main()
        finally:
            sys.stdin = original_stdin
    except Exception as exc:
        print(f"[iterate_stop_finalize] handoff failed: {exc}", file=sys.stderr)

    # 2. Resolve project root
    try:
        from lib.project_root import resolve_project_root
        project_root = resolve_project_root()
    except (ImportError, ValueError):
        return 0

    # 3. Freshness gate — skip if finalize_iterate already ran
    run_id = _get_latest_run_id(project_root)
    if not run_id:
        return 0

    if _dashboard_reflects_run_id(project_root, run_id):
        return 0

    # 4. Repair pass — finalize_iterate was not run during this session.
    #    HARD GATE (iterate-2026-05-27): refuse the repair pass when no
    #    valid worktree pointer exists for this session. cwd at Stop-time
    #    is the main repo; running finalize against main would write the
    #    8 tracked compliance + agent-doc MDs in the wrong tree, bypassing
    #    the single-producer guarantee (PR #78). Steps 1-3 above are safe
    #    (handoff writes to runtime/, project_root resolution is a read,
    #    freshness gate is a read). Step 4 is the LAST step before
    #    return 0 — audited 2026-05-27 — so an early return here only
    #    skips the dangerous finalize call.
    if worktree is None:
        print(
            "[iterate_stop_finalize] no valid iterate worktree pointer for "
            f"session {os.environ.get('SHIPWRIGHT_SESSION_ID', '?')!r} "
            "— repair pass skipped (cwd would be main tree).",
            file=sys.stderr,
        )
        return 0

    try:
        from tools.finalize_iterate import run as finalize_run
        result = finalize_run(project_root, run_id=run_id)
        print(f"[iterate_stop_finalize] repair pass completed: "
              f"{sum(1 for s in result['steps'].values() if s.get('written'))} artifacts updated",
              file=sys.stderr)
    except Exception as exc:
        print(f"[iterate_stop_finalize] repair failed: {exc}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
