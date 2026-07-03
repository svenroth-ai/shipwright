"""render_terminal — a compact, deterministic A-F card from the view-model.

Renders FROM the typed :class:`ReportModel`; it never parses another renderer's
output. Every repo-derived string is passed through :mod:`sanitize` so a hostile
commit subject / filename cannot inject ANSI or bidi control sequences into the
terminal (GPT #15).
"""

from __future__ import annotations

from report_model import DimensionView, ReportModel
from sanitize import one_line

_STATUS_TAG = {"ok": "[ok] ", "gap": "[gap]", "n/a": "[N/A]"}


def _fmt_score(score: float | None) -> str:
    return "  N/A" if score is None else f"{score:.2f}"


def _dim_line(dim: DimensionView) -> str:
    tag = _STATUS_TAG.get(dim.status, "[?]  ")
    label = one_line(dim.label, limit=32).ljust(32)
    detail = one_line(dim.detail, limit=90)
    return f"  {tag} {label} {_fmt_score(dim.score)}  {detail}"


def render_terminal(model: ReportModel) -> str:
    """Return the plain-text Control Grade card for ``model``."""
    lines: list[str] = []
    score = "N/A" if model.score is None else f"{model.score:.1f}/100"
    total = len(model.dimensions)
    measured = f"{model.measurable_count} of {total} controls measured"
    lines.append("=" * 72)
    lines.append(f"Control Grade: {model.grade}  ({score})  — {model.mode}, {measured}")
    lines.append(f"Repository: {one_line(model.target_display, limit=60)}")
    lines.append(one_line(model.verdict, limit=200))
    lines.append("=" * 72)

    lines.append(f"Dimensions ({model.measurable_count} of {total} measurable):")
    for dim in model.dimensions:
        lines.append(_dim_line(dim))

    if model.controls_shipwright_would_light:
        lit = ", ".join(one_line(c, limit=40)
                        for c in model.controls_shipwright_would_light)
        lines.append("")
        lines.append(f"Controls Shipwright would light up: {lit}")

    if model.static_test_inventory:
        lines.append(f"Test inventory: {one_line(model.static_test_inventory, limit=120)}")

    if model.reasons:
        lines.append("")
        lines.append("Top reasons:")
        for reason in model.reasons:
            lines.append(f"  - {one_line(reason, limit=120)}")

    lines.append("")
    lines.append(f"Note: {model.honest_ceiling_note}")
    if model.verified_from:
        lines.append(f"verified_from: {one_line(model.verified_from, limit=100)}")
    return "\n".join(lines)
