"""The ``SECTION_MANIFEST`` parser — one implementation, all readers.

``plan.md`` declares the plan's sections in a ``SECTION_MANIFEST`` comment
block, and the numbering is documented as the build order. Until now the block
was a flat list of ``NN-slug`` names: dependencies were **not expressible**, so
"the numbering is the build order" was a promise nothing could establish, and a
section could be scheduled before the one that produces what it needs.

A line may now name what the section presupposes::

    <!-- SECTION_MANIFEST
    01-auth
    02-database
    03-api: 01-auth, 02-database
    END_MANIFEST -->

A bare ``NN-slug`` line means "no declared dependencies" and parses exactly as
it always did, so every manifest written before this module stays valid and
:func:`validate_dependency_order` is vacuously satisfied for it. Declaring the
dependency is what turns the ordering promise into something checkable.

``:`` cannot occur inside a section id (the grammar is ``NN-`` plus
``[a-z0-9-]``), so the separator is unambiguous.

This module replaces two private parsers that were drifting copies of each
other — ``plugins/shipwright-plan/scripts/lib/sections.py`` and
``verifiers/plan_checks._parse_section_manifest``. Both now call in here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

__all__ = [
    "MANIFEST_RE",
    "SECTION_NAME_RE",
    "ManifestResult",
    "SectionEntry",
    "parse_manifest",
    "parse_manifest_text",
    "validate_dependency_order",
]

MANIFEST_RE = re.compile(
    r"<!--\s*SECTION_MANIFEST\s*\n(?P<body>.*?)END_MANIFEST\s*-->",
    re.DOTALL,
)

# Zero-padded two-digit prefix + kebab-case slug. Anchored at both ends, so a
# traversal payload (``../../etc/passwd``) or a stray path separator can never
# be read as a section id — ids reach the filesystem as ``sections/<id>.md``.
SECTION_NAME_RE = re.compile(r"^\d{2}-[a-z0-9]+(?:-[a-z0-9]+)*$")

_DEP_SEPARATOR = ":"


@dataclass(frozen=True)
class SectionEntry:
    """One manifest line: the section, what it presupposes, and where it was
    written (``line_no`` is 1-based **within the manifest block**, which is
    what a diagnostic needs to point at)."""

    name: str
    dependencies: tuple[str, ...] = ()
    line_no: int = 0


@dataclass
class ManifestResult:
    """Parse outcome.

    ``sections`` stays a plain ``list[str]`` — every pre-existing caller reads
    it that way, and dependencies arrive as an additional field rather than a
    changed shape.
    """

    is_valid: bool
    entries: list[SectionEntry] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def sections(self) -> list[str]:
        return [e.name for e in self.entries]

    @property
    def dependencies(self) -> dict[str, list[str]]:
        return {e.name: list(e.dependencies) for e in self.entries}


def _parse_line(raw: str, line_no: int, errors: list[str]) -> SectionEntry | None:
    """Parse one manifest line into an entry, appending any diagnostics.

    Returns ``None`` when the line yields no section (blank, comment, or a
    malformed name — the caller keeps going so one bad line does not hide the
    rest).
    """
    line = raw.strip()
    if not line or line.startswith("#"):
        return None

    name_part, sep, dep_part = line.partition(_DEP_SEPARATOR)
    name = name_part.strip()
    if not SECTION_NAME_RE.match(name):
        errors.append(f"line {line_no}: Invalid section name: '{name}'")
        return None

    if not sep:
        return SectionEntry(name=name, line_no=line_no)

    deps: list[str] = []
    tokens = dep_part.split(",")
    # A trailing comma leaves one empty tail token; that is punctuation, not a
    # missing dependency, so it is dropped rather than reported.
    if tokens and not tokens[-1].strip():
        tokens = tokens[:-1]
    for token in tokens:
        dep = token.strip()
        if not dep:
            errors.append(f"line {line_no}: empty dependency token in '{name}'")
            continue
        if not SECTION_NAME_RE.match(dep):
            errors.append(f"line {line_no}: Invalid dependency id: '{dep}'")
            continue
        if dep in deps:
            errors.append(f"line {line_no}: duplicate dependency '{dep}' on '{name}'")
            continue
        deps.append(dep)

    return SectionEntry(name=name, dependencies=tuple(deps), line_no=line_no)


def parse_manifest_text(content: str) -> ManifestResult:
    """Parse the ``SECTION_MANIFEST`` block out of ``plan.md`` content."""
    match = MANIFEST_RE.search(content)
    if not match:
        return ManifestResult(False, errors=["No SECTION_MANIFEST block found in plan.md"])

    block = match.group("body").strip()
    if not block:
        return ManifestResult(False, errors=["SECTION_MANIFEST block is empty"])

    entries: list[SectionEntry] = []
    errors: list[str] = []
    seen: set[str] = set()

    for line_no, raw in enumerate(block.splitlines(), start=1):
        entry = _parse_line(raw, line_no, errors)
        if entry is None:
            continue
        if entry.name in seen:
            errors.append(f"line {line_no}: duplicate section id '{entry.name}'")
            continue
        seen.add(entry.name)
        entries.append(entry)

    if errors:
        return ManifestResult(False, entries=entries, errors=errors)
    if not entries:
        return ManifestResult(False, errors=["No valid sections found"])
    return ManifestResult(True, entries=entries)


def parse_manifest(plan_path: Path | str) -> ManifestResult:
    """Read ``plan_path`` and parse its ``SECTION_MANIFEST`` block."""
    path = Path(plan_path)
    if not path.exists():
        return ManifestResult(False, errors=[f"Plan not found: {path}"])
    try:
        content = path.read_text(encoding="utf-8", errors="ignore")
    except OSError as exc:
        return ManifestResult(False, errors=[f"Plan not readable: {exc}"])
    return parse_manifest_text(content)


def validate_dependency_order(entries: list[SectionEntry]) -> list[str]:
    """Return the ways the numbering contradicts the declared dependencies.

    Three rules, all consequences of one idea — *a section is built after
    everything it presupposes*:

    1. a section may not presuppose itself;
    2. a dependency must be declared in the same manifest (a plan may only
       order its own sections; anything already built is not a dependency);
    3. a dependency must appear **earlier** in the manifest than the section
       naming it.

    Rule 3 subsumes cycle detection — no cycle can place every member before
    every other member — so there is no separate graph walk to keep correct.

    An empty list means the order is consistent with what was declared. A
    manifest that declares no dependencies returns ``[]``: nothing was
    promised, so nothing is broken.
    """
    position = {e.name: i for i, e in enumerate(entries)}
    errors: list[str] = []

    for entry in entries:
        for dep in entry.dependencies:
            where = f"line {entry.line_no}"
            if dep == entry.name:
                errors.append(f"{where}: section '{entry.name}' depends on itself")
                continue
            if dep not in position:
                errors.append(
                    f"{where}: '{entry.name}' depends on '{dep}', "
                    f"which is not declared in this manifest"
                )
                continue
            if position[dep] > position[entry.name]:
                errors.append(
                    f"{where}: '{entry.name}' depends on '{dep}', "
                    f"which is numbered after it — a prerequisite must come first"
                )

    return errors
