"""html_report — the stunning, self-contained HTML Control Grade report.

This is the public lead-magnet artifact **and it renders UNTRUSTED repo
strings**, so escape-only output is the #1 requirement, not the polish
(plan §14 A / GPT #3/#4/#15). Renders FROM the typed :class:`ReportModel`
view-model — never parses another renderer's text.

**The security seam is structural, not disciplinary** (external-review High
finding, both models): the document is assembled with :func:`el`, an
auto-escaping element builder. A child that is a :class:`_Raw` (produced only by
``el`` itself, or an explicit trusted literal) is emitted verbatim; **every other
child is HTML-escaped as a text node by default**. So a forgotten wrap on a
model-derived string is escaped, not injected — safety no longer depends on
remembering an escape call at each of dozens of seams. Attribute values are
always escaped. Text cleaning uses :func:`sanitize.strip_terminal` (removes
ANSI/OSC-8/bidi/control, *preserves* newlines — GPT #4/Gemini #2: don't flatten
multi-line reasons); the CSS renders the newlines and defuses long tokens.

Determinism: the only non-scored value is ``generated_at``, injected once into
the footer. Same repo state → byte-identical scored content (AC).
"""

from __future__ import annotations

import html as _htmllib

from _html_styles import META_CSP, STYLES
from report_model import DimensionView, ReportModel
from sanitize import strip_terminal


class _Raw(str):
    """Marks a string as trusted, already-escaped HTML (never re-escaped)."""

    __slots__ = ()


def _text(value: object) -> str:
    """Untrusted → safe text node: strip control/ANSI/bidi, then HTML-escape."""
    return _htmllib.escape(strip_terminal(str(value)), quote=True)


def _attrs(attrs: dict[str, object]) -> str:
    out = []
    for key, val in attrs.items():
        if val is None:
            continue
        name = key.rstrip("_").replace("_", "-")
        out.append(f' {name}="{_htmllib.escape(str(val), quote=True)}"')
    return "".join(out)


def el(tag: str, *children: object, **attrs: object) -> _Raw:
    """Build an element; ``_Raw`` children pass through, all others are escaped."""
    inner = "".join(
        str(c) if isinstance(c, _Raw) else _text(c) for c in children
    )
    return _Raw(f"<{tag}{_attrs(attrs)}>{inner}</{tag}>")


_GRADE_CLASS = {"A": "grade-a", "B": "grade-b", "C": "grade-c",
                "D": "grade-d", "F": "grade-f"}
_STATUS = {"ok": ("status-ok", "OK"), "gap": ("status-gap", "GAP"),
           "n/a": ("status-na", "N/A")}

_CTA_COPY = (
    "These N/A controls aren't failures — they're the controls a cold repo "
    "can't prove from the outside. Adopting Shipwright lights them up, so you "
    "can raise your grade and certify it."
)
_FUNNEL_LEDE = (
    "N/A on a cold repo — excluded from the score, never counted as a failed 0. "
    "These are the controls Shipwright would light up once adopted."
)


def _fmt_score(score: float | None) -> str:
    return "N/A" if score is None else f"{score:.2f}"


def _hero(m: ReportModel) -> _Raw:
    measured = f"{m.measurable_count} of {len(m.dimensions)} controls measured"
    score_txt = "N/A" if m.score is None else f"{m.score:.1f}"
    grade = el("div", m.grade, class_=f"grade {_GRADE_CLASS.get(m.grade, 'grade-na')}")
    body = el(
        "div",
        el("div", "Control Grade", class_="eyebrow"),
        el("div",
           el("span", score_txt, class_="score"),
           el("span", "/100" if m.score is not None else "", class_="score-max"),
           class_="score-row"),
        el("p", m.verdict, class_="verdict"),
        el("div",
           el("span", m.mode, class_="badge badge-mode"),
           el("span", measured, class_="badge"),
           class_="badges"),
        class_="hero-body",
    )
    return el(
        "header",
        el("div", grade, body, class_="hero"),
        el("div", "Repository: ", el("span", m.target_display), class_="target"),
        class_="hero-wrap",
    )


