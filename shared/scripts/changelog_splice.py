"""Splicing a rendered Keep-a-Changelog section into an existing document.

`changelog_sections` answers "where is what". This module applies a DECISION:
given a document and a freshly rendered section, insert it, replace what is
recorded, or refuse. It is expressed entirely in terms of those predicates, so
there is no second heading parser to drift.

Used by `shared/scripts/tools/aggregate_changelog.py`, the writer the release
path invokes (changelog SKILL.md Step 4).

NOT used by `plugins/shipwright-changelog/scripts/lib/changelog.py`: that
writer carries its own splice because it additionally preserves a UTF-8 BOM and
the file's own line endings (PR #452 AC12), which this one does not, and it
replaces a lone same-version section unconditionally rather than comparing
bodies. Folding the two together means giving the aggregator those guarantees
AND changing the direct writer's contract - deliberately out of scope, recorded
so the next reader does not mistake it for an oversight.

Unlike `changelog_sections`, this module imports a sibling, so it must NOT be
loaded by path under a private module name - that sibling would resolve against
whatever is on `sys.path` at the time. Import it normally, with
`shared/scripts` on the path.
"""

from __future__ import annotations

import re

from changelog_sections import insertion_index, section_end, section_starts


class SectionConflict(ValueError):
    """The existing history cannot be extended safely.

    Raised instead of writing something plausible over content whose meaning is
    not knowable — the "stop and say why" arm. Callers translate it into their
    own error type so their CLI contract is unchanged.

    Message text is deliberately **ASCII**. It is the one string an operator
    must read to reconcile a stopped release by hand, and it reaches them
    through a subprocess pipe: a Windows child writes stdout/stderr in the
    console codepage, so a non-ASCII character arrives as mojibake — or kills
    the read outright when the caller decodes UTF-8.
    """


def insert_section(changelog_text: str, new_section: str) -> str:
    """Insert ``new_section`` at the structural point in ``changelog_text``."""
    # Preserve the line-ending-with-newline convention by splitting via
    # splitlines(keepends=True).
    lines = changelog_text.splitlines(keepends=True)
    idx = insertion_index(lines)

    # An unterminated last line would otherwise be concatenated with the new
    # heading (`# Changelog## [0.3.0]`). The sibling writer in
    # `changelog.update_changelog` has always guarded this; the retired
    # aggregator-local copy did not, and this is now the ONE implementation.
    if idx >= len(lines) and lines and not lines[-1].endswith("\n"):
        lines = lines[:-1] + [lines[-1] + "\n"]

    separator = "" if idx < len(lines) else "\n"
    new_block = new_section
    if not new_block.endswith("\n"):
        new_block += "\n"
    new_block += "\n"  # blank line separator before the following content

    before = "".join(lines[:idx])
    after = "".join(lines[idx:])
    # Guard: don't emit three consecutive blank lines.
    if before.endswith("\n\n") and new_block.startswith("\n"):
        new_block = new_block.lstrip("\n")
    return before + new_block + separator + after


def normalize_body(text: str) -> str:
    """Collapse a section body to what a comparison should care about.

    Line endings and trailing whitespace are formatting, not content: a
    checkout that converted the file to CRLF must not read as "the operator
    changed the release". Indentation is NOT touched, so a nested list item
    stays distinguishable from a top-level one.
    """
    lines = [line.rstrip() for line in text.replace("\r\n", "\n").split("\n")]
    return "\n".join(lines).strip()


def section_body(lines: list[str], start: int) -> str:
    """The normalized body of the section beginning at `start`, heading excluded.

    The heading is excluded from the BODY comparison deliberately: it carries
    the release date, and a caller that defaults that date to *today* renders
    the same bullets under a new heading when a release is resumed the next
    morning. Comparing it verbatim would refuse the one scenario a same-version
    replace exists to fix. What a heading may carry BESIDES a version and a
    date is guarded separately — see :func:`heading_annotation`.
    """
    return normalize_body("".join(lines[start + 1:section_end(lines, start)]))


