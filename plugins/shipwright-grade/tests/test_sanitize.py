"""Tests for sanitize — hostile-string neutralisation."""

from __future__ import annotations

from sanitize import one_line, strip_terminal


class TestStripTerminal:
    def test_strips_csi_color_codes(self):
        assert strip_terminal("\x1b[31mRED\x1b[0m") == "RED"

    def test_strips_osc8_hyperlink(self):
        payload = "\x1b]8;;https://evil.example\x07click\x1b]8;;\x07"
        out = strip_terminal(payload)
        assert "evil.example" not in out
        assert out == "click"

    def test_strips_control_chars(self):
        assert strip_terminal("a\x07b\x00c") == "abc"

    def test_strips_bidi_override(self):
        payload = "safe" + chr(0x202E) + "evil" + chr(0x202C)
        out = strip_terminal(payload)
        assert chr(0x202E) not in out and chr(0x202C) not in out
        assert out == "safeevil"

    def test_keeps_plain_text_and_unicode(self):
        assert strip_terminal("héllo wörld ✅") == "héllo wörld ✅"

    def test_empty(self):
        assert strip_terminal("") == ""


class TestOneLine:
    def test_collapses_newlines_and_tabs(self):
        assert one_line("a\n\nb\tc") == "a b c"

    def test_truncates_long_input(self):
        out = one_line("x" * 500, limit=10)
        assert len(out) == 10
        assert out.endswith("…")

    def test_sanitizes_before_collapsing(self):
        assert one_line("\x1b[31mfoo\x1b[0m\nbar") == "foo bar"
