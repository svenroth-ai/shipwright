#!/usr/bin/env python3
"""Single-source terminal control-char sanitizer for triage render surfaces.

Extracted (a1-6 follow-up) from the byte-identical copies that lived in
``aggregate_triage.py`` (renders ``triage_inbox.md``) and ``triage_cli.py``
(``triage_cli list``), so the C0/C1 stripping policy cannot drift between the
two TTY-facing producers. Both import ``strip_control_chars`` as their local
``_strip_control_chars``.
"""

from __future__ import annotations


def strip_control_chars(text: str) -> str:
    """Strip terminal control sequences while preserving newlines and tabs.

    Drops C0 (``0x00``-``0x1F``, ``0x7F``) AND C1 (``0x80``-``0x9F``, incl.
    ``0x9B`` CSI) control chars — a TTY pager (``less`` / ``cat``) would
    otherwise execute them (F31; C1 per the Gemini-HIGH plan review). The threat
    is a malformed / attacker-influenceable producer: an embedded ESC/BEL in a
    ``launchPayload``, or a GitHub workflow name / branch in a triage title.
    Non-control Unicode (``>= 0xA0``) survives, preserving umlauts / CJK /
    em-dashes.
    """
    return "".join(
        ch for ch in text
        if ch in ("\n", "\t") or (0x20 <= ord(ch) < 0x7F) or ord(ch) >= 0xA0
    )
