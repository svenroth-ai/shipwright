"""Split external-reviewer **prose** into normalized findings.

Separated from :mod:`lib.review_findings` (which holds the native-shape
adapters) because this is the only source that needs real parsing, and because
together the two exceed the 300-line file limit.

The prose is not arbitrary: ``shared/prompts/*/system`` mandates a per-finding
layout — ``Category / Severity / File:line / Finding / Suggestion``. Real
payloads from the configured providers render it at least three ways::

    - Category: bug                     - **Category:** Approach
    - Severity: high                    - **Severity:** High
    - File: src/x.py:325                - **Finding:** …

    1. **Category: approach - Severity: high**
       **Finding:** …

so the parser tolerates a leading bullet or number, optional bold markers, and a
combined category/severity header.

**The no-fabrication rule.** When no block parses, the result is an empty list
plus ``PARSE_UNSTRUCTURED`` — never one synthetic finding holding the raw text.
A reviewer that found nothing would otherwise be rendered as having found
something, which corrupts the one question this artifact answers. The caller
retains the raw text in ``raw_excerpt``, and ``parse_status`` keeps an
unparseable review distinguishable from a genuinely clean one.
"""

from __future__ import annotations

import re
from typing import Any

from .review_finding_shape import MAX_FINDINGS, MAX_TEXT_CHARS, make_finding

__all__ = [
    "PARSE_PARTIAL",
    "PARSE_STRUCTURED",
    "PARSE_UNSTRUCTURED",
    "ProseOverflowError",
    "from_external_prose",
]

PARSE_STRUCTURED = "structured"
PARSE_UNSTRUCTURED = "unstructured"
#: Some legs of a multi-provider review parsed and some did not — distinct from
#: both, because "structured" would hide a provider whose review was lost.
PARSE_PARTIAL = "partial"


class ProseOverflowError(ValueError):
    """Raised when a payload holds more findings than can be recorded."""

#: One labelled key. Tolerates a leading bullet/number, optional bold markers,
#: and both ASCII and full-width colons — every rendering observed in real
#: payloads from the configured providers.
#: ``(?::[ \t]*line)?`` consumes the ``File:line:`` label the reviewer prompt
#: itself mandates (``shared/prompts/code_reviewer/system``). Without it the key
#: matched at ``File:`` and the value became ``line: `path/x.py:157```, which
#: then had its trailing number peeled off and stored a path of ``line:
#: `path/x.py`` — observed verbatim in this change's own first artifact.
_KEY_RE = re.compile(
    r"(?:^|\n)[ \t]*(?:[-*•]|\d+[.)])?[ \t]*\*{0,2}"
    r"(category|severity|file|finding|suggestion)"
    r"(?:[ \t]*:[ \t]*line)?"
    r"\*{0,2}[ \t]*[:：]",
    re.IGNORECASE,
)

#: ``Category: approach - Severity: high`` folded onto one line.
_INLINE_SEVERITY_RE = re.compile(r"severity[ \t]*[:：][ \t]*\**\s*(\w+)", re.IGNORECASE)

#: ``path/to/file.py:325`` — split the trailing line number off a file value.
_FILE_LINE_RE = re.compile(r"^(.*?):(\d+)\s*$")

#: Where the findings stop and the reviewer's closing prose begins — a Markdown
#: heading or a horizontal rule on its own line.
_TAIL_BOUNDARY_RE = re.compile(r"\n[ \t]*(?:#{1,6}[ \t]|(?:---|\*\*\*|___)[ \t]*\r?\n)")


def _clean(value: str) -> str:
    """Strip the decoration the layouts wrap values in."""
    text = re.sub(r"\*{1,2}", "", value.strip())
    text = text.strip().strip("`").strip()
    return re.sub(r"[ \t]*\n[ \t]*", " ", text).strip(" -—\t")


def _block_end(prose: str, start: int, next_key_start: int | None) -> int:
    """Where the last key's value stops.

    Without this the final value ran to end-of-text and swallowed whatever
    followed the findings — a trailing "### Overall Assessment …" ended up glued
    onto the last suggestion (observed in this change's own first artifact). Stop
    at the next Markdown heading or horizontal rule instead.
    """
    if next_key_start is not None:
        return next_key_start
    tail = _TAIL_BOUNDARY_RE.search(prose, start)
    return tail.start() if tail else len(prose)


def _parse_blocks(prose: str) -> list[dict[str, str]]:
    """Split ``prose`` into per-finding key/value blocks.

    A new block opens at a ``Category`` key, and also at the FIRST key of any
    kind — layouts that omit ``Category`` (``**Finding:** … **Suggestion:** …``)
    would otherwise be dropped wholesale. A repeated key without an intervening
    ``Category`` likewise starts a new block, which is what keeps those
    category-less layouts splitting into separate findings.
    """
    matches = list(_KEY_RE.finditer(prose))
    if not matches:
        return []
    blocks: list[dict[str, str]] = []
    current: dict[str, str] = {}
    for index, match in enumerate(matches):
        key = match.group(1).lower()
        next_start = matches[index + 1].start() if index + 1 < len(matches) else None
        value = _clean(prose[match.end():_block_end(prose, match.end(), next_start)])
        if key == "category" or key in current:
            if current:
                blocks.append(current)
            current = {}
        current[key] = value
    if current:
        blocks.append(current)
    return blocks


def from_external_prose(prose: str) -> tuple[list[dict[str, Any]], str]:
    """Split external reviewer prose into findings.

    Returns ``(findings, parse_status)``. Raises :class:`ProseOverflowError`
    when the payload holds more findings than :data:`MAX_FINDINGS` — silently
    keeping the first 200 would record a partial review as a complete one.
    """
    if not isinstance(prose, str) or not prose.strip():
        return [], PARSE_UNSTRUCTURED

    blocks = _parse_blocks(prose)
    if len(blocks) > MAX_FINDINGS:
        raise ProseOverflowError(
            f"external review prose holds {len(blocks)} finding blocks, above the "
            f"{MAX_FINDINGS} cap — refusing to record a truncated review as complete"
        )

    out: list[dict[str, Any]] = []
    for block in blocks:
        category = block.get("category")
        severity = block.get("severity")
        if severity is None and category:
            inline = _INLINE_SEVERITY_RE.search(category)
            if inline:
                severity = inline.group(1)
                category = _clean(category[: inline.start()])
        text = block.get("finding") or block.get("suggestion")
        if not text:
            continue
        file_value, line_value = block.get("file"), None
        if file_value:
            match = _FILE_LINE_RE.match(file_value)
            if match:
                file_value, line_value = match.group(1), match.group(2)
        out.append(make_finding(
            finding=text[:MAX_TEXT_CHARS],
            source="external-review",
            severity=severity,
            category=category,
            file=file_value,
            line=line_value,
            suggestion=block.get("suggestion") if block.get("finding") else None,
        ))

    if not out:
        return [], PARSE_UNSTRUCTURED
    return out, PARSE_STRUCTURED
