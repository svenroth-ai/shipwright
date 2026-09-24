"""Resolve the base ref a loop unit branches off, by branch strategy.

Extracted from ``autonomous_loop.py``
(iterate-2026-06-13-campaign-serial-default) so the loop state machine stays
under the bloat guideline. The ``serial`` strategy (interleaved campaigns)
branches each sub-iterate off the FRESH remote default ref; ``stacked`` off the
previous unit's branch; ``independent`` off local ``main``.

**``cwd`` threading (campaign-dag-scheduler R4, work item 11).** Every
``git`` call below now accepts an optional `cwd` — ``None`` preserves the
historical behavior (run with the PROCESS's own cwd, exactly as before this
change) for every existing caller (``autonomous_loop.cmd_next``,
``lib.loop_state.verify_merged_commit_ancestry``, both unchanged). R4's
``loop_claim.py::cmd_next_batch`` is the first caller that MUST NOT rely on
process cwd — it runs from the shared orchestrator process, but a per-unit
worktree may exist by the time it runs (R5a) — so it threads its own
``--campaign-worktree`` through here explicitly rather than trusting
whatever the process happened to be sitting in.
"""

from __future__ import annotations

import subprocess


def resolve_default_branch(*, cwd: str | None = None) -> str:
    """Remote default branch name from ``origin/HEAD``, fallback ``main``.

    The serial strategy must NOT assume the default branch is literally ``main``.
    """
    try:
        r = subprocess.run(
            ["git", "symbolic-ref", "refs/remotes/origin/HEAD"],
            capture_output=True, text=True, timeout=10, cwd=cwd,
        )
        prefix = "refs/remotes/origin/"
        if r.returncode == 0 and r.stdout.strip().startswith(prefix):
            return r.stdout.strip()[len(prefix):]
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return "main"


def fresh_remote_default_ref(*, cwd: str | None = None) -> str:
    """Fetch (fail-soft) + return the fresh remote default ref ``origin/<default>``.

    The serial strategy branches off this remote ref — never the possibly-stale
    LOCAL ``main`` — so a sub-iterate always starts from a tree that already
    contains every prior sub-iterate's merged change (code-enforced freshness).
    A failed/absent ``git fetch`` is fail-soft: resolve against the last-known
    ``origin`` ref rather than crashing the loop offline.
    """
    try:
        subprocess.run(["git", "fetch", "origin"],
                       capture_output=True, text=True, timeout=60, cwd=cwd)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return f"origin/{resolve_default_branch(cwd=cwd)}"


def resolve_base_branch(strategy: str, units: list, unit: dict, *, cwd: str | None = None) -> str | None:
    """The ref ``unit`` branches off, given the loop's branch ``strategy``.

    - ``serial``: fresh ``origin/<default>`` (interleaved campaign — EVERY unit,
      incl. the first, so it composes on every prior merged sub-iterate).
    - ``stacked``: the previous unit's branch (``None`` for the first).
    - ``independent``: local ``main``.
    - ``single-branch`` / unknown: ``None`` (stay on the current branch).
    """
    if strategy == "serial":
        return fresh_remote_default_ref(cwd=cwd)
    if strategy == "stacked":
        idx = units.index(unit)
        return units[idx - 1].get("branch") if idx > 0 else None
    if strategy == "independent":
        return "main"
    return None
