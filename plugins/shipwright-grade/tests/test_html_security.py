"""Security tests for html_report — the headline requirement.

The report renders UNTRUSTED repo strings. These tests prove escape-only output:
XSS / event-handler / ``javascript:`` / ANSI / OSC-8 / bidi payloads fed through
every text-bearing model field are rendered inert — both as literal-substring
checks AND as a parser-based assertion that the payload contributed **zero live
DOM nodes** (plan §14 A / GPT #3/#4/#15).
"""

from __future__ import annotations

import re
from html.parser import HTMLParser
from types import SimpleNamespace

from html_report import _CTA_URL, el, render_html
from report_model import build_report_model
from support import GEN_A, dim, mixed_model


def test_attribute_values_are_control_stripped_and_escaped():
    # The attribute seam is as strong as the text seam: control/ANSI/bidi are
    # stripped and quotes/brackets escaped, so an attribute can never be a weaker
    # context than a text node (defense-in-depth for any future attribute value).
    out = str(el("a", "x", href='"><svg/onload=alert(1)>\x1b[31m' + chr(0x202E)))
    assert '"><svg' not in out          # quote/bracket breakout escaped
    assert "&quot;&gt;&lt;svg" in out
    assert "\x1b" not in out and chr(0x202E) not in out   # control/bidi stripped


class _TagCollector(HTMLParser):
    """Collects every start-tag name (and any <a> hrefs) so a test can prove
    which elements — and which link targets — the document actually contains."""

    def __init__(self):
        super().__init__()
        self.tags: list[str] = []
        self.hrefs: list[str] = []

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        if tag == "a":
            self.hrefs += [v for k, v in attrs if k == "href"]

    handle_startendtag = handle_starttag


def _hostile_html():
    return render_html(mixed_model(hostile=True), generated_at=GEN_A)


class TestEscapeOnly:
    def test_script_payload_is_escaped_not_injected(self):
        out = _hostile_html()
        assert "<script>alert(1)</script>" not in out
        assert "&lt;script&gt;" in out

    def test_event_handler_payload_is_inert(self):
        out = _hostile_html()
        # The onerror img-injection must be escaped, never a live <img> tag.
        assert "<img src=x onerror=" not in out
        assert "&lt;img" in out

    def test_javascript_uri_not_in_attribute(self):
        out = _hostile_html()
        assert not re.search(r'(href|src)\s*=\s*["\']?javascript:', out.lower())

    def test_ansi_and_control_and_bidi_stripped(self):
        out = _hostile_html()
        assert "\x1b" not in out          # ESC / ANSI / OSC-8 gone
        assert "\x07" not in out          # BEL gone
        assert "\x00" not in out          # NUL gone
        assert chr(0x202E) not in out     # bidi override gone
        assert "evil.example" not in out  # OSC-8 target gone

    def test_hostile_payload_contributes_zero_live_nodes(self):
        # Parser-based inertness: with hostile input the document must contain no
        # fetch/script element at all, and the ONLY <a> must be the renderer's
        # static CTA link — hostile strings never become an element or a URL.
        collector = _TagCollector()
        collector.feed(_hostile_html())
        seen = set(collector.tags)
        for forbidden in ("script", "img", "iframe", "svg", "form",
                          "object", "embed", "link"):
            assert forbidden not in seen, f"hostile input produced a <{forbidden}>"
        assert collector.tags.count("a") == 2            # exactly the 2 CTA anchors…
        assert set(collector.hrefs) == {_CTA_URL}        # …all the trusted CTA
        # Sanity: the document really was parsed (structural tags are present).
        assert {"html", "head", "body", "main", "a"} <= seen

    def test_every_text_field_routes_through_escaper(self):
        # Feed a raw HTML sentinel through each text-bearing model field and
        # prove none reaches the document un-escaped (the "one seam" guarantee —
        # a forgotten wrap would surface here).
        sentinel = "<b>PWN</b>"
        report = SimpleNamespace(
            grade="B", score=82.5, gradeable=True, verdict=sentinel,
            band_label=sentinel,
            dimensions=[dim("security", "Security", 0.1, 0.9,
                            anchor=sentinel, detail=sentinel)],
            reasons=[sentinel], verified_from=sentinel)
        routing = SimpleNamespace(effective_mode="heuristic", state="absent",
                                  reason=sentinel)
        model = build_report_model(
            grade_report=report, routing=routing, target_display=sentinel,
            head_sha="abc", events_truncated=False, static_test_inventory=sentinel,
            network_note=sentinel, network_enrichments=(sentinel,),
            network_enabled=True)
        out = render_html(model, generated_at=GEN_A)
        assert "<b>PWN</b>" not in out
        assert "&lt;b&gt;PWN&lt;/b&gt;" in out
