#!/usr/bin/env python3
"""Structural analysis of a Keep-a-Changelog document.

Pure functions over the lines of a CHANGELOG.md — no I/O, no writing. They
exist so a writer can SPLICE a new section into the text it read instead of
rebuilding the file from a fresh header. Rebuilding is what destroyed
hand-written histories (trg-6690d175): every reconstruction path loses whatever
fragment it forgets to concatenate.

**Two writers share this module**, and that is the point:

* ``plugins/shipwright-changelog/scripts/lib/changelog.py::update_changelog``
* ``shared/scripts/tools/aggregate_changelog.py`` — the writer the release path
  actually invokes (changelog SKILL.md Step 4)

They previously carried separate copies, which already disagreed on a lowercase
``## [unreleased]`` and on where a link-reference footer ends a block. Neither
lost content, so nothing had failed yet — but adding same-version replace logic
as a third copy is precisely the drift ``conventions.md:50`` records ("when N
readers share one arithmetic, extract it to ONE SSoT or a predicate WILL
drift").

**Why this file sits at ``shared/scripts/`` top level and not under ``lib/``:**
ADR-045. Every plugin ships its own ``scripts/lib`` package, so a shared helper
under ``lib/`` binds ``sys.modules['lib']`` to whichever one imports first and
the other side's siblings vanish. Same placement as ``tests_block.py`` and
``markdown_table.py``. It has no intra-package imports (only ``re``), so a
consumer may also load it by path under a private module name — which is what
the plugin writer does, to touch no ``lib`` namespace at all.
"""

import re

# ANY level-2 heading — ``## [1.2.0]``, ``## Notes``, or a bare ``##``. This is
# what ends a section. ``###`` never matches (the third ``#`` is not \s).
HEADING_RE = re.compile(r"^##(?:\s|$)")

# A level-2 heading carrying a bracketed name: ``## [1.2.0] - 2026-01-01`` or
# ``## [Unreleased]``.
#
# These two MUST stay consistent: SECTION_HEADING_RE accepts any whitespace
# after ``##``, so HEADING_RE has to as well. When section_end() used a
# ``startswith("## ")`` literal instead, a tab-separated heading was seen as a
# section by section_starts() but not as a section *boundary* — replacing the
# version above it would have run straight through and deleted it.
SECTION_HEADING_RE = re.compile(r"^##\s+\[([^\]]+)\]")


def entry_version(entry: str) -> str:
    """Return the released version `entry` writes a section for.

    Raises ValueError if the entry is not a released-version section. Released
    sections only: the ``[Unreleased]`` block is owned by the release-time
    aggregator, and overwriting it would discard pending bullets.
    """
    versions = [
        match.group(1).strip()
        for match in (SECTION_HEADING_RE.match(line) for line in entry.splitlines())
        if match
    ]
    if not versions:
        raise ValueError(
            "changelog entry has no '## [version]' heading — refusing to write "
            "it rather than guess where it belongs"
        )
    if len(versions) > 1:
        raise ValueError(
            f"changelog entry contains {len(versions)} '## [version]' headings "
            f"({', '.join(versions)}); it must be exactly one section, "
            "otherwise re-running cannot tell which span to replace"
        )
    if versions[0].lower() == "unreleased":
        raise ValueError(
            "refusing an entry headed '## [Unreleased]': update_changelog "
            "writes released sections only, and replacing the Unreleased "
            "block would discard pending bullets"
        )
    return versions[0]


# Lines that belong to a section BODY: a deeper heading (``### Added``) or a
# list item, optionally indented.
_DEEPER_HEADING_RE = re.compile(r"^#{3,}\s")
_LIST_ITEM_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s")


def continues_section(line: str) -> bool:
    """True if `line` can be part of the body of a changelog section.

    A section body is blank lines, deeper headings, list items and their
    indented continuations. Anything else — prose, a link-reference footer, an
    ``# H1`` — trails the section rather than belonging to it.

    This is what bounds a REPLACED span. Ending a section at merely "the next
    ``##`` heading or EOF" makes the last section in a file swallow everything
    below it, so re-running a release silently deleted the canonical
    Keep-a-Changelog link footer and any closing prose. Stopping early can at
    worst leave content stranded below the new section; it can never delete it,
    and this writer exists to make deletion impossible.
    """
    text = line.rstrip("\r\n")
    if not text.strip():
        return True
    if HEADING_RE.match(text):
        return False
    if _DEEPER_HEADING_RE.match(text) or _LIST_ITEM_RE.match(text):
        return True
    return text[:1].isspace()


def section_end(lines: list[str], start: int) -> int:
    """Index one past the last line the section beginning at `start` owns."""
    end = start + 1
    while end < len(lines) and continues_section(lines[end]):
        end += 1
    return end


def section_starts(lines: list[str], version: str) -> list[int]:
    """Line indices of every ``## [version]`` heading matching `version`."""
    starts = []
    for i, line in enumerate(lines):
        match = SECTION_HEADING_RE.match(line)
        if match and match.group(1).strip() == version:
            starts.append(i)
    return starts


def unreleased_start(lines: list[str]) -> int | None:
    """Line index of the first ``## [Unreleased]`` heading, or None.

    Case-INSENSITIVE, matching :func:`insertion_index`. A reader that spells
    this itself and forgets the casing disagrees with where a new section is
    placed — which is exactly how the aggregator ended up finding the right
    insertion point while silently failing to warn about the legacy bullets
    sitting above it.
    """
    for i, line in enumerate(lines):
        match = SECTION_HEADING_RE.match(line)
        if match and match.group(1).strip().lower() == "unreleased":
            return i
    return None


def insertion_index(lines: list[str]) -> int:
    """Line index where a new released section belongs.

    Preference order — every arm INSERTS, none displaces existing text:
      1. above the first released (non-Unreleased) section;
      2. after the ``[Unreleased]`` block;
      3. after the title/header paragraph — the unknown-file-shape arm: go to
         the top and leave everything else alone;
      4. end of file.
    """
    unreleased_at = None
    for i, line in enumerate(lines):
        match = SECTION_HEADING_RE.match(line)
        if not match:
            continue
        if match.group(1).strip().lower() == "unreleased":
            if unreleased_at is None:
                unreleased_at = i
        else:
            return i

    if unreleased_at is not None:
        end = section_end(lines, unreleased_at)
        # Back up over trailing blanks so we don't stack blank lines.
        while end - 1 > unreleased_at and not lines[end - 1].strip():
            end -= 1
        return end

    for i in range(1, len(lines)):
        if not lines[i].strip():
            end = i
            while end + 1 < len(lines) and not lines[end + 1].strip():
                end += 1
            return end + 1

    return len(lines)
