"""Auxiliary Compliance-Dashboard section builders.

Extracted from ``compliance_report.py`` (anti-ratchet: that generator is a
grandfathered over-limit file, so a new section — AR-10's CI-security block —
is offset by moving these cohesive, self-contained section renderers here).
Each takes the collected ``ComplianceData`` and returns markdown lines.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

# Same shared markdown helper import shape as compliance_report.py (ADR-045:
# markdown_table lives outside the plugin `lib/` namespace).
_SHARED_SCRIPTS = Path(__file__).resolve().parents[4] / "shared" / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))
from markdown_table import escape_cell  # noqa: E402

if TYPE_CHECKING:
    from scripts.lib.data_collector import ComplianceData


def render_date(timestamp: str) -> date:
    """Deterministic reference ``date`` for AR-10 accepted-risk expiry.

    Derived from the event-pinned ``data.timestamp`` (not wall-clock) so the
    dashboard render stays byte-stable, matching the ``Generated:`` banner.
    Falls back to today only when the pinned timestamp is unparseable."""
    try:
        return date.fromisoformat((timestamp or "")[:10])
    except ValueError:
        return date.today()


def project_velocity(data: ComplianceData) -> list[str]:
    """Project velocity computed from event timestamps."""
    build_events = [we for we in data.work_events if we.source == "build"]
    iterate_events = [we for we in data.work_events if we.source == "iterate"]

    lines = ["## Project Velocity", ""]

    if build_events:
        first_date = build_events[0].timestamp[:10]
        last_date = build_events[-1].timestamp[:10]
        lines.append(f"- Build: {len(build_events)} sections ({first_date} → {last_date})")

    if iterate_events:
        first_date = iterate_events[0].timestamp[:10]
        last_date = iterate_events[-1].timestamp[:10]
        lines.append(f"- Iterate: {len(iterate_events)} changes ({first_date} → {last_date})")

    if data.work_events:
        lines.append(f"- Last activity: {data.work_events[-1].timestamp[:10]}")

    lines.append("")
    return lines


def external_review_evidence(data: ComplianceData) -> list[str]:
    """External LLM review audit evidence — one row per planning split.

    Reads the markers written by shipwright-plan v0.3.0+ Step 5. Splits with
    no marker are shown as "missing" so auditors can see the gap.
    """
    if not data.external_review_states:
        return []

    lines = [
        "## External LLM Review Evidence",
        "",
        "| Split | Status | Provider | Findings | Self-review fallback | Reason |",
        "|-------|--------|----------|----------|----------------------|--------|",
    ]
    for s in data.external_review_states:
        provider = s.provider or "—"
        fallback = "yes" if s.self_review_fallback_ran else "no"
        reason = s.reason or "—"
        lines.append(
            f"| {escape_cell(s.split)} | {escape_cell(s.status)} | {escape_cell(provider)} "
            f"| {s.findings_count} | {fallback} | {escape_cell(reason)} |"
        )
    lines.append("")
    return lines
