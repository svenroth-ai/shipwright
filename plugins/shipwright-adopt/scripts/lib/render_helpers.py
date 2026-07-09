"""Shared pure helpers for adopt's agent-doc renderers.

Extracted from ``artifact_writer.py`` (which sits at its bloat baseline) so
the renderer modules can share ``_utc_today`` / ``_fmt_stack_line`` without
either file growing past its ceiling. Neutral leaf module — imports nothing
local, so it introduces no ``lib.*`` import cycle.
"""

from __future__ import annotations

from datetime import datetime, timezone


def _utc_today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _fmt_stack_line(stack_group: dict[str, str]) -> str:
    if not stack_group:
        return "—"
    return ", ".join(sorted(stack_group.keys()))
