#!/usr/bin/env python3
"""Single-source terminal control-char sanitizer for triage render surfaces.

Extracted (a1-6 follow-up) from the byte-identical copies that lived in
``aggregate_triage.py`` (renders ``triage_inbox.md``) and ``triage_cli.py``
(``triage_cli list``), so the C0/C1 stripping policy cannot drift between the
two TTY-facing producers. ``aggregate_triage`` imports ``strip_control_chars``
directly; the CLI listing reaches it through ``lib.triage_render``.
"""

from __future__ import annotations

import unicodedata


def strip_control_chars(text: str) -> str:
    """Strip terminal control sequences while preserving newlines and tabs.

    Drops C0 (``0x00``-``0x1F``, ``0x7F``) AND C1 (``0x80``-``0x9F``, incl.
    ``0x9B`` CSI) control chars — a TTY pager (``less`` / ``cat``) would
    otherwise execute them (F31; C1 per the Gemini-HIGH plan review). The threat
    is a malformed / attacker-influenceable producer: an embedded ESC/BEL in a
    ``launchPayload``, or a GitHub workflow name / branch in a triage title.
    Non-control Unicode (``>= 0xA0``) survives, preserving umlauts / CJK /
    em-dashes — including invisible joiners, which is why a caller deciding
    whether a field is blank must use :func:`is_visually_empty`.
    """
    return "".join(
        ch for ch in text
        if ch in ("\n", "\t") or (0x20 <= ord(ch) < 0x7F) or ord(ch) >= 0xA0
    )


def strip_control_chars_inline(text: str) -> str:
    """Same policy, for a field that must stay on ONE line.

    ``strip_control_chars`` keeps ``\\n`` and ``\\t`` because a launch payload
    is multi-line by design. A title, a source or a decision reason is not:
    a stored newline there lets whoever wrote it forge extra rows in a
    line-oriented listing — output spoofing rather than escape execution, and
    the sanitizer above cannot catch it without breaking payload rendering.
    Interior whitespace collapses to single spaces so nothing runs together.

    Invisible-but-truthy content is NOT filtered here — see
    :func:`is_visually_empty`. An earlier attempt dropped Unicode category
    ``Cf``, which was wrong twice: it split every ZWJ emoji sequence (U+200D)
    and changed Persian / Devanagari word rendering (U+200C), while still
    missing U+FE0F and the combining marks, which are ``Mn``. Enumerating
    invisible characters loses; asking whether anything visible remains wins.
    """
    return " ".join(strip_control_chars(text).split())


def is_visually_empty(text: str) -> bool:
    """True when ``text`` would render as blank space, however it is spelled.

    A field can be non-empty to ``bool()`` and still show the reader nothing:
    a zero-width space, a variation selector, a combining mark, a Hangul
    filler, a braille blank. Callers that fall back to a placeholder must
    branch on this, not on truthiness — otherwise the placeholder silently
    fails to fire and the line renders blank.

    The test is by Unicode *property*, not by a character list: a string is
    visually empty when every character is a control (``C``), a mark (``M``)
    or a separator (``Z``).

    Known limit, stated rather than papered over: characters that render blank
    in most fonts while being letters or symbols by property — U+3164 HANGUL
    FILLER (``Lo``), U+2800 BRAILLE PATTERN BLANK (``So``) — are NOT reported
    empty. Catching those means blacklisting glyphs, which is the approach this
    function exists to replace; they are a font-rendering question, not a
    Unicode-property one.
    """
    return all(unicodedata.category(ch)[0] in "CMZ" for ch in text)