def _dim_card(d: DimensionView) -> _Raw:
    cls, label = _STATUS.get(d.status, ("status-na", d.status.upper()))
    prov = d.provenance
    bits = [prov.source, prov.mode]
    if prov.freshness and prov.freshness != "n/a":
        bits.append(f"@ {prov.freshness}")
    if prov.sampled:
        bits.append("sampled")
    if prov.truncated:
        bits.append("truncated")
    children = [
        el("div",
           el("span", label, class_=f"pill {cls}"),
           el("span", f"{d.weight * 100:.0f}%", class_="weight"),
           el("span", _fmt_score(d.score), class_="dim-score"),
           class_="dim-head"),
        el("h3", d.label, class_="dim-label"),
        el("div", d.anchor, class_="anchor"),
        el("p", d.detail, class_="detail"),
        el("div", " · ".join(bits), class_="prov"),
    ]
    if d.would_light_up and prov.disabled_enrichments:
        children.append(
            el("div", "Would light: " + ", ".join(prov.disabled_enrichments),
               class_="disabled-enrich"))
    return el("article", *children, class_=f"dim-card {cls}")


def _dimensions(m: ReportModel) -> _Raw:
    grid = el("div", *(_dim_card(d) for d in m.dimensions), class_="dim-grid")
    return el(
        "section",
        el("h2", f"Dimensions — {m.measurable_count} of {len(m.dimensions)} "
                 "measurable", class_="section-title"),
        el("div", grid, class_="scroll-x"),
        class_="dimensions",
    )


def _would_light(m: ReportModel) -> _Raw:
    if not m.controls_shipwright_would_light:
        return _Raw("")
    items = (el("li", label) for label in m.controls_shipwright_would_light)
    return el(
        "section",
        el("h2", "Controls Shipwright would light up", class_="section-title"),
        el("div",
           el("p", _FUNNEL_LEDE, class_="panel-lede"),
           el("ul", *items, class_="light-list"),
           class_="funnel"),
        class_="funnel-wrap",
    )


def _reasons(m: ReportModel) -> _Raw:
    if not m.reasons:
        return _Raw("")
    # AC: top 1–3 fixable reasons. The engine already caps at 3, but the
    # renderer enforces the display bound independently of upstream.
    items = (el("li", reason) for reason in m.reasons[:3])
    return el(
        "section",
        el("h2", "Top fixable reasons", class_="section-title"),
        el("ol", *items, class_="reasons"),
        class_="reasons-wrap",
    )


def _prov_row(key: str, value: object) -> _Raw:
    return el("div", el("span", key, class_="k"), el("span", value, class_="v"),
              class_="prov-row")


def _provenance(m: ReportModel) -> _Raw:
    rows = []
    if m.static_test_inventory:
        rows.append(_prov_row("Test inventory:", m.static_test_inventory))
    if m.network_enabled and m.network_enrichments:
        rows.append(_prov_row(
            "Network:", "enriched via " + ", ".join(m.network_enrichments)))
    elif m.network_note:
        rows.append(_prov_row("Network:", m.network_note))
    rows.append(_prov_row("verified_from:", m.verified_from))
    return el("section", *rows, class_="provenance")


def _disclaimer(m: ReportModel) -> _Raw:
    return el("aside",
              el("strong", "Honest ceiling. ", class_="disc-title"),
              el("span", m.honest_ceiling_note),
              class_="disclaimer")


def _cta() -> _Raw:
    return el(
        "section",
        el("h2", "Raise your grade", class_="cta-title"),
        el("p", _CTA_COPY, class_="cta-copy"),
        el("div", "Grade your repo → adopt → certify", class_="cta-chip"),
        class_="cta",
    )


def _footer(generated_at: str | None) -> _Raw:
    return el("footer",
              el("span", f"Generated {generated_at or '—'}", class_="stamp"),
              class_="page-footer")


def _document(title: str, body: _Raw) -> str:
    return (
        "<!doctype html>\n"
        '<html lang="en">\n<head>\n'
        '<meta charset="utf-8">\n'
        f'<meta http-equiv="Content-Security-Policy" content="{META_CSP}">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{_text(title)}</title>\n"
        f"<style>{STYLES}</style>\n"
        "</head>\n<body>\n"
        f"{body}\n"
        "</body>\n</html>\n"
    )


def render_html(model: ReportModel, *, generated_at: str | None = None) -> str:
    """Return the self-contained HTML Control Grade report for ``model``.

    ``generated_at`` is the only non-deterministic input and appears solely in
    the footer; pass ``None`` (default) or a fixed value for byte-stable output.
    """
    body = el(
        "main",
        _hero(model),
        _dimensions(model),
        _would_light(model),
        _reasons(model),
        _disclaimer(model),
        _cta(),
        _provenance(model),
        _footer(generated_at),
        class_="page",
    )
    title = f"Control Grade {model.grade} — {strip_terminal(str(model.target_display))}"
    return _document(title, body)
