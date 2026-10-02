#!/usr/bin/env python3
"""F0 resume - how a resumed run is DESCRIBED: manifest marking, console block, gate rule.

Pure composition over a `suite_resume.ResumeContext`. Kept apart from the decisions so the
sentence the console prints and the marking the retained manifest carries stay one reviewed
surface. ASCII-only (a cp1252 console raises UnicodeEncodeError, #244).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.tools.suite_resume import REUSE_GREEN, ResumeContext  # noqa: E402

_SHOWN_TESTS = 5


def manifest_extra(ctx: ResumeContext, run_id: str | None) -> dict[str, Any]:
    """The marking the retained manifest carries, so staged evidence is never mistaken
    for a full run (consumed by `stage_f0_evidence`)."""
    extra: dict[str, Any] = {}
    if ctx.fallback:
        extra["resume_fallback"] = ctx.fallback
    if ctx.used:
        extra["resumed"] = {
            "run_id": run_id, "invocation": ctx.invocation,
            "prior_invocations": list(ctx.chain), "tree_changed_files": len(ctx.changed),
            "units": {u: {"mode": ctx.plans[u].mode, "rerun_tests": ctx.reran.get(u, [])}
                      for u in sorted(ctx.used)}}
    return extra


def render_block(result) -> list[str]:
    """Console lines naming a resumed run for what it is."""
    ctx = getattr(result, "resume", None)
    if ctx is None:
        return []
    lines: list[str] = []
    if ctx.used:
        lines += ["", "RESUMED F0 RUN - NOT a full run; CI re-runs everything and is the "
                  "safety net:",
                  f"  this invocation: {ctx.invocation}; continues: {', '.join(ctx.chain)}",
                  f"  files changed since that run: {len(ctx.changed)}"]
        for unit_id in sorted(ctx.used):
            plan = ctx.plans[unit_id]
            if plan.mode == REUSE_GREEN:
                lines.append(f"  {unit_id}: green result REUSED, not re-run")
            else:
                shown = ", ".join(ctx.reran[unit_id][:_SHOWN_TESTS])
                more = len(ctx.reran[unit_id]) - _SHOWN_TESTS
                lines.append(f"  {unit_id}: re-ran only {len(ctx.reran[unit_id])} red "
                             f"test(s): {shown}{f' (+{more} more)' if more > 0 else ''}")
        lines.append("  the retained evidence is marked 'resumed' (resumed-local evidence).")
    lines += [f"  {u}: ran in FULL - {why}" for u, why in sorted(ctx.notes.items())]
    if ctx.fallback:
        lines.append(f"  FULL RE-RUN after a resume fallback: {ctx.fallback}")
    elif ctx.overall and not ctx.used:
        lines.append(f"F0 resume: not used - {ctx.overall}")
    return lines


def gate_refused_resume(result, exit_code: int) -> bool:
    """True when a resumed run's ONLY problem is the diff-coverage gate (exit 4)."""
    ctx = getattr(result, "resume", None)
    return ctx is not None and ctx.active and exit_code == 4
