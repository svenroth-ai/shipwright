"""Resolve the base ref a loop unit branches off, by branch strategy.

Extracted from ``autonomous_loop.py``
(iterate-2026-06-13-campaign-serial-default) so the loop state machine stays
under the bloat guideline. The ``serial`` strategy (interleaved campaigns)
branches each sub-iterate off the FRESH remote default ref; ``stacked`` off the
previous unit's branch; ``independent`` off local ``main``.
"""

from __future__ import annotations

import subprocess


def resolve_default_branch() -> str:
    """Remote default branch name from ``origin/HEAD``, fallback ``main``.

    The serial strategy must NOT assume the default branch is literally ``main``.
    """
    try:
        r = subprocess.run(
            ["git", "symbolic-ref", "refs/remotes/origin/HEAD"],
            capture_output=True, text=True, timeout=10,
        )
        prefix = "refs/remotes/origin/"
        if r.returncode == 0 and r.stdout.strip().startswith(prefix):
            return r.stdout.strip()[len(prefix):]
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return "main"


def fresh_remote_default_ref() -> str:
    """Fetch (fail-soft) + return the fresh remote default ref ``origin/<default>``.

    The serial strategy branches off this remote ref — never the possibly-stale
    LOCAL ``main`` — so a sub-iterate always starts from a tree that already
    contains every prior sub-iterate's merged change (code-enforced freshness).
    A failed/absent ``git fetch`` is fail-soft: resolve against the last-known
    ``origin`` ref rather than crashing the loop offline.
    """
    try:
        subprocess.run(["git", "fetch", "origin"],
                       capture_output=True, text=True, timeout=60)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return f"origin/{resolve_default_branch()}"


def resolve_base_branch(strategy: str, units: list, unit: dict) -> str | None:
    """The ref ``unit`` branches off, given the loop's branch ``strategy``.

    - ``serial``: fresh ``origin/<default>`` (interleaved campaign — EVERY unit,
      incl. the first, so it composes on every prior merged sub-iterate).
    - ``stacked``: the previous unit's branch (``None`` for the first).
    - ``independent``: local ``main``.
    - ``single-branch`` / unknown: ``None`` (stay on the current branch).
    """
    if strategy == "serial":
        return fresh_remote_default_ref()
    if strategy == "stacked":
        idx = units.index(unit)
        return units[idx - 1].get("branch") if idx > 0 else None
    if strategy == "independent":
        return "main"
    return None
