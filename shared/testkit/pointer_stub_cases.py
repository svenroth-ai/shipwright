"""The ONE fixture table for the root pointer stub (BRIEF 14.1: every recogniser shares one set).

Used by ``shared/tests/test_shipwright_pointer.py`` now and by the R1c both-copies check, the R3
abort, the R2 migration tool and CI later: import it via ``sys.path.insert(0, <repo>/shared/testkit)``
and iterate :func:`cases`. Each case is ``(id, data, expect, location, location_expect, why)``:
``expect`` is the :func:`shipwright_pointer.classify` kind for the bytes; ``location`` is where the
file sits (``root`` or ``new`` = ``.shipwright/config/``); ``location_expect`` is what the
location-aware caller (R1c) must do, ``None`` when the content verdict is all there is.
"""

from __future__ import annotations

from typing import NamedTuple

MAX = 512
BOM = b"\xef\xbb\xbf"
SIG = "SHIPWRIGHT-POINTER/1"
BODY = ("moved_to: .shipwright/config/\nmin_plugin_version: 0.40.0\n"
        "This file is a stub left so older Shipwright plugins still recognise this project. "
        "Shipwright now keeps its configuration in .shipwright/config/. "
        "Update the Shipwright plugins; do not edit or delete this file.\n")


class Case(NamedTuple):
    id: str
    data: bytes
    expect: str
    location: str = "root"
    location_expect: str | None = None
    why: str = ""


def _stub(first: str = SIG, body: str = BODY) -> str:
    return f"{first}\n{body}"


def _pad(text: str, size: int, *, bom: bool = False, crlf: bool = False) -> bytes:
    """*text* plus a filler line so the CR-stripped size (BOM included) is exactly *size*."""
    base = len(text.encode()) + (len(BOM) if bom else 0)
    fill = size - base - 1  # the filler line ends with "\n"
    assert fill >= 0, (size, base)
    out = text + "#" * fill + "\n"
    if crlf:
        out = out.replace("\n", "\r\n")
    return (BOM if bom else b"") + out.encode()


def cases() -> list[Case]:
    s = _stub()
    return [
        Case("lf_canonical", s.encode(), "stub"),
        Case("crlf", s.replace("\n", "\r\n").encode(), "stub", why="core.autocrlf=true checkout"),
        Case("bom", BOM + s.encode(), "stub", why="PowerShell 5.1 / editors write a BOM"),
        Case("trailing_spaces", _stub(SIG + "  \t").encode(), "stub"),
        Case("leading_spaces", _stub("  " + SIG).encode(), "stub", why="surrounding whitespace stripped"),
        Case("exactly_512", _pad(s, MAX), "stub"),
        Case("size_513", _pad(s, MAX + 1), "edited"),
        Case("bom_512", _pad(s, MAX, bom=True), "stub", why="the BOM counts toward the cap"),
        Case("bom_513", _pad(s, MAX + 1, bom=True), "edited"),
        Case("crlf_512_after_strip", _pad(s, MAX, crlf=True), "stub", why="CR bytes do not count"),
        Case("version_2", _stub("SHIPWRIGHT-POINTER/2").encode(), "too_new"),
        Case("version_2_oversized", _pad(_stub("SHIPWRIGHT-POINTER/2"), MAX + 1), "edited",
             why="edited is reported before the version"),
        Case("version_0", _stub("SHIPWRIGHT-POINTER/0").encode(), "not_stub"),
        Case("version_leading_zero", _stub("SHIPWRIGHT-POINTER/01").encode(), "not_stub"),
        Case("version_overlong", _stub("SHIPWRIGHT-POINTER/" + "9" * 40).encode(), "too_new",
             why="a future format is never read as config, however long its number"),
        Case("version_overlong_oversized", _pad(_stub("SHIPWRIGHT-POINTER/" + "9" * 40), MAX + 1), "edited"),
        Case("version_fullwidth_digit", _stub("SHIPWRIGHT-POINTER/１").encode(), "not_stub",
             why="only ASCII digits"),
        Case("lowercase_signature", _stub("shipwright-pointer/1").encode(), "not_stub"),
        Case("signature_on_line_2", ("\n" + s).encode(), "not_stub"),
        Case("signature_after_text", ("note\n" + s).encode(), "not_stub"),
        Case("unicode_separator_in_line_1", _stub(SIG + " x").encode(), "not_stub",
             why="lines split on LF only; the separator stays inside line 1"),
        Case("trailing_nbsp", _stub(SIG + "\u00a0").encode(), "not_stub", why="only ASCII whitespace is stripped"),
        Case("trailing_nel", _stub(SIG + "\u0085").encode(), "not_stub", why="only ASCII whitespace is stripped"),
        Case("double_bom", BOM + BOM + s.encode(), "not_stub", why="one BOM is dropped; a second is content"),
        Case("empty", b"", "not_stub"),
        Case("non_utf8", b"\xff\xfe\x00S\x00H", "not_stub"),
        Case("conflict_on_line_1", ("<<<<<<< HEAD\n" + s + "=======\n" + s + ">>>>>>> b\n").encode(),
             "not_stub"),
        Case("conflict_after_signature",
             (SIG + "\n<<<<<<< HEAD\nmin_plugin_version: 0.40.0\n=======\nmin_plugin_version: 0.41.0\n"
              ">>>>>>> b\n").encode(), "not_stub", why="BRIEF 14.9: the version line is the likely conflict"),
        Case("json_after_signature", (SIG + '\n{"status": "complete"}\n').encode(), "stub",
             why="signature + cap is the whole rule (14.1); later lines are not inspected"),
        Case("real_json_config", b'{"status": "complete", "phases": {}}\n', "not_stub"),
        Case("stub_at_new_path", s.encode(), "stub", location="new", location_expect="loud_error",
             why="14.1: a stub at .shipwright/config/ is a loud error, never config (asserted in R1c)"),
    ]
