"""Resolve Shipwright project root for hooks and scripts.

Hooks run with cwd set to the workspace root, which may differ from
the managed project root (e.g. ``webui/`` inside a monorepo).  This
module provides a single deterministic resolution function used by all
hooks and scripts.

It is also the **single source of truth for the greenfield/foreign
boundary**: :func:`is_shipwright_project` is the one predicate every hook
delegates to (phase-quality / compliance / triage / handoff / tool-call
audits) so a tree carrying any single marker is classified identically
everywhere. Before iterate-2026-06-12-canonical-project-predicate the
hooks each carried their own marker set (run-only, run+build, 5-config,
5-config+agent_docs) and disagreed on partially-initialised trees.
"""

from __future__ import annotations

import os
from pathlib import Path

# Config-file markers — any one of these makes a directory a Shipwright
# project. ``shipwright_run_config.json`` stays first (the canonical primary)
# but it carries no special weight in :func:`is_shipwright_project`.
CONFIG_MARKERS: tuple[str, ...] = (
    "shipwright_run_config.json",
    "shipwright_project_config.json",
    "shipwright_plan_config.json",
    "shipwright_build_config.json",
    "shipwright_events.jsonl",
)

def is_shipwright_project(path: Path) -> bool:
    """Return True if *path* is a Shipwright-managed project (canonical SSoT).

    True when *path* carries any config-file marker (:data:`CONFIG_MARKERS`)
    **or** a ``.shipwright/agent_docs/`` directory. The agent_docs arm covers
    the window between ``/shipwright-project`` init and the first config write
    so fresh projects aren't skipped by the Stop-hook audits.

    Fail-closed on odd inputs — a non-existent path, a missing marker, or
    ``.shipwright/agent_docs`` existing as a *file* rather than a directory all
    return ``False`` (``Path.exists`` / ``Path.is_dir`` never raise for these).
    """
    if any((path / marker).exists() for marker in CONFIG_MARKERS):
        return True
    return (path / ".shipwright" / "agent_docs").is_dir()


# Back-compat alias for the historical private name. External importers
# (e.g. the drift-anchor F7 guard) import ``_is_shipwright_project``; keep it
# pointing at the canonical predicate so there is exactly one implementation.
_is_shipwright_project = is_shipwright_project


def _has_config_marker(path: Path) -> bool:
    """True if *path* carries a config-file marker (excludes the agent_docs-only
    case). Lets :func:`resolve_project_root` prefer a fully-configured sibling
    over a merely-initialised one during the monorepo subdir scan."""
    return any((path / marker).exists() for marker in CONFIG_MARKERS)


def resolve_project_root(*, allow_env: bool = True) -> Path:
    """Resolve Shipwright project root with deterministic fallback chain.

    Priority:
      1. ``SHIPWRIGHT_PROJECT_ROOT`` env var (if *allow_env* and valid)
      2. cwd, if it is itself a Shipwright project
      3. Exactly **one** immediate subdirectory of cwd that is a Shipwright
         project (handles monorepo-with-subdirectory-project). A subdir that
         carries a config marker outranks one detected only via
         ``.shipwright/agent_docs/`` — so a stray agent_docs directory beside a
         real configured project cannot turn a clean resolution into a
         multi-candidate ``ValueError``.
      4. cwd fallback (standalone / not-yet-initialized project)

    Raises :class:`ValueError` when step 3 finds multiple candidates of the
    same tier — better to fail loudly than silently pick the wrong project.
    """
    if allow_env:
        env_val = os.environ.get("SHIPWRIGHT_PROJECT_ROOT", "").strip()
        if env_val:
            env_path = Path(env_val).resolve()
            if env_path.is_dir() and is_shipwright_project(env_path):
                return env_path

    cwd = Path.cwd()

    if is_shipwright_project(cwd):
        return cwd

    candidates = [
        d for d in cwd.iterdir()
        if d.is_dir() and not d.name.startswith(".") and is_shipwright_project(d)
    ]

    # Prefer config-bearing candidates: an agent_docs-only subdir only counts
    # when no fully-configured sibling exists. Keeps resolution backward-compatible
    # now that agent_docs-only trees qualify as projects.
    config_candidates = [d for d in candidates if _has_config_marker(d)]
    effective = config_candidates or candidates

    if len(effective) == 1:
        return effective[0]

    if len(effective) > 1:
        names = ", ".join(sorted(c.name for c in effective))
        raise ValueError(
            f"Multiple Shipwright projects found under {cwd}: {names}. "
            f"Set SHIPWRIGHT_PROJECT_ROOT to disambiguate."
        )

    return cwd
