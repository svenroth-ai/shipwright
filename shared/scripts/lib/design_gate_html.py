"""Design gates #5 (shared chrome) and #6 (standalone HTML), extracted from
``design_gate_extras`` (which re-exports them). Behaviour unchanged."""

from __future__ import annotations

import re

try:
    from .design_gate_result import GateResult  # loaded as lib.<module> (shared/tests)
    from .html_tag_scanner import parse_tags
except ImportError:
    # loaded as top-level — check-design-gates.py puts shared/scripts/lib itself on sys.path.
    from design_gate_result import GateResult
    from html_tag_scanner import parse_tags


# --------------------------------------------------------------------------- #
# #5 — shared chrome from one definition
# --------------------------------------------------------------------------- #


def _nav_targets(html: str) -> set[str]:
    targets = set()
    for attrs in parse_tags(html):
        classes = attrs.get("class", "").split()
        href = attrs.get("href")
        if href and ("nav-item" in classes or "topnav-link" in classes):
            targets.add(href)
    return targets


def screen_declares_nav(html: str) -> bool:
    """Whether a screen's markup carries any ``nav-item``/``topnav-link``
    anchor at all — tells "genuinely no shared chrome" apart from "no chrome
    definition despite screens plainly using one" (external review)."""
    return bool(_nav_targets(html))


def chrome_nav_targets_consistent(chrome_definition_html: str, screen_html: str) -> GateResult:
    """**#5** — a screen's nav targets (``href`` values on its ``nav-item``/
    ``topnav-link`` anchors) must be the SAME SET the chrome definition
    declares — byte-identical markup isn't required, a different target set
    is. No-nav screens (Layout C / auth) are exempt. An EXISTING but empty/
    malformed definition is NOT itself an exemption — a screen that plainly
    uses nav markup still has to draw it from somewhere (round 9)."""
    chrome_targets = _nav_targets(chrome_definition_html)
    screen_targets = _nav_targets(screen_html)
    if not chrome_targets:
        if screen_targets:
            return GateResult(
                False,
                f"chrome definition declares no nav targets, but the screen "
                f"declares {sorted(screen_targets)} — not drawn from it",
            )
        return GateResult(True, "chrome definition declares no nav targets to compare")
    if not screen_targets:
        return GateResult(True, "screen has no nav markup (e.g. an auth/Layout-C screen) — exempt")
    if screen_targets != chrome_targets:
        return GateResult(
            False,
            f"nav targets {sorted(screen_targets)} do not match the chrome "
            f"definition's {sorted(chrome_targets)}",
        )
    return GateResult(True, f"{len(screen_targets)} nav target(s) match the chrome definition")


# --------------------------------------------------------------------------- #
# #6 — standalone HTML
# --------------------------------------------------------------------------- #

#: Google Fonts is the one documented exception (`step-4-generate-screens.md`
#: "no external dependencies except optional CDN font").
_ALLOWED_EXTERNAL_HOSTS = ("fonts.googleapis.com", "fonts.gstatic.com")

_WHITESPACE_STRIP_RE = re.compile(r"[\t\n\r]")


def _external_host(raw: str) -> str | None:
    """The value's hostname if external (``http``/``https`` or protocol-
    relative), else ``None``. Decided by SCHEME, not leading-slash count —
    a real browser also resolves ``https:evil.example`` (0 slashes) and
    ``https:/evil.example`` (1) externally (round 8b). Tab/newline are
    stripped from anywhere in the value, not just the ends, since a literal
    one inside a quoted attribute is valid HTML. Never a substring match —
    ``https://evil.example/?=fonts.googleapis.com`` must not pass."""
    from urllib.parse import urlparse

    normalized = _WHITESPACE_STRIP_RE.sub("", raw).strip().replace("\\", "/")
    if not normalized:
        return None
    if normalized.startswith("//"):
        parsed = urlparse(f"https:{normalized}")
    else:
        parsed = urlparse(normalized)
        if parsed.scheme not in ("http", "https"):
            return None
    return (parsed.hostname or "").lower()


def standalone_html_violations(html: str) -> list[str]:
    """**#6** — every external ``src``/``href`` reference outside the one
    allowed font-CDN exception. Empty list means the file is standalone."""
    violations = []
    for attrs in parse_tags(html):
        for name in ("src", "href"):
            raw = attrs.get(name)
            if not raw:
                continue
            host = _external_host(raw)
            if host is not None and host not in _ALLOWED_EXTERNAL_HOSTS:
                violations.append(raw)
    return violations
