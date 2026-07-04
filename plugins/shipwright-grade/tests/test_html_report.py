"""Tests for html_report — structure, determinism, theme, n/a semantics.

The escape-only / injection security tests live in ``test_html_security.py``
(the headline requirement, kept in its own file). This file covers the
self-contained document, determinism, theme/responsiveness, n/a semantics and
section coverage.
"""

from __future__ import annotations

import re

from html_report import render_html
from report_model import build_report_model
from support import GEN_A, GEN_B, mixed_dims, mixed_model
from types import SimpleNamespace


def _html(**kw):
    return render_html(mixed_model(**kw), generated_at=GEN_A)


# --------------------------------------------------------------------------- #
# Self-contained / no external-request surface (GPT #3).
# --------------------------------------------------------------------------- #
class TestSelfContained:
    def test_is_a_full_html_document(self):
        out = _html()
        assert out.lstrip().lower().startswith("<!doctype html>")
        assert "<html" in out and "</html>" in out

    def test_restrictive_meta_csp(self):
        out = _html()
        assert 'http-equiv="Content-Security-Policy"' in out
        assert "default-src 'none'" in out
        assert "style-src 'unsafe-inline'" in out

    def test_no_external_request_surface(self):
        out = _html(hostile=True)
        low = out.lower()
        assert "<script" not in low          # zero inline/loaded JS
        assert "<iframe" not in low
        assert not re.search(r'src\s*=\s*["\']https?:', low)
        assert not re.search(r'href\s*=\s*["\']https?:', low)
        assert not re.search(r'href\s*=\s*["\']javascript:', low)
        assert "srcset=" not in low
        assert "@import" not in low
        assert "url(http" not in low
        assert "ping=" not in low
        assert not re.search(r'\baction\s*=', low)
        assert "http-equiv=\"refresh\"" not in low

    def test_no_model_driven_href_anchor_is_text(self):
        # The open-standard anchor is rendered as text, never as a link target.
        out = _html()
        low = out.lower()
        assert "OpenSSF Scorecard" in out          # anchor text present
        assert "<a " not in low and "<a>" not in low   # zero anchor elements
        assert "href=" not in low                       # zero link targets


# --------------------------------------------------------------------------- #
# Determinism (byte-identical scored content; timestamp only in footer).
# --------------------------------------------------------------------------- #
class TestDeterminism:
    def test_idempotent(self):
        m = mixed_model()
        assert render_html(m, generated_at=GEN_A) == render_html(m, generated_at=GEN_A)

    def test_scored_content_byte_identical_across_timestamps(self):
        m = mixed_model()
        a = render_html(m, generated_at=GEN_A).replace(GEN_A, "X")
        b = render_html(m, generated_at=GEN_B).replace(GEN_B, "X")
        assert a == b

    def test_generated_at_is_the_only_variable(self):
        out = render_html(mixed_model(), generated_at=GEN_A)
        assert GEN_A in out
        assert out.count(GEN_A) == 1


# --------------------------------------------------------------------------- #
# Theme-aware + responsive (AC).
# --------------------------------------------------------------------------- #
class TestThemeAndResponsive:
    def test_dark_mode_media_query_present(self):
        assert "prefers-color-scheme: dark" in _html()

    def test_responsive_viewport_and_scroll_container(self):
        out = _html()
        assert 'name="viewport"' in out
        assert "overflow-x" in out          # wide content scrolls internally
        assert "overflow-wrap" in out        # long hostile tokens can't overflow


# --------------------------------------------------------------------------- #
# n/a semantics (GPT #12): N/A, never 0/…; funnel panel; reasons cap.
# --------------------------------------------------------------------------- #
class TestNaSemantics:
    def test_na_dimension_shows_na_not_zero(self):
        # Every n/a dimension must render "N/A" in its score cell — never a
        # numeric 0. Count the score cells directly so a broken impl that
        # rendered n/a as 0.00 / 0.50 / "0/20" cannot slip through.
        model = mixed_model()
        out = render_html(model, generated_at=GEN_A)
        na_count = model.na_count
        assert na_count == 4
        assert out.count('class="dim-score">N/A<') == na_count
        # The measurable dims render a numeric score, not N/A.
        measurable = len(model.dimensions) - na_count
        assert len(re.findall(r'class="dim-score">\d', out)) == measurable
        assert "0/15" not in out          # never the "0/denominator" failure form

    def test_reasons_capped_at_three(self):
        # AC: top 1–3 reasons — a 5-reason model must render at most 3.
        report = SimpleNamespace(
            grade="C", score=72.0, gradeable=True, verdict="v", band_label="b",
            dimensions=mixed_dims(),
            reasons=[f"reason number {i}" for i in range(5)], verified_from="vf")
        routing = SimpleNamespace(effective_mode="heuristic", state="absent",
                                  reason="r")
        model = build_report_model(
            grade_report=report, routing=routing, target_display="r",
            head_sha="abc", events_truncated=False)
        out = render_html(model, generated_at=GEN_A)
        assert "reason number 0" in out and "reason number 2" in out
        assert "reason number 3" not in out and "reason number 4" not in out

    def test_would_light_panel_lists_na_dims(self):
        out = _html()
        assert "would light up" in out.lower()
        for label in ("Change reconciliation", "Security", "Dependency hygiene"):
            assert label in out


# --------------------------------------------------------------------------- #
# Section coverage (hero + cards + reasons + disclaimer + provenance + CTA).
# --------------------------------------------------------------------------- #
class TestSections:
    def test_hero_has_grade_score_verdict_and_mode_badge(self):
        out = _html()
        assert ">B<" in out or ">B</" in out         # big letter grade
        assert "82.5" in out                         # score
        assert "Controlled, minor gaps" in out       # verdict
        assert "heuristic" in out.lower()            # mode badge
        assert "3 of 7" in out or "3 / 7" in out     # measured-controls count

    def test_dimension_cards_show_anchor_and_provenance(self):
        out = _html()
        assert "Requirement traceability" in out
        assert "ISO/IEC/IEEE 29148" in out           # open-standard anchor
        assert "route/feature inference" in out       # provenance source

    def test_top_reasons_present(self):
        assert "1/2 changes linked" in _html()

    def test_honest_ceiling_disclaimer_and_provenance_stamp(self):
        out = _html()
        assert "does not verify behaviour" in out
        assert "shipwright-grade heuristic @ deadbeefcafe1234" in out

    def test_cta_placeholder_present(self):
        assert "grade" in _html().lower()             # CTA copy present
