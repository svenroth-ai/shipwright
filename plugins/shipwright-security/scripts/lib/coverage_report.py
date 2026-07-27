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
# The SSoT markdown-cell escaper lives in shared/scripts (same import the report
# generator uses for its finding cells).
sys.path.insert(0, str(_LIB_DIR.parents[2].parent / "shared" / "scripts"))

from markdown_table import escape_cell  # noqa: E402
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
    # Degraded classes are named HERE too, not only in the degraded banner.
    # Today every degraded row comes from a scan_errors marker, so the two
    # overlap — but the banner renders from scan_errors while this renders from
    # the MANIFEST, and Part 2 adds a degradation with no marker behind it (a
    # project gitleaks config carrying no effective rules runs fine and finds
    # almost nothing). Naming degraded rows here means that case arrives already
    # warned about instead of silently changing a status.
    degraded = [
        str(r["class"]) for r in rows
        if r.get("status") == "degraded" and r.get("class")
    ]
    parts = []
    if unchecked:
        parts.append(
            "did not look for: "
            + ", ".join(class_label(c) for c in unchecked))
    if degraded:
        parts.append(
            "could not trust the result for: "
            + ", ".join(class_label(c) for c in degraded))
    if not parts:
        return []
    return [
        f"> ⚠️ **Incomplete Coverage** — this scan {'; and '.join(parts)}. "
        "Those classes read as clean below only because nothing reliable "
        "looked at them. See the Coverage table.",
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
        # EVERY cell is escaped, not just `detail`. The manifest is read back
        # from findings.json, which a scanner or a prior run wrote — untrusted
        # input. An unescaped `|` or newline in `class`/`tool`/`status` would
        # break the table or inject markdown into a report an operator (or an
        # agent) reads.
        cls = escape_cell(class_label(str(row.get("class", "?"))))
        tool = escape_cell(str(row.get("tool") or "—"))
        raw_status = str(row.get("status"))
        # A file-sourced manifest has already been coerced into the closed
        # vocabulary by coverage_sanitize (the original survives in `detail`),
        # so an unrecognized value here means an in-process producer bug —
        # render it escaped rather than hiding it behind a plausible icon.
        status = _STATUS_ICON.get(raw_status, escape_cell(raw_status))
        detail = escape_cell(str(row.get("detail") or "—"))
        lines.append(f"| {cls} | {tool} | {status} | {detail[:160]} |")
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
