"""Resolve Shipwright project root for hooks and scripts.

Hooks run with cwd set to the workspace root, which may differ from
the managed project root (e.g. ``webui/`` inside a monorepo).  This
module provides a single deterministic resolution function used by all
hooks and scripts.
"""

from __future__ import annotations

import os
from pathlib import Path

_CONFIG_MARKER = "shipwright_run_config.json"
_SECONDARY_MARKERS = (
    "shipwright_project_config.json",
    "shipwright_plan_config.json",
    "shipwright_build_config.json",
    "shipwright_events.jsonl",
)


def _is_shipwright_project(path: Path) -> bool:
    """Return True if *path* looks like a Shipwright-managed project."""
    if (path / _CONFIG_MARKER).exists():
        return True
    return any((path / m).exists() for m in _SECONDARY_MARKERS)


def resolve_project_root(*, allow_env: bool = True) -> Path:
    """Resolve Shipwright project root with deterministic fallback chain.

    Priority:
      1. ``SHIPWRIGHT_PROJECT_ROOT`` env var (if *allow_env* and valid)
      2. cwd, if it contains a Shipwright config marker
      3. Exactly **one** immediate subdirectory of cwd that contains a
         marker (handles monorepo-with-subdirectory-project)
      4. cwd fallback (standalone / not-yet-initialized project)

    Raises :class:`ValueError` when step 3 finds multiple candidate
    subdirectories — better to fail loudly than silently pick the wrong
    project.
    """
    if allow_env:
        env_val = os.environ.get("SHIPWRIGHT_PROJECT_ROOT", "").strip()
        if env_val:
            env_path = Path(env_val).resolve()
            if env_path.is_dir() and _is_shipwright_project(env_path):
                return env_path

    cwd = Path.cwd()

    if _is_shipwright_project(cwd):
        return cwd

    candidates = [
        d for d in cwd.iterdir()
        if d.is_dir() and not d.name.startswith(".") and _is_shipwright_project(d)
    ]

    if len(candidates) == 1:
        return candidates[0]

    if len(candidates) > 1:
        names = ", ".join(sorted(c.name for c in candidates))
        raise ValueError(
            f"Multiple Shipwright projects found under {cwd}: {names}. "
            f"Set SHIPWRIGHT_PROJECT_ROOT to disambiguate."
        )

    return cwd
