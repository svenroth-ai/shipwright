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

from changelog_sections import HEADING_RE, continues_section, unreleased_start

HAND_WRITTEN_MARK = " (hand-written)"
_HEADING = re.compile(r"^###\s+(.+?)\s*$")
_TOP_BULLET = re.compile(r"^-\s+")
_ANY_BULLET = re.compile(r"^\s*-\s+")  # what the aggregator always named back: every dash bullet, at any depth
_FENCE = re.compile(r"^\s*(```|~~~)")


def take(changelog: str, categories: Sequence[str]) -> tuple[str, dict[str, list[str]], list[str]]:
    """``(new_text, moved, left)``: the changelog with the moved bullets gone from ``[Unreleased]``, the moved entries by
    category in document order (each the bullet's text without ``- ``, continuation lines kept), and the text of every
    bullet that stays. Without an ``[Unreleased]`` block, or with nothing to move, the text comes back unchanged.

    An entry is never split (fix round 1): its indented lines, a lazy continuation (a plain column-0 line right after it)
    and a fenced block that opens inside it all go with it, and nothing inside a fence is read as a bullet or a heading.
    An entry whose end cannot be told (a fence that never closes) stays in ``[Unreleased]`` and is named in ``left``."""
    lines = _split(changelog)
    start = unreleased_start(lines)
    if start is None:
        return changelog, {}, []
    end = _block_end(lines, start)
    moved: dict[str, list[str]] = {}
    keep: list[str] = []
    category: str | None = None
    in_fence = False
    i = start + 1
    while i < end:
        line = lines[i]
        if in_fence or _FENCE.match(line):  # a fence outside any entry is kept whole, its lines read as text
            in_fence = (not in_fence) if _FENCE.match(line) else in_fence
            keep.append(line)
            i += 1
            continue
        heading = _HEADING.match(line.rstrip("\r\n"))
        if heading:
            category = heading.group(1) if heading.group(1) in categories else None
        last = _entry_end(lines, i, end) if category and _TOP_BULLET.match(line) else None
        if last is None:
            if category and _TOP_BULLET.match(line):  # ambiguous: the whole rest stays, nothing is moved by half
                keep.extend(lines[i:end])
                break
            keep.append(line)
            i += 1
            continue
        block = [_TOP_BULLET.sub("", line, count=1).rstrip("\r\n")] + [x.rstrip("\r\n") for x in lines[i + 1:last + 1]]
        moved.setdefault(category, []).append("\n".join(block).strip())
        i = last + 1
    left = [_ANY_BULLET.sub("", line).strip() for line in keep if _ANY_BULLET.match(line)]
    if not moved:
        return changelog, {}, left
    return "".join(lines[:start + 1] + _tidy(keep) + lines[end:]), moved, left


def _split(text: str) -> list[str]:
    """Lines split on ``\\n`` only, each keeping its ending (``str.splitlines`` also breaks on U+2028 and friends)."""
    parts = text.split("\n")
    return [part + "\n" for part in parts[:-1]] + ([parts[-1]] if parts[-1] else [])


def _block_end(lines: list[str], start: int) -> int:
    """One past the last line of the ``[Unreleased]`` block: ``changelog_sections.section_end``, except that a fenced
    block and a lazy continuation (a plain column-0 line right after a non-blank one) belong to it. The next ``##``
    heading always ends it, so an unclosed fence can never take a released section with it."""
    k, in_fence, prev_text = start + 1, False, False
    while k < len(lines) and not HEADING_RE.match(lines[k]):
        line = lines[k]
        if in_fence or _FENCE.match(line):
            in_fence = in_fence != bool(_FENCE.match(line))
        elif not (continues_section(line) or prev_text):
            break
        prev_text, k = bool(line.strip()), k + 1
    return k


def _entry_end(lines: list[str], i: int, end: int) -> int | None:
    """The index of the last line of the entry whose bullet is ``lines[i]``; None when that cannot be told."""
    last, k, blank = i, i + 1, False
    while k < end:
        line = lines[k]
        if not line.strip():
            blank, k = True, k + 1
            continue
        indented = line[:1].isspace()
        if _FENCE.match(line) and (indented or not blank):  # a fence that opens inside the entry belongs to it
            close = next((m for m in range(k + 1, end) if _FENCE.match(lines[m])), None)
            if close is None:
                return None
            last, k, blank = close, close + 1, False
        elif indented or not (blank or _HEADING.match(line) or _ANY_BULLET.match(line) or line.startswith("#")):
            last, k, blank = k, k + 1, False  # an indented line, or a lazy continuation right after the entry
        else:
            break
    return last


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