# `## [0.3.0] - 2026-04-23` — a bracketed version, optionally followed by a
# dash and a single date token. Anything else on that line is an annotation a
# re-render cannot reproduce.
_PLAIN_HEADING_RE = re.compile(r"^##\s+\[[^\]]+\]\s*(?:[-–—]\s*\S+\s*)?$")


def heading_annotation(heading_line: str) -> str:
    """Return the heading text when it carries more than a version and a date.

    Empty string when the heading is plain.

    A replace rewrites the whole heading line, so anything on it that the
    renderer does not reproduce is silently discarded. Keep-a-Changelog puts
    the yank marker there — `## [0.3.0] - 2026-04-23 [YANKED]` — and dropping
    it would make a withdrawn release read as a normal one. That is a real
    loss, so it is detected rather than assumed absent.
    """
    text = heading_line.rstrip("\r\n")
    return "" if _PLAIN_HEADING_RE.match(text) else text.strip()


def apply_section(
    changelog_text: str,
    version: str,
    new_section: str,
    document_name: str,
) -> tuple[str, str]:
    """Return ``(new_text, action)`` for writing `new_section` into the document.

    ``action`` is one of ``inserted`` / ``replaced`` / ``unchanged``.

    Re-running a release is normal: a writer that renders from pending entries
    consumes them AFTER writing, so any interruption in that window leaves the
    section written and the entries still pending. Inserting again produces a
    second ``## [x.y.z]``.

    Replacing unconditionally would be worse. Consuming the entries is not
    atomic either — if it took some and then died, the recorded section holds
    more bullets than the survivors render, and a replace would delete released
    history. So a replace happens only when it cannot lose anything: when the
    recorded body is what the pending entries now say, AND the recorded heading
    carries nothing a re-render would drop. Otherwise this raises
    :class:`SectionConflict` naming the disagreement, and the caller stops
    without touching either side.
    """
    if version.strip().lower() == "unreleased":
        # `entry_version` refuses this for the same reason: the Unreleased
        # block holds entries that have not been released yet, and replacing
        # it would discard them.
        raise SectionConflict(
            "refusing to write a section for version 'Unreleased': that block "
            "holds entries not yet released, and replacing it would discard them"
        )

    lines = changelog_text.splitlines(keepends=True)
    existing = section_starts(lines, version)

    if len(existing) > 1:
        raise SectionConflict(
            f"{document_name} already contains {len(existing)} sections for "
            f"version {version}; refusing to guess which one to replace. "
            "Remove the duplicates and re-run."
        )

    if not existing:
        return insert_section(changelog_text, new_section), "inserted"

    start = existing[0]
    # Measure both sides with the SAME ruler. `section_body` stops at
    # `section_end`; comparing it against ALL of `new_section` would turn any
    # rendered line that `continues_section` rejects — a multi-line bullet
    # whose continuation is not indented, say — into an eternal mismatch, so a
    # release identical to what is on record would refuse forever.
    rendered = new_section.splitlines(keepends=True)
    rendered_body = section_body(rendered, 0) if rendered else ""
    if rendered_body != section_body(lines, start):
        raise SectionConflict(
            f"{document_name} already records a section for version {version}, "
            "and it is not what the pending entries say. Refusing to overwrite "
            "it: an earlier release may have been interrupted partway through "
            "consuming them, or the section was edited by hand. Reconcile the "
            "two by hand and re-run. Nothing has been changed and nothing has "
            "been consumed."
        )

    annotation = heading_annotation(lines[start])
    if annotation:
        raise SectionConflict(
            f"{document_name} records version {version} under the heading "
            f"{annotation!r}, which carries more than a version and a date. "
            "Replacing the section rewrites that heading, so the extra marking "
            "(for example [YANKED]) would be lost. Refusing: reconcile it by "
            "hand and re-run. Nothing has been changed and nothing consumed."
        )

    head, tail = lines[:start], lines[section_end(lines, start):]
    body = new_section if new_section.endswith("\n") else new_section + "\n"
    suffix = "\n" if tail else ""
    new_text = "".join(head) + body + suffix + "".join(tail)
    return new_text, ("unchanged" if new_text == changelog_text else "replaced")
