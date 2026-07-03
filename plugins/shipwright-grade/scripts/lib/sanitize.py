"""sanitize — neutralise hostile repo-derived strings before display.

The grader prints strings it does not control (commit subjects, author names,
filenames). Before any of them reach a terminal we strip ANSI/CSI sequences,
OSC-8 hyperlinks, C0/C1 control characters and Unicode bidi overrides (GPT #15 /
the Trojan-source class). Full HTML-context escaping is enforced in the HTML
report (G3); this module is the terminal/markdown-context guard.
"""

from __future__ import annotations

import re

# CSI / SGR sequences: ESC [ ... final-byte.
_CSI_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")
# OSC sequences (incl. OSC-8 hyperlinks): ESC ] ... BEL | ST.
_OSC_RE = re.compile(r"\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)")
# Remaining single-char escapes.
_ESC_RE = re.compile(r"\x1b[@-Z\\-_]")
# C0 (minus \t \n) + DEL + C1 control chars.
_CTRL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f\x80-\x9f]")
# Unicode bidi overrides / isolates (Trojan-source): U+202A-U+202E, U+2066-U+2069.
# Built with chr() so no literal control characters live in this source file.
_BIDI_CHARS = "".join(
    chr(c) for c in (*range(0x202A, 0x202F), *range(0x2066, 0x206A))
)
_BIDI_RE = re.compile("[" + re.escape(_BIDI_CHARS) + "]")


def strip_terminal(text: str) -> str:
    """Remove terminal control sequences and bidi overrides from ``text``."""
    if not text:
        return ""
    out = _OSC_RE.sub("", text)
    out = _CSI_RE.sub("", out)
    out = _ESC_RE.sub("", out)
    out = _BIDI_RE.sub("", out)
    out = _CTRL_RE.sub("", out)
    return out


def one_line(text: str, *, limit: int = 200) -> str:
    """Sanitised single-line form: control-stripped, newlines/tabs -> spaces."""
    cleaned = strip_terminal(text).replace("\t", " ")
    cleaned = re.sub(r"\s*[\r\n]+\s*", " ", cleaned).strip()
    cleaned = re.sub(r"  +", " ", cleaned)
    if len(cleaned) > limit:
        cleaned = cleaned[: limit - 1].rstrip() + "…"
    return cleaned
