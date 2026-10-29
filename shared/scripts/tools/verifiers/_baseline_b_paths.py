"""Path-ownership baseline: the null model T-code has to beat (BP unit BL0b, item 3).

A changed non-test file under ``plugins/X/`` maps to the FR whose catalog name is ``/X``. A changed non-test Python file
under ``shared/`` maps to the FRs of the plugins that (transitively, through other ``shared`` modules) import it. The import graph
is read from the HEAD tree by module STEM (``lib.events_log`` -> ``events_log``): stems shared by two modules over-approximate
(a recall-friendly bias for the baseline, i.e. it errs in the baseline's favour). Not followed: imports built at run time,
scripts run as subprocesses, non-Python files under ``shared/`` (templates, prompts, profiles).
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from ._baseline_touch_git import is_test_path

__all__ = ["plugin_owners", "import_owners", "path_frs"]

_ROW = re.compile(r"^\|\s*(FR-\d{2}\.\d{2})\s*\|[^|]*\|\s*/(shipwright-[\w-]+)\s*\|", re.M)


def plugin_owners(spec_text: str) -> dict[str, str]:
    """``shipwright-x`` -> ``FR-01.nn`` from the catalog rows named ``/shipwright-x``."""
    return {plugin: fr for fr, plugin in _ROW.findall(spec_text)}


def _imported_stems(path: Path) -> set[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except (SyntaxError, ValueError):
        return set()
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out |= {part for a in node.names for part in a.name.split(".")}
        elif isinstance(node, ast.ImportFrom):
            out |= set((node.module or "").split(".")) | {a.name for a in node.names}
    out.discard("")
    return out


def import_owners(tree: Path, owners: dict[str, str]) -> dict[str, set[str]]:
    """Stem of every ``shared`` module -> FRs of the plugins reaching it (direct or through another shared module)."""
    shared = {p: p.stem for p in (tree / "shared").rglob("*.py") if not is_test_path(p.relative_to(tree).as_posix()) and p.stem != "__init__"
              and "node_modules" not in p.parts and ".venv" not in p.parts}
    importers: dict[str, set[str]] = {}  # stem -> stems of shared modules importing it
    direct: dict[str, set[str]] = {}     # stem -> plugin FRs importing it
    for path, stem in shared.items():
        for imp in _imported_stems(path):
            importers.setdefault(imp, set()).add(stem)
    for plugin, fr in owners.items():
        for path in (tree / "plugins" / plugin).rglob("*.py"):
            rel = path.relative_to(tree).as_posix()
            if is_test_path(rel) or ".venv" in path.parts:
                continue
            for imp in _imported_stems(path):
                direct.setdefault(imp, set()).add(fr)
    reach: dict[str, set[str]] = {}
    for stem in set(shared.values()):
        seen, todo, frs = {stem}, [stem], set()
        while todo:
            cur = todo.pop()
            frs |= direct.get(cur, set())
            for nxt in importers.get(cur, set()) - seen:
                seen.add(nxt)
                todo.append(nxt)
        reach[stem] = frs
    return reach


def path_frs(changes: list[tuple[str, str, str]], owners: dict[str, str], reach: dict[str, set[str]]) -> dict[str, list[str]]:
    """FR -> changed files that map to it. Tests are the git leg's business and are skipped here."""
    out: dict[str, list[str]] = {}
    for _status, old, new in changes:
        for path in {old, new}:
            m = re.match(r"^plugins/(shipwright-[\w-]+)/", path)
            if is_test_path(path) or (m and "/tests/" in path):
                continue
            if m and m[1] in owners:
                out.setdefault(owners[m[1]], []).append(path)
            elif path.startswith("shared/") and path.endswith(".py"):
                for fr in reach.get(Path(path).stem, set()):
                    out.setdefault(fr, []).append(path)
    return out
