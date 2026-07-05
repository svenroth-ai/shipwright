"""Tests for html_report — structure, determinism, theme, n/a semantics.

The escape-only / injection security tests live in ``test_html_security.py``
(the headline requirement, kept in its own file). This file covers the
self-contained document, determinism, theme/responsiveness, n/a semantics and
section coverage.
"""

from __future__ import annotations

import re

from html_report import render_html
from report_copy import CTA_URL as _CTA_URL
from report_copy import DIMENSION_COPY
from report_model import _DIM_META, build_report_model
from support import GEN_A, GEN_B, mixed_dims, mixed_model
from types import SimpleNamespace


def _html(**kw):
    return render_html(mixed_model(**kw), generated_at=GEN_A)


def _card(out: str, label: str) -> str:
    """Return the single <article> whose dimension label matches (each article is
    matched independently, so a non-greedy regex can't span multiple cards)."""
    for article in re.findall(r"<article\b.*?</article>", out, re.S):
        if label in article:
            return article
    raise AssertionError(f"no dimension card for {label!r}")


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
        # The ONLY external reference allowed is the single static CTA link (a
        # user-initiated navigation, not an auto-fetch). Everything else — even
        # under hostile input — must be absent.
        out = _html(hostile=True)
        low = out.lower()
        assert "<script" not in low          # zero inline/loaded JS
        assert "<iframe" not in low
        assert not re.search(r'src\s*=\s*["\']https?:', low)   # no auto-fetch src
        assert not re.search(r'href\s*=\s*["\']javascript:', low)
        assert "srcset=" not in low
        assert "@import" not in low
        assert "url(http" not in low
        assert "ping=" not in low
        assert not re.search(r'\baction\s*=', low)
        assert "http-equiv=\"refresh\"" not in low
        # Every href in the document is the trusted CTA URL — nothing else.
        assert set(re.findall(r'href="([^"]*)"', out)) == {_CTA_URL}

    def test_all_links_are_the_trusted_cta(self):
        # The CTA links (understand + fix) are the ONLY <a> elements — exactly two
        # in the current design — all pointing at the hardcoded CTA and hardened.
        out = _html()
        low = out.lower()
        anchors = re.findall(r"<a\s", low)
        assert len(anchors) == 2
        assert set(re.findall(r'href="([^"]*)"', out)) == {_CTA_URL}
        assert low.count('rel="noopener noreferrer"') == len(anchors)
        assert low.count('target="_blank"') == len(anchors)

    def test_no_anchors_in_dimension_cards(self):
        # Model/repo content must NEVER become a link: every <a> lives in the CTA
        # section, and the dimension cards contain zero anchors (defends the
        # "no model-controlled field becomes a link" acceptance criterion).
        out = _html(hostile=True)
        for article in re.findall(r"<article\b.*?</article>", out, re.S):
            assert "<a " not in article and "href=" not in article
        # All anchors are inside the single CTA section.
        cta = re.search(r'<section class="cta">.*?</section>', out, re.S).group(0)
        assert cta.count("<a ") == out.count("<a ")


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

    def test_missing_panel_lists_na_dims(self):
        out = _html()
        assert "What your repo is missing" in out
        assert "your grade goes up" in out.lower()
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

    def test_dimension_cards_teach_in_plain_language(self):
        out = _html()
        assert "Requirement traceability" in out          # engine label
        # The plain-language question + expandable "why it matters" are present…
        assert "Can you explain why every piece of code exists?" in out
        assert "<details class=\"why\">" in out
        assert "Why it matters" in out
        assert "Backed by:" in out
        # …and the concrete scenario copy for the differentiator is rendered.
        assert "fix the login bug" in out

    def test_anchor_and_provenance_surfaced_but_off_the_face(self):
        # Spec: each dim surfaces its open-standard anchor + provenance
        # (source/mode/freshness). The redesign keeps them — but tucked INSIDE
        # the expandable (after <summary>), so the jargon never leads the card.
        out = _html()
        rt = re.search(r"<article\b.*?Requirement traceability.*?</article>",
                       out, re.S).group(0)
        # The always-visible one-liner is the plain copy, NOT the standard.
        visible = re.search(r'class="dim-visible">([^<]*)<', rt).group(1)
        assert "trace back to a reason" in visible
        assert "ISO/IEC/IEEE" not in visible
        # The anchor + provenance ARE surfaced, but only after the <summary>.
        assert "ISO/IEC/IEEE 29148" in rt
        assert "How this was measured" in rt
        assert "route/feature inference" in rt                 # provenance source
        assert rt.index("ISO/IEC/IEEE 29148") > rt.index("<summary>")

    def test_na_card_shows_reframe_not_engine_jargon(self):
        out = _html()
        # The n/a reconciliation card shows the jargon-free reframe, and the raw
        # engine DETAIL ("not measurable — needs per-change behavior-impact") is
        # suppressed on the face. (Apostrophe-free fragment — ' HTML-escapes.)
        # NB the technical provenance ("…re-verification (BP-2)") is still
        # surfaced deep inside the expandable — that's the honest audit trail.
        assert "measure this from the outside" in out
        rec = _card(out, "Change reconciliation")
        assert "needs per-change behavior-impact" not in rec   # engine detail gone
        # The reframe is on the face (before the expandable summary).
        assert rec.index("measure this from the outside") < rec.index("<summary>")

    def test_measured_card_shows_in_your_repo_detail(self):
        out = _html()
        # A measured dimension surfaces its concrete finding under "In your repo".
        assert "In your repo:" in out

    def test_top_reasons_present(self):
        assert "1/2 changes linked" in _html()

    def test_honest_ceiling_disclaimer_and_provenance_stamp(self):
        out = _html()
        assert "does not verify behaviour" in out
        assert "shipwright-grade heuristic @ deadbeefcafe1234" in out

    def test_cta_has_two_steps_understand_and_fix(self):
        out = _html()
        cta = re.search(r'<section class="cta">.*?</section>', out, re.S)
        assert cta, "CTA section present"
        cta = cta.group(0)
        # Two next steps: understand (Masterclass) + fix (adopt).
        assert "Masterclass" in cta
        assert "Understand it" in cta and "Fix it" in cta
        assert "/shipwright-adopt" in cta
        # "certify" is gone from the CTA (stays only in the honest-ceiling note).
        assert "certify" not in cta.lower()
        # Both CTA links point at the trusted URL.
        assert cta.count(f'href="{_CTA_URL}"') == 2


