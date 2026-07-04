"""Renderers surface the G2 network provenance line (both formats, both states)."""

from __future__ import annotations

from report_model import build_report_model
from render_markdown import render_markdown
from render_terminal import render_terminal
from types import SimpleNamespace


def _model(**net):
    report = SimpleNamespace(
        grade="B", score=82.0, gradeable=True, verdict="v", band_label="b",
        dimensions=[SimpleNamespace(key="security", label="Security", weight=0.1,
                                    score=1.0, status="ok", anchor="a", detail="0 open")],
        reasons=[], verified_from="heuristic @ abc",
    )
    routing = SimpleNamespace(effective_mode="heuristic", state="absent", reason="r")
    return build_report_model(
        grade_report=report, routing=routing, target_display="repo",
        head_sha="abc", events_truncated=False, **net)


def test_enabled_shows_enrichments():
    model = _model(network_enabled=True,
                   network_enrichments=("code-scanning SARIF (o/r)", "CI JUnit (o/r)"))
    for text in (render_terminal(model), render_markdown(model)):
        assert "enriched via" in text
        assert "code-scanning SARIF (o/r)" in text


def test_local_only_shows_note():
    model = _model(network_enabled=False,
                   network_note="local-only (default) — pass --allow-network to enrich")
    for text in (render_terminal(model), render_markdown(model)):
        assert "local-only" in text
