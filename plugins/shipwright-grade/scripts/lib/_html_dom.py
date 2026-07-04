"""_html_dom — the escape-by-default HTML element builder (the security seam).

Extracted from :mod:`html_report` so the trusted/untrusted boundary lives in
one small, auditable place. The rule: a :class:`_Raw` child (produced only by
:func:`el` itself, or an explicit trusted literal) is emitted verbatim; **every
other child is HTML-escaped as a text node by default**, and **every attribute
value** is cleaned + escaped the same way. So a forgotten wrap on a
model-derived string is escaped, not injected — safety never depends on
remembering an escape call at each seam.

Text/attribute cleaning uses :func:`sanitize.strip_terminal` (removes
ANSI/OSC-8/bidi/control, preserves newlines) then :func:`html.escape`.
"""

from __future__ import annotations

import html as _htmllib

from sanitize import strip_terminal


class _Raw(str):
    """Marks a string as trusted, already-escaped HTML (never re-escaped)."""

    __slots__ = ()


def _text(value: object) -> str:
    """Untrusted → safe text node: strip control/ANSI/bidi, then HTML-escape."""
    return _htmllib.escape(strip_terminal(str(value)), quote=True)


def _attrs(attrs: dict[str, object]) -> str:
    out = []
    for key, val in attrs.items():
        if val is None:
            continue
        name = key.rstrip("_").replace("_", "-")
        # Same cleaning seam as text nodes so an attribute value is never a
        # weaker context than a text node — even though every attribute value
        # today is a trusted literal.
        out.append(f' {name}="{_text(val)}"')
    return "".join(out)


def el(tag: str, *children: object, **attrs: object) -> _Raw:
    """Build an element; ``_Raw`` children pass through, all others are escaped."""
    inner = "".join(
        str(c) if isinstance(c, _Raw) else _text(c) for c in children
    )
    return _Raw(f"<{tag}{_attrs(attrs)}>{inner}</{tag}>")
