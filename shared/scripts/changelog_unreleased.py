"""Hand-written entries under ``## [Unreleased]`` move into the release (operator decision Q5, AC09).

Keep a Changelog moves "Unreleased" into the new version; before Q5 the release left those bullets where they were and
only named them, so a reader of the release never saw them. :func:`take` lifts every bullet that sits under one of the
categories the release section renders (``### Added`` ... ``### Security``) out of the ``[Unreleased]`` block, with its
indented continuation lines (blank lines inside the bullet included), and returns them by category; a ``### <category>`` heading left with no content goes too.
A bullet under no such heading (no heading at all, or another one such as ``### Breaking Changes``) has no category the
release could put it in: it STAYS and is named back as before (``left``), never placed by a guess. :func:`marked` is the
preview's copy of the moved entries, each marked ``(hand-written)``.

Standard library plus the shared section predicates only (``changelog_sections``, ADR-045).
"""

from __future__ import annotations

import re
from typing import Sequence

from changelog_sections import section_end, unreleased_start

HAND_WRITTEN_MARK = " (hand-written)"
_HEADING = re.compile(r"^###\s+(.+?)\s*$")
_TOP_BULLET = re.compile(r"^-\s+")
_ANY_BULLET = re.compile(r"^\s*-\s+")  # what the aggregator always named back: every dash bullet, at any depth


def take(changelog: str, categories: Sequence[str]) -> tuple[str, dict[str, list[str]], list[str]]:
    """``(new_text, moved, left)``: the changelog with the moved bullets gone from ``[Unreleased]``, the moved entries by
    category in document order (each the bullet's text without ``- ``, continuation lines kept), and the text of every
    bullet that stays. Without an ``[Unreleased]`` block, or with nothing to move, the text comes back unchanged."""
    lines = changelog.splitlines(keepends=True)
    start = unreleased_start(lines)
    if start is None:
        return changelog, {}, []
    end = section_end(lines, start)
    moved: dict[str, list[str]] = {}
    keep: list[str] = []
    category: str | None = None
    i = start + 1
    while i < end:
        line = lines[i]
        heading = _HEADING.match(line.rstrip("\r\n"))
        if heading:
            category = heading.group(1) if heading.group(1) in categories else None
        if category and _TOP_BULLET.match(line):
            block = [_TOP_BULLET.sub("", line, count=1).rstrip("\r\n")]
            while (nxt := _continuation(lines, i + 1, end)) is not None:  # indented lines, across blank ones inside the bullet
                block.extend(x.rstrip("\r\n") for x in lines[i + 1:nxt + 1])
                i = nxt
            moved.setdefault(category, []).append("\n".join(block).strip())
        else:
            keep.append(line)
        i += 1
    left = [_ANY_BULLET.sub("", line).strip() for line in keep if _ANY_BULLET.match(line)]
    if not moved:
        return changelog, {}, left
    return "".join(lines[:start + 1] + _tidy(keep) + lines[end:]), moved, left


def _continuation(lines: list[str], i: int, end: int) -> int | None:
    """The index of the next indented line of the same bullet, when only blank lines lie between; else None."""
    while i < end and not lines[i].strip():
        i += 1
    return i if i < end and lines[i][:1].isspace() else None


def _tidy(body: list[str]) -> list[str]:
    """The kept body without a ``### <heading>`` that lost all its content, framed by one blank line on each side."""
    out: list[str] = []
    for n, line in enumerate(body):
        if _HEADING.match(line.rstrip("\r\n")):
            rest = body[n + 1:]
            stop = next((k for k, x in enumerate(rest) if _HEADING.match(x.rstrip("\r\n"))), len(rest))
            if not any(x.strip() for x in rest[:stop]):
                continue
        out.append(line)
    while out and not out[0].strip():
        out.pop(0)
    while out and not out[-1].strip():
        out.pop()
    eol = "\r\n" if any(x.endswith("\r\n") for x in body) else "\n"
    return [eol] + out + ([eol] if out else [])


def marked(moved: dict[str, list[str]]) -> dict[str, list[str]]:
    """The moved entries as the preview shows them: the first line of each ends in ``(hand-written)``."""
    def mark(text: str) -> str:
        first, sep, rest = text.partition("\n")
        return first + HAND_WRITTEN_MARK + sep + rest
    return {category: [mark(t) for t in texts] for category, texts in moved.items()}
