"""What decides whether a small iterate's code review was due: risk flags and diff size.

Split from :mod:`cascade_trigger` along its natural seam. This module reads git
and the run's self-reports. The gate next door decides what the review record
must then say.

**Risk flags** are the union of three sources. Any one of them is enough:

* the session plan Stage 1 wrote (``.shipwright/agent_docs/iterates/<run_id>.plan.json``,
  ``classify_complexity --run-id``), which a standalone iterate leaves;
* Step 3.4's ``risk_recheck.json``, which a campaign sub-iterate leaves;
* the two detectors that shared/ already carries, recomputed from the branch diff
  (``cross_component`` and ``touches_ci_supplychain``). A flag the agent did not
  record still counts.

**Diff size** follows ``lib/review_diff_threshold.py`` exactly: added+removed lines
of ``git diff --numstat --no-renames <merge-base>..<commit>``, without the
finalization records, ``> 100``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_SCRIPTS_ROOT = Path(__file__).resolve().parents[2]
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from lib.review_diff_threshold import is_counted_path, numstat_changed_lines  # noqa: E402
from lib.review_record_schema import is_safe_run_id  # noqa: E402

from .ci_supplychain import _is_ci_supplychain  # noqa: E402
from .git_helpers import _branch_base_commit, _run_git  # noqa: E402
from .integration_coverage import _is_cross_component  # noqa: E402
from .risk_recheck_recording import _read_recheck_record  # noqa: E402

__all__ = ["DiffMeasure", "measure_diff", "recorded_risk_flags"]

_GIT_TIMEOUT = 30.0


def _plan_flags(project_root: Path, run_id: str) -> tuple[list[str], str | None]:
    """``risk_flags`` from the Stage-1 session plan. Absence is ``([], None)``."""
    path = Path(project_root) / ".shipwright" / "agent_docs" / "iterates" / f"{run_id}.plan.json"
    if not path.exists():
        return [], None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return [], f"{path.name} is unreadable ({exc}); a corrupt plan cannot vouch for 'no risk flag'"
    flags = data.get("risk_flags") if isinstance(data, dict) else None
    if not isinstance(flags, list):
        return [], f"{path.name} carries no `risk_flags` list"
    return [f for f in flags if isinstance(f, str) and f.strip()], None


def recorded_risk_flags(project_root: Path, run_id: str) -> tuple[list[str], str | None]:
    """The run's self-reported flags (session plan + Step 3.4 record), or why not."""
    if not is_safe_run_id(run_id):
        return [], f"run id {str(run_id)[:60]!r} is not a single safe path component"
    flags, err = _plan_flags(project_root, run_id)
    if err:
        return [], err
    block, err = _read_recheck_record(Path(project_root), run_id)
    if err:
        return [], err
    if block is not None:
        flags += [f for f in block.get("risk_flags") or [] if isinstance(f, str) and f.strip()]
    return sorted(set(flags)), None


class DiffMeasure:
    """The branch's changed paths and counted lines, or the reason they are unknown."""

    def __init__(self, paths: list[str] | None = None, lines: int | None = None,
                 error: str | None = None, base: str = "") -> None:
        self.paths = paths or []
        self.lines = lines
        self.error = error
        self.base = base

    def diff_flags(self) -> list[str]:
        """Detectors run over the counted paths: a finalization record is not code."""
        paths = [p for p in self.paths if is_counted_path(p)]
        flags = []
        if _is_cross_component(paths):
            flags.append("cross_component")
        if _is_ci_supplychain(paths):
            flags.append("touches_ci_supplychain")
        return flags


def _is_merge(project_root: Path, commit: str) -> bool:
    rc, out, _ = _run_git(project_root, "rev-list", "--parents", "-n", "1", commit, timeout=_GIT_TIMEOUT)
    return rc != 0 or len(out.split()) > 2


def measure_diff(project_root: Path, commit: str) -> DiffMeasure:
    """Count the branch against its merge-base with the trunk.

    No trustworthy trunk base is UNKNOWN, never "the last commit": a branch of
    several commits would otherwise be measured by its tip alone. A commit that
    already sits on the trunk (``base == commit``) has no branch range, so the
    commit itself is measured, unless it is a merge commit, whose own numstat
    shows nothing; that case is unknown too.
    """
    base = _branch_base_commit(project_root, commit)
    rc, head, _ = _run_git(project_root, "rev-parse", commit, timeout=_GIT_TIMEOUT)
    head = head.strip()
    if rc != 0 or not head:
        return DiffMeasure(error=f"cannot resolve {commit[:12]!r}")
    if not base:
        return DiffMeasure(error=f"no trustworthy trunk merge-base for {head[:8]} "
                                 "(needs two agreeing trunk names, e.g. main + origin/main)")
    if base != head:
        args = ["diff", "--numstat", "--no-renames", f"{base}..{head}"]
    elif _is_merge(project_root, head):
        return DiffMeasure(error=f"{head[:8]} is a merge commit already on the trunk; its size is unknown")
    else:
        args = ["show", "--numstat", "--no-renames", "--format=", head]
    rc, out, err = _run_git(project_root, "-c", "core.quotePath=false", *args, timeout=_GIT_TIMEOUT)
    if rc != 0:
        return DiffMeasure(error=f"`git {args[0]} --numstat` failed ({(err or '').strip()[:120]})")
    try:
        paths, lines = numstat_changed_lines(out)
    except ValueError as exc:
        return DiffMeasure(error=str(exc))
    return DiffMeasure(paths, lines, base=base[:8])
