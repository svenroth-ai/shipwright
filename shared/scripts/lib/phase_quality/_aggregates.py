"""Finding loaders + locked aggregate orchestrator + GC.

Reads the per-run Finding-JSONs and drives the three aggregate
regenerators in :mod:`._dashboard_render`:

* :class:`LoadedFinding` — typed wrapper around a parsed Finding-JSON.
* :func:`load_findings` — enumerate + sort all findings under the
  ``.shipwright/compliance/skill-compliance`` directory.
* :func:`count_by_status` / :func:`_roll_up_counts` — small math
  helpers reused by every renderer.
* :func:`gc_old_findings` — archive findings older than ``GC_AGE_DAYS``.
* :func:`regenerate_all_aggregates` — locked wrapper that calls the
  three renderers in :mod:`._dashboard_render`.

Iterate Campaign B (B3): split out of the 1108-LOC monolith. The
Markdown-render logic itself lives in :mod:`._dashboard_render` so
this module stays under the 300-LOC source budget.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

_SCRIPTS_ROOT = Path(__file__).resolve().parents[2]
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from lib.file_lock import LockTimeout, file_lock  # noqa: E402

from ._constants import (
    FINDING_DIR,
    GC_AGE_DAYS,
    LOCK_PATH,
)

# Model + loaders + counters live in the sibling leaf module; re-exported here
# (see __all__) so existing ``from ._aggregates import LoadedFinding`` callers and
# the package __init__ keep working. Importing them from ._findings_model rather
# than defining them here is what broke the _aggregates <-> _dashboard_render
# import cycle (CodeQL py/cyclic-import).
from ._findings_model import (  # noqa: F401  (re-export, see __all__)
    LoadedFinding,
    _roll_up_counts,
    count_by_status,
    load_actionable_findings,
    load_findings,
)


def gc_old_findings(
    project_root: Path,
    *,
    max_age_days: int = GC_AGE_DAYS,
) -> int:
    """Move findings older than ``max_age_days`` to ``archive/``.

    Returns the number of files archived. Best-effort: failures on
    individual moves are swallowed so GC never blocks the hook.
    """
    base = project_root / FINDING_DIR
    if not base.is_dir():
        return 0
    archive = base / "archive"
    cutoff = time.time() - (max_age_days * 86400)
    moved = 0
    for path in base.glob("*.json"):
        try:
            if path.stat().st_mtime >= cutoff:
                continue
            archive.mkdir(parents=True, exist_ok=True)
            target = archive / path.name
            try:
                os.replace(path, target)
                moved += 1
            except OSError:
                continue
        except OSError:
            continue
    return moved


def regenerate_all_aggregates(project_root: Path, *, timeout_seconds: float = 5.0) -> None:
    """Run the three aggregate rewrites under a single file lock.

    Locking only the aggregate step is intentional — per-run Finding
    JSONs are already disjoint, so contention only exists when multiple
    sessions finish at the same time and fight over the summary files
    (plan § 5.2).
    """
    # Renderers live in the sibling ._dashboard_render; imported at call-time to
    # keep this module's import cheap. The model layer both modules share now
    # lives in ._findings_model, so this no longer needs to be cycle-breaking.
    from ._dashboard_render import (
        rewrite_aggregated_report,
        rewrite_session_findings_summary,
        write_quality_dashboard_file,
    )

    lock_path = project_root / LOCK_PATH
    try:
        with file_lock(lock_path, timeout_seconds=timeout_seconds):
            rewrite_aggregated_report(project_root)
            rewrite_session_findings_summary(project_root)
            write_quality_dashboard_file(project_root)
    except LockTimeout as exc:
        sys.stderr.write(
            f"[audit_phase_quality] aggregate rewrite skipped: {exc}\n"
        )


__all__ = [
    "LoadedFinding",
    "_roll_up_counts",
    "count_by_status",
    "gc_old_findings",
    "load_actionable_findings",
    "load_findings",
    "regenerate_all_aggregates",
]
