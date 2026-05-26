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

import json
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

_SCRIPTS_ROOT = Path(__file__).resolve().parents[2]
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from lib.file_lock import LockTimeout, file_lock  # noqa: E402

from ._constants import (
    CATEGORIES,
    FINDING_DIR,
    GC_AGE_DAYS,
    LOCK_PATH,
    STATUS_FAIL,
    STATUS_PASS,
    STATUS_SKIP,
    STATUS_WARN,
)


@dataclass
class LoadedFinding:
    path: Path
    phase: str
    run_id: str
    session_id: str
    audited_at: str
    source: str
    payload: dict[str, Any] = field(default_factory=dict)

    @property
    def sort_key(self) -> tuple[str, float]:
        return (self.audited_at, self.path.stat().st_mtime if self.path.exists() else 0.0)


def load_findings(project_root: Path) -> list[LoadedFinding]:
    """Load every valid Finding-JSON under ``.shipwright/compliance/skill-compliance``.

    Corrupt files are skipped with a stderr warning (plan § 4.13).
    """
    base = project_root / FINDING_DIR
    if not base.is_dir():
        return []
    loaded: list[LoadedFinding] = []
    for path in base.glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            sys.stderr.write(
                f"[audit_phase_quality] skipping corrupt finding {path}: {exc}\n"
            )
            continue
        if not isinstance(data, dict):
            continue
        loaded.append(LoadedFinding(
            path=path,
            phase=data.get("phase") or "unknown",
            run_id=data.get("run_id") or "unknown",
            session_id=data.get("session_id") or "unknown",
            audited_at=data.get("audited_at") or "",
            source=data.get("source") or "unknown",
            payload=data,
        ))
    loaded.sort(key=lambda f: f.sort_key, reverse=True)
    return loaded


def count_by_status(findings: Iterable[dict[str, Any]]) -> dict[str, int]:
    counts = {STATUS_PASS: 0, STATUS_FAIL: 0, STATUS_WARN: 0, STATUS_SKIP: 0}
    for item in findings:
        status = item.get("status") or STATUS_SKIP
        if status in counts:
            counts[status] += 1
    return counts


def _roll_up_counts(payload: dict[str, Any]) -> dict[str, int]:
    total = {STATUS_PASS: 0, STATUS_FAIL: 0, STATUS_WARN: 0, STATUS_SKIP: 0}
    for category in CATEGORIES:
        for k, v in count_by_status(payload.get(category, [])).items():
            total[k] += v
    return total


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
    # Lazy import to avoid a cycle when ``_dashboard_render`` imports
    # ``LoadedFinding`` / ``count_by_status`` / ``_roll_up_counts`` from
    # here.
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
    "load_findings",
    "regenerate_all_aggregates",
]
