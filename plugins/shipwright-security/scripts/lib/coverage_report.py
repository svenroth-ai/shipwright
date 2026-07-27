#!/usr/bin/env python3
"""Markdown rendering for the scan coverage manifest.

Kept out of ``generate_security_report`` so the report generator (already over
its bloat baseline) gains only a delegating call. Every function returns a list
of Markdown lines and returns ``[]`` for nothing-to-say, so callers can splice
unconditionally — the same contract as ``degraded_banner``.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

_LIB_DIR = Path(__file__).resolve().parent
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

from scan_coverage import (  # noqa: E402
    class_label,
    is_complete,
    unchecked_classes,
)

_STATUS_ICON = {
    "covered": "✅ checked",
    "degraded": "⚠️ failed to run",
    "not_requested": "⬜ not requested",
    "not_available": "❌ NOT CHECKED",
}


def coverage_banner(coverage: list[dict[str, Any]] | None) -> list[str]:
    """Warn that this scan did not look at every class of weakness.

    Three outcomes:

    - complete coverage → ``[]`` (the table below still shows the detail);
    - an absent/empty manifest → an "unknown coverage" warning, because a
      report that cannot say what it checked must not read as a clean pass;
    - one or more unchecked classes → a warning naming them.
    """
    rows = [r for r in (coverage or []) if isinstance(r, dict)]
    if not rows:
        return [
            "> ⚠️ **Coverage not reported** — this scan record does not say "
            "which classes of weakness were checked, so coverage is unknown. "
            "Absence of findings here is NOT evidence that a class is clean.",
            "",
        ]
    if is_complete(rows):
        return []
    unchecked = unchecked_classes(rows)
    if not unchecked:
        # Only degraded rows — the degraded banner already carries that story.
        return []
    names = ", ".join(class_label(c) for c in unchecked)
    return [
        f"> ⚠️ **Incomplete Coverage** — this scan did not look for: {names}. "
        "Those classes read as clean below only because nothing looked at "
        "them. See the Coverage table.",
        "",
    ]


def coverage_table(coverage: list[dict[str, Any]] | None) -> list[str]:
    """A per-class table naming what was checked and what was not."""
    rows = [r for r in (coverage or []) if isinstance(r, dict)]
    if not rows:
        return []
    lines = [
        "## Coverage",
        "",
        "| Class | Tool | Checked | Why not |",
        "|-------|------|---------|---------|",
    ]
    for row in rows:
        cls = class_label(str(row.get("class", "?")))
        tool = str(row.get("tool") or "—")
        status = _STATUS_ICON.get(str(row.get("status")), str(row.get("status")))
        detail = str(row.get("detail") or "—").replace("\n", " ").replace("|", "\\|")
        lines.append(f"| {cls} | {tool} | {status} | {detail[:120]} |")
    lines.append("")
    return lines


def coverage_summary_line(coverage: list[dict[str, Any]] | None) -> str:
    """One-line coverage statement for a card detail or a CLI summary."""
    rows = [r for r in (coverage or []) if isinstance(r, dict)]
    if not rows:
        return "coverage not reported"
    unchecked = unchecked_classes(rows)
    if not unchecked:
        return "coverage: all classes checked" if is_complete(rows) else \
               "coverage: a check failed to run (see scan errors)"
    return "not checked: " + ", ".join(class_label(c) for c in unchecked)