# --------------------------------------------------------------------------- #
# Copy integrity — the marketing instrument's honesty + jargon-free coverage
# are load-bearing (over-claiming gets debunked), so pin them directly.
# --------------------------------------------------------------------------- #
class TestCopyIntegrity:
    def test_every_engine_dimension_has_plain_copy(self):
        # A dimension key absent from DIMENSION_COPY would fall back to the raw
        # engine detail as the card face — the exact jargon this redesign kills.
        assert set(_DIM_META) <= set(DIMENSION_COPY)

    def test_load_bearing_honest_hedges_are_present(self):
        # Each phrase is a claim the spec says gets debunked if wrong — a future
        # edit that over-claims (drops the hedge) must fail here.
        assert ("or explicitly classified"
                in DIMENSION_COPY["requirement_traceability"]["improves"])
        assert ("flags every behavior-affecting change"
                in DIMENSION_COPY["change_reconciliation"]["improves"])
        assert ("not how much of your code they cover"
                in DIMENSION_COPY["test_health"]["limit"])
        assert ("unchecked growth is prevented"
                in DIMENSION_COPY["maintainability"]["improves"])
        # …and reconciliation must NOT promise a hard block it can't make today.
        assert "won't let it through" not in DIMENSION_COPY[
            "change_reconciliation"]["improves"]
