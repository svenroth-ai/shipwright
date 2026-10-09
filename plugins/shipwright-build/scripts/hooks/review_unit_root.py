"""Resolve the tree that holds a campaign run's ``reviews.json`` (salvage hook helper).

Split out of ``write-review-payload-on-stop.py`` to keep that hook under its size
limit; self-contained for the same ADR-044 reason (no ``shared/scripts/lib`` import).

A campaign runner works in its unit's own worktree, but a reviewer's
``SubagentStop`` hook fires with the session's root, so ``reviews.json`` is not
under it. The env cannot name the unit either: ``SHIPWRIGHT_LOOP_UNIT_ID`` is
exported inside the runner's Bash and never reaches a hook. Every worktree
``loop_state.json`` records for a unit is therefore a candidate, filtered by
"holds this run's reviews.json"."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Callable, Optional


def _main_root(start: Path) -> Optional[Path]:
    """The MAIN checkout for ``start`` (``loop_state.json`` lives there), or
    ``None`` when git cannot say."""
    try:
        out = subprocess.run(
            ["git", "-C", str(start), "rev-parse", "--path-format=absolute",
             "--git-common-dir"],
            capture_output=True, encoding="utf-8", errors="replace", timeout=10, check=False,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    return Path(out).parent if out else None


def _registered_worktrees(root: Path) -> Optional[set[Path]]:
    """Real paths of the repo's registered worktrees, or ``None`` when git cannot say."""
    try:
        out = subprocess.run(
            ["git", "-C", str(root), "worktree", "list", "--porcelain"],
            capture_output=True, encoding="utf-8", errors="replace", timeout=10, check=False,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    paths = {Path(line[len("worktree "):]).resolve() for line in out.splitlines()
             if line.startswith("worktree ")}
    return paths or None


def unit_worktrees(project_root: Path) -> list[Path]:
    """Worktrees ``loop_state.json`` records for the campaign's units, kept only
    when git itself lists them: ``loop_state.json`` is written by the runner, so a
    crafted entry must not steer where the hook writes."""
    roots = [project_root]
    main = _main_root(project_root)
    if main is not None and main != project_root:
        roots.append(main)
    found: list[Path] = []
    for root in roots:
        try:
            state = json.loads((root / ".shipwright" / "loop_state.json")
                               .read_text(encoding="utf-8"))
            units = state.get("units") or []
        except (OSError, ValueError, AttributeError):
            continue
        for unit in units if isinstance(units, list) else []:
            wt = unit.get("worktree") if isinstance(unit, dict) else None
            if isinstance(wt, str) and wt.strip():
                found.append(Path(wt))
    registered = _registered_worktrees(project_root)
    if registered is None:
        return []
    return [w for w in found if w.resolve() in registered]


def resolve_run_root(project_root: Path, run_id: str,
                     reviews_json_path: Callable[[Path, str], Path]) -> Path:
    """The resolved root when it holds the run's ``reviews.json``, else the one
    unit worktree that does (none or several: ambiguous), else the resolved root (the caller's wrong-root
    refusal then still fires)."""
    if reviews_json_path(project_root, run_id).exists():
        return project_root
    # The session root and the main checkout can both list the same worktree: dedupe by real path.
    unique = {c.resolve(): c for c in unit_worktrees(project_root)}.values()
    holders = [c for c in unique if reviews_json_path(c, run_id).exists()]
    # Two worktrees holding the same run id (a stale attempt) cannot be told apart
    # here: refuse rather than salvage into the wrong one.
    return holders[0] if len(holders) == 1 else project_root
