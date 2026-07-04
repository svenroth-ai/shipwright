"""Terminal card — control-stripping security (AC: terminal control-stripped).

The compact terminal card already existed (G1); G3 adds the missing security
coverage the AC calls for: a hostile commit subject / filename must not inject
ANSI colour, OSC-8 hyperlinks, bidi overrides or raw control bytes into the
terminal (GPT #15 / Trojan-source).
"""

from __future__ import annotations

from types import SimpleNamespace

from render_terminal import render_terminal
from report_model import build_report_model

_ANSI = "\x1b[31mRED\x1b[0m"
_OSC8 = "\x1b]8;;https://evil.example\x07link\x1b]8;;\x07"
_BIDI = chr(0x202E) + "evil" + chr(0x202C)
_CTRL = "a\x07b\x00c"


def _hostile_model():
    hostile = f"pkg {_ANSI} {_OSC8} {_BIDI} {_CTRL}"
    dims = [SimpleNamespace(
        key="security", label=f"Security {_ANSI}", weight=0.1, score=1.0,
        status="ok", anchor="a", detail=hostile)]
    report = SimpleNamespace(
        grade="B", score=82.0, gradeable=True, verdict=hostile,
        band_label="b", dimensions=dims, reasons=[hostile],
        verified_from=hostile)
    routing = SimpleNamespace(effective_mode="heuristic", state="absent", reason="r")
    return build_report_model(
        grade_report=report, routing=routing, target_display=hostile,
        head_sha="abc", events_truncated=False, static_test_inventory=hostile)


class TestTerminalControlStripping:
    def test_no_ansi_osc_control_or_bidi_in_card(self):
        out = render_terminal(_hostile_model())
        assert "\x1b" not in out          # ESC / ANSI / OSC-8 introducer
        assert "\x07" not in out          # BEL
        assert "\x00" not in out          # NUL
        assert chr(0x202E) not in out     # bidi override
        assert "evil.example" not in out  # OSC-8 link target

    def test_card_still_renders_grade_and_dimensions(self):
        out = render_terminal(_hostile_model())
        assert "Control Grade: B" in out
        assert "Security" in out
