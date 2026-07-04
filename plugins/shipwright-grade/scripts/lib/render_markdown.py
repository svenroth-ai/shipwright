"""render_markdown — a deterministic Markdown card from the view-model.

Like the terminal renderer, this consumes the typed :class:`ReportModel`
directly (no markdown-as-IR) and sanitises every repo-derived string. The
Markdown intentionally avoids raw HTML; the escape-only HTML report lands in G3.
"""

from __future__ import annotations

from report_model import DimensionView, ReportModel
from sanitize import one_line

_STATUS_EMOJI = {"ok": "✅", "gap": "⚠️", "n/a": "▫️"}


def _fmt_score(score: float | None) -> str:
    return "N/A" if score is None else f"{score:.2f}"


def _md_escape_cell(text: str) -> str:
    return one_line(text, limit=120).replace("|", "\\|")


def _dim_row(dim: DimensionView) -> str:
    emoji = _STATUS_EMOJI.get(dim.status, "•")
    label = _md_escape_cell(dim.label)
    weight = f"{dim.weight * 100:.0f}%"
    detail = _md_escape_cell(dim.detail)
    return f"| {emoji} {label} | {weight} | {_fmt_score(dim.score)} | {detail} |"


def render_markdown(model: ReportModel) -> str:
    """Return the Markdown Control Grade card for ``model``."""
    score = "N/A" if model.score is None else f"{model.score:.1f}/100"
    total = len(model.dimensions)
    out: list[str] = []
    out.append(f"# Control Grade: {model.grade} ({score})")
    out.append("")
    out.append(
        f"**{model.mode}** — {model.measurable_count} of {total} controls measured  "
    )
    out.append(f"**Repository:** {one_line(model.target_display, limit=80)}  ")
    out.append(f"**Mode:** {model.mode} ({one_line(model.routing_reason, limit=120)})  ")
    out.append(f"**Verdict:** {one_line(model.verdict, limit=200)}")
    out.append("")
    out.append(f"## Dimensions ({model.measurable_count} of {total} measurable)")
    out.append("")
    out.append("| Dimension | Weight | Score | Detail |")
    out.append("|---|---|---|---|")
    for dim in model.dimensions:
        out.append(_dim_row(dim))
    out.append("")

    if model.controls_shipwright_would_light:
        out.append("## Controls Shipwright would light up")
        out.append("")
        for label in model.controls_shipwright_would_light:
            out.append(f"- {one_line(label, limit=60)}")
        out.append("")

    if model.static_test_inventory:
        out.append(f"**Test inventory:** {one_line(model.static_test_inventory, limit=160)}")
        out.append("")

    if model.reasons:
        out.append("## Top reasons")
        out.append("")
        for reason in model.reasons:
            out.append(f"- {one_line(reason, limit=160)}")
        out.append("")

    if model.network_enabled and model.network_enrichments:
        left = ", ".join(one_line(e, limit=60) for e in model.network_enrichments)
        out.append(f"**Network:** enriched via {left}")
        out.append("")
    elif model.network_note:
        out.append(f"**Network:** {one_line(model.network_note, limit=140)}")
        out.append("")

    out.append(f"> {model.honest_ceiling_note}")
    if model.verified_from:
        out.append("")
        out.append(f"`verified_from: {one_line(model.verified_from, limit=120)}`")
    return "\n".join(out)
