"""Split a decision log into its compact-format ADR sections (Group F, F4).

Split from ``group_f`` so that file stays under its bloat-baseline cap and the
segmentation rule has one owner. An ADR runs from its ``### ADR-N:`` header to
the next heading of level 1-3 (an ADR header or not) or to end of file, so a
following ``## `` section or ``### DR-NNN:`` block is never counted as ADR body.
Heading-like lines inside a code fence (a shell ``# comment``) are body text.
"""

from __future__ import annotations

import re

# Match the compact-format ADR header `### ADR-NNN: Title`. The verbose
# old format (`## ADR-NNN | date | ...`) is also detected — only the
# compact form has clean line-counted bodies (ADR-bloat detection
# specifically targets the compact form per the plan).
_ADR_HEADER_RE = re.compile(r"^### ADR-(\d+):\s*.+$", re.MULTILINE)
_SECTION_END_RE = re.compile(r"^#{1,3}\s")
_FENCE_RE = re.compile(r"^\s*(```|~~~)")


def adr_sections(lines: list[str]) -> list[tuple[str, list[str]]]:
    """Return ``(adr_id, body_lines)`` for every compact-format ADR."""
    sections: list[tuple[str, list[str]]] = []
    current_id: str | None = None
    current_body: list[str] = []
    in_fence = False
    for line in lines:
        is_fence = bool(_FENCE_RE.match(line))
        if is_fence:
            in_fence = not in_fence
        if is_fence or in_fence:
            if current_id is not None:
                current_body.append(line)
            continue
        m = _ADR_HEADER_RE.match(line)
        if m or _SECTION_END_RE.match(line):
            if current_id is not None:
                sections.append((current_id, current_body))
            current_id = f"ADR-{m.group(1)}" if m else None
            current_body = []
        elif current_id is not None:
            current_body.append(line)
    if current_id is not None:
        sections.append((current_id, current_body))
    return sections
