"""Per-screen viewport of the Test-phase screenshot check (derived from the route entry, the package screen map or the mockup).

The default is 1280x800 for every screen. A screen that is designed for a phone width is compared at THAT width (both shots of
the screen, approved and built, get the same size), so the comparison no longer measures a desktop render against a phone design.
"""

from __future__ import annotations

import re
from pathlib import Path

VIEWPORT = (1280, 800)
_VP_WH_RE = re.compile(r"^\s*(\d{3,4})\s*[x\u00d7]\s*(\d{3,4})\s*$")
_MIN_W, _MAX_W, _MIN_H, _MAX_H = 240, 3840, 320, 4000
_PHONE_CLASS_RE = re.compile(r"""(?<![\w-])class\s*=\s*["'][^"']*(?<![\w-])(?:phone|mobile)-frame(?![\w-])""", re.I)
_PHONE_VAR_RE = re.compile(r"--(?:phone|mobile)-width\s*:\s*([^;}\n]+)", re.I)
_PHONE_ROOT_RE = re.compile(r"<body\b[^>]*>\s*<[a-z][\w-]*\b[^>]*" + _PHONE_CLASS_RE.pattern, re.I)
_PX_RE = re.compile(r"(\d{2,4})px")
_META_RE = re.compile(r"<meta\b[^>]*>", re.I)
_LEADING_COMMENT_RE = re.compile(r"\s*(?:<!doctype[^>]*>\s*)?<!--(.*?)-->", re.S | re.I)
_COMMENT_WIDTH_RE = re.compile(r"\b(?:phone|mobile)\s+width\s+(\d{3,4})\s*px", re.I)
PHONE_DEFAULT_WIDTH = 390


def _parse_viewport(value) -> tuple[int, int] | None:
    """``(w, h)`` from ``[w, h]`` / ``{"width", "height"}`` / ``"WxH"`` / a bare width (height stays 800); None = not a viewport."""
    w = h = None
    if isinstance(value, str) and (m := _VP_WH_RE.match(value)):
        w, h = int(m.group(1)), int(m.group(2))
    elif isinstance(value, (list, tuple)) and len(value) == 2:
        w, h = value
    elif isinstance(value, dict):
        w, h = value.get("width"), value.get("height", VIEWPORT[1])
    elif isinstance(value, int) and not isinstance(value, bool):
        w, h = value, VIEWPORT[1]
    ok = all(isinstance(n, int) and not isinstance(n, bool) for n in (w, h)) and _MIN_W <= w <= _MAX_W and _MIN_H <= h <= _MAX_H
    return (w, h) if ok else None


def _mockup_viewport(html: str) -> tuple[tuple[int, int], str] | str | None:
    """The viewport a mockup itself declares: a ``shipwright-viewport`` meta, a numeric ``<meta name=viewport width=N>``, a phone/mobile
    frame in the markup (mobile-only layout), or a leading comment naming the phone width. None = it declares nothing (default);
    a declaration that is present but not a viewport is an error TEXT, never a silent default."""
    metas = sorted(_META_RE.findall(html), key=lambda m: "shipwright-viewport" not in m.lower())  # the explicit meta wins
    for meta in metas:
        name = re.search(r"(?<![\w-])name\s*=\s*[\"']([^\"']*)", meta, re.I)
        content = re.search(r"content\s*=\s*[\"']([^\"']*)", meta, re.I)
        if not (name and content):
            continue
        if name.group(1).lower() == "shipwright-viewport":
            vp = _parse_viewport(content.group(1).strip())
            return (vp, "mockup-meta") if vp else f"the mockup's shipwright-viewport meta {content.group(1)!r} is not a viewport"
        elif name.group(1).lower() == "viewport" and (w := re.search(r"(?<![\w-])width\s*=\s*([^,;\s]+)", content.group(1), re.I)):
            raw = w.group(1)
            if raw.lower() == "device-width":
                continue  # responsive: declares no size
            vp = _parse_viewport(int(raw)) if re.fullmatch(r"\d{1,5}", raw) else None
            return (vp, "mockup-meta") if vp else f"the mockup's viewport meta width {raw!r} is not a whole width in {_MIN_W}-{_MAX_W}"
    comment = _LEADING_COMMENT_RE.match(html)  # only the mockup's own header comment, never one in the body
    markup = re.sub(r"<!--.*?--!?>|<style\b.*?</style[^>]*>|<script\b.*?</script[^>]*>", "", html, flags=re.S | re.I)
    if _PHONE_ROOT_RE.search(markup):  # the screen IS a phone frame (the page's outermost element): the frame's own width is the page width
        w = _PHONE_VAR_RE.search(html)
        px = _PX_RE.fullmatch(w.group(1).strip()) if w else None
        if w and not px:
            return f"the mockup's phone width {w.group(1).strip()!r} is not a plain NNNpx value"
        vp = _parse_viewport(int(px.group(1)) if px else PHONE_DEFAULT_WIDTH)
        return (vp, "mockup-phone-frame") if vp else f"the mockup's phone width {px.group(1)}px is outside {_MIN_W}-{_MAX_W}"
    if comment and (w := _COMMENT_WIDTH_RE.search(comment.group(1))):
        vp = _parse_viewport(int(w.group(1)))
        return (vp, "mockup-comment") if vp else f"the mockup's phone width {w.group(1)}px is outside {_MIN_W}-{_MAX_W}"
    return None


def screen_viewport(entry, map_entry, sources: list[Path]) -> tuple[tuple[int, int], str] | str:
    """``((w, h), source)`` for one screen, else an error text. Order: the package screen-map entry, the mockup
    itself (the approved package decides, test wiring cannot); the default 1280x800 when none declares one. A declaration that is not a viewport is an error, never a silent default."""
    if isinstance(entry, dict) and "viewport" in entry:  # test wiring must not be able to pick the size a red screen is compared at
        return "'viewport' is not accepted on a screen-routes.json entry: declare it in the package screen-map entry or the mockup itself"
    if isinstance(map_entry, dict) and "viewport" in map_entry:
        vp = _parse_viewport(map_entry["viewport"])
        if vp is None:
            return (f"'viewport' in screen-map.json must be [width, height], {{\"width\", \"height\"}}, \"WxH\" or a width "
                    f"({_MIN_W}-{_MAX_W} x {_MIN_H}-{_MAX_H})")
        return vp, "screen-map"
    for src in sources:
        try:
            found = _mockup_viewport(src.read_text(encoding="utf-8", errors="ignore"))
        except OSError:
            found = None
        if found:
            return found
    return VIEWPORT, "default"

