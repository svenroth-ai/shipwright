"""How a Triage Inbox entry is rendered to `triage_inbox.md`.

Split from the TTY renderer (`triage_render.py`) in
iterate-2026-08-01-triage-defer-lifecycle: two surfaces, two skins, one set of
rules. Everything about ORDER, the display cap and the elision wording is
imported from there, so the rendered document and the terminal listing cannot
start disagreeing about which parked entries they show.

The escaping rule is this module's own, because markdown is dangerous in ways a
terminal is not — a stored `|`, a leading `#`, or a triple-backtick can restructure
the document around it. It composes with, and does not replace, the control-character
stripping every stored field already gets.
"""

from __future__ import annotations

import html
import re

from .triage_defer import DEFERRED_TOP_N, REVISIT_FIELD, sort_deferred
from .triage_render import (
    NO_REASON,
    clip,
    elision_line,
    format_revisit,
)
from .tty_sanitize import is_visually_empty, strip_control_chars


def escape_md(text: object) -> str:
    """Neutralise untrusted text for ordinary inline Markdown rendering.

    Moved out of `aggregate_triage` in iterate-2026-08-01-triage-defer-lifecycle
    — it is rendering, which is what this module is for, and that file sits at
    its ADR-090 bloat ceiling, so the deferred section it now emits had to be
    paid for by moving something out.

    Control characters/newlines are removed first, raw HTML is entity-escaped,
    and CommonMark punctuation is backslash-escaped. Code contexts use
    :func:`code_span` instead — backslash escaping does not protect delimiters
    inside a code span.
    """
    if text is None:
        return ""
    text = strip_control_chars(str(text))
    text = text.replace("\r\n", " ").replace("\n", " ").replace("\r", " ")
    text = html.escape(text, quote=False)
    for char in "\\`*_[]()|":
        text = text.replace(char, "\\" + char)
    if text.startswith(("#", "+", "-", ">")):
        text = "\\" + text
    text = re.sub(r"^(\d{1,9})([.)])(?=\s)", r"\1\\\2", text)
    return text


def code_span(text: object) -> str:
    """A delimiter-safe CommonMark code span for untrusted single-line text."""
    value = strip_control_chars(str(text) if text is not None else "")
    value = value.replace("\r\n", " ").replace("\n", " ").replace("\r", " ")
    longest = max((len(run) for run in re.findall(r"`+", value)), default=0)
    delimiter = "`" * (longest + 1)
    padding = " " if value.startswith("`") or value.endswith("`") else ""
    return f"{delimiter}{padding}{value}{padding}{delimiter}"



def render_deferred_markdown(
    items: list[dict], severity_rank: dict, *, cap: int = DEFERRED_TOP_N,
) -> list[str]:
    """The parked block for `triage_inbox.md` — same rules, markdown skin.

    The rendered document showed a parked entry as a bare count in the status
    summary, so the agent reading it could not tell a decided-but-not-now
    finding from one that had never existed. Operator decision #3 of 2026-07-27:
    parked entries appear on EVERY surface, in their own section.

    Same order and same cap as the terminal listing (both read
    :func:`sort_deferred` and :data:`DEFERRED_TOP_N`), so an operator who reads
    one and then the other sees the same entries in the same sequence.

    Every stored field goes through :func:`escape_md`, which strips control
    characters before Markdown escaping — the reason included. A reason is typed by whoever made
    the decision on either surface, and the file can be hand-edited, so it is
    untrusted display input exactly like the title beside it.
    """
    if not items:
        return []
    ordered = sort_deferred(items, severity_rank)
    shown = ordered[:cap]
    out = [
        f"## Deferred — decided, revisit later ({len(ordered)})",
        "",
        "_Not gone: each of these was decided, with a date it comes back on._",
        "",
    ]
    for item in shown:
        reason_shown = escape_md(item.get("statusReason") or "")
        reason = NO_REASON if is_visually_empty(reason_shown) else reason_shown
        title = clip(escape_md(item.get("title", "")))
        metadata = (
            f"id={item.get('id', '')} | severity={item.get('severity', '')} | "
            f"revisit={format_revisit(item.get(REVISIT_FIELD))}"
        )
        out.append(f"- **{title}** {code_span(metadata)}")
        out.append(f"  - Reason: {clip(reason)}")
        command = f"triage_cli.py unpark {item.get('id', '')} --reason <why>"
        out.append(f"  - Un-park: {code_span(command)}")
        out.append("")
    if len(ordered) > len(shown):
        out.extend([f"_{elision_line(len(ordered), len(shown))}_", ""])
    return out
