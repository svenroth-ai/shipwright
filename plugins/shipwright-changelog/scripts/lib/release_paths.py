"""Where the release CLI finds the code next to it, in every layout the plugin ships in.

``{plugin_root}/../../shared`` is the shared tree in all four: the monorepo checkout and a git worktree
(``plugins/shipwright-changelog``), the installed cache (``cache/shipwright/shipwright-changelog/<version>``),
the cache's mirror (``cache/shipwright/plugins/shipwright-changelog``) and the Codex bundle
(``<bundle>/origin/shipwright-changelog``). Run's ``orchestrator.py`` is a sibling plugin's script and is reached
through ``ORCHESTRATOR`` only (programme P16); ``tests/test_release_paths_and_boundary.py`` builds each layout and resolves it.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

ORCHESTRATOR = ("scripts", "lib", "orchestrator.py")  # inside the run plugin
RUN_PLUGIN = "shipwright-run"
ORPHAN_MARKER = ".orphaned_at"  # the cache installer's tombstone inside a replaced plugin version


def shared_root(plugin_root: Path) -> Path:
    return Path(plugin_root).resolve().parents[1] / "shared"


def run_config_path(shared: Path, project_root: Path) -> Path:
    """The run config's path through the shared resolver (programme P16: a root file is named through ``shipwright_paths`` only).
    The module is loaded by file, never as ``lib.shipwright_paths``: this plugin has its own ``lib`` package."""
    name = "shipwright_paths"
    module = sys.modules.get(name)
    if module is None:
        spec = importlib.util.spec_from_file_location(name, Path(shared) / "scripts" / "lib" / f"{name}.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module  # register before exec, or its dataclasses cannot resolve their own module
        spec.loader.exec_module(module)
    return module.path("run_config", project_root)


def _version_key(path: Path) -> tuple[int, ...]:
    return tuple(int(n) for n in re.findall(r"\d+", path.name))


def orchestrator_path(plugin_root: Path) -> Path | None:
    """The run plugin's ``orchestrator.py`` for this layout, or ``None`` when no layout holds it."""
    root = Path(plugin_root).resolve()
    rel = Path(*ORCHESTRATOR)
    candidates = [root.parents[1] / "plugins" / RUN_PLUGIN / rel,  # checkout, worktree, the cache's mirror tree
                  root.parent / RUN_PLUGIN / rel]  # Codex bundle: sibling plugins under origin/
    installed = root.parent.parent / RUN_PLUGIN  # cache/shipwright/shipwright-run/<version>
    if installed.is_dir():
        versions = sorted((v for v in installed.iterdir() if v.is_dir() and not (v / ORPHAN_MARKER).exists()),
                          key=_version_key, reverse=True)  # a version the installer marked orphaned is not a live copy
        own = [v for v in versions if v.name == root.name]  # the run plugin of the SAME version as this plugin first, then the newest
        candidates += [v / rel for v in own + [v for v in versions if v not in own]]
    return next((c for c in candidates if c.is_file()), None)
