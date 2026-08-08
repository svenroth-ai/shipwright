"""Coverage check for mandated "read completely" file loads.

A single ``Read`` call caps at 2,000 lines (documented harness limit). A
skill instruction that says "read completely" silently breaks once a target
file crosses that cap -- nothing reports the shortfall, so the governance
promise ("the agent knows this before changing anything") quietly stops
being true exactly when a project is mature enough to need it (TC3.2,
trg-c0d83dce). ``decision_log.md`` already dodges this by reading an index
instead (`lib.decision_log_index`); this module is for the mandated loads
that have no index to dodge with -- `.shipwright/planning/*/spec.md` today.

This is a check, not an architecture: it reports each file's line count
against the cap so a caller can declare "read K of N lines" as a fact,
mirroring the coverage envelope `event_context_coverage.py` already reports
for event data. It does not read the files' content, cap or extend a Read
call, or decide what to do about an oversized file -- that stays the
calling skill's job.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

#: Matches the harness's documented per-`Read`-call line cap.
READ_LINE_CAP = 2000


def check_coverage(paths: list[str], cap_lines: int = READ_LINE_CAP) -> dict[str, Any]:
    """Report each of `paths` against `cap_lines`.

    Missing files are reported (`exists: False`) rather than raising --
    a mandated-load list built from a glob can legitimately be empty or
    stale, and that is itself worth declaring, not a crash.
    """
    files: list[dict[str, Any]] = []
    any_exceeds = False
    for raw_path in paths:
        path = Path(raw_path)
        if not path.is_file():
            files.append({"path": raw_path, "exists": False})
            continue
        try:
            with path.open("r", encoding="utf-8", errors="replace") as fh:
                total_lines = sum(1 for _ in fh)
        except OSError as exc:
            # Declared, not raised -- a permission-denied or vanished-between-
            # is_file()-and-open() file must not crash the check; the whole
            # point of this module is that a mandated load says so instead of
            # proceeding as if it were read. Keeps the SAME keys as a normal
            # row (external code review, iterate-2026-08-08): a caller that
            # unconditionally reads `exceeds_cap` off every existing-file row
            # must not KeyError on this one -- `None` reads as "unknown", not
            # "no problem".
            files.append({
                "path": raw_path, "exists": True, "error": str(exc),
                "total_lines": None, "cap_lines": cap_lines, "exceeds_cap": None,
            })
            continue
        exceeds = total_lines > cap_lines
        any_exceeds = any_exceeds or exceeds
        files.append({
            "path": raw_path,
            "exists": True,
            "total_lines": total_lines,
            "cap_lines": cap_lines,
            "exceeds_cap": exceeds,
        })
    return {"files": files, "any_exceeds_cap": any_exceeds}
