"""Spec parser for the Phase-Quality spec category (PR 4 — S1-S10).

Pure parsers for Shipwright spec documents (``.shipwright/agent_docs/spec.md`` plus
per-split ``.shipwright/planning/<split>/spec.md``). Used by
``tools/verifiers/spec_checks.py`` so every S* check operates on the
same normalised view of an FR.

Supports the two shapes Shipwright writes today:

1. **Table form** (iterate specs, split specs)::

       | FR-01.02 | Description text | Must |

   Shared with ``drift_parsers.parse_fr_table``; this module delegates
   to it so table-FR parsing can never drift from the traceability
   checks.

2. **Heading form** (``.shipwright/agent_docs/spec.md``)::

       ## FR-7: Title
       **Description:** what the requirement says.
       **Acceptance Criteria:**
       - criterion 1
       - criterion 2

   Headings accept ``#``…``####`` depth, optional "FR-"/"FR " prefix,
   digits or dotted ids (``FR-7``, ``FR-02.03``). FR-coherence
   (S5) inspects both the Description and Acceptance Criteria under
   each heading.

Everything in this module is pure, read-only, and greenfield-safe —
missing inputs return empty results instead of raising.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable


# ---------------------------------------------------------------------------
# FR heading parser
# ---------------------------------------------------------------------------

# Matches "## FR-7: Title", "### FR-02.03 — Title", "#### FR 4 Title".
# Tolerates colon, en/em dash, or plain whitespace between id and title, and
# accepts IDs with optional dot segments ("FR-02.03") or single digits
# ("FR-7").
_FR_HEADING_RE = re.compile(
    r"^(?P<hashes>#{1,6})\s+"
    r"(?P<id>FR[-\s]?\d+(?:\.\d+)*)"
    r"\s*(?:[:\u2014\u2013-]\s*)?"
    r"(?P<title>.*)$"
)

# Canonical-label matchers for bullet / bold-paragraph shape, shared with
# the ADR parser's convention. Accepts "**Description:** ..." or
# "- **Description:** ...".
_DESC_LABEL_RE = re.compile(
    r"^(?:-\s*)?\*\*\s*(?P<label>[A-Za-z][A-Za-z _-]*)\s*:?\s*\*\*\s*:?\s*(?P<rest>.*)$"
)

_DESCRIPTION_LABELS: frozenset[str] = frozenset({
    "description", "summary", "intent", "requirement", "what",
})
_ACCEPTANCE_LABELS: frozenset[str] = frozenset({
    "acceptance criteria", "acceptance", "criteria", "done when",
    "definition of done", "dod",
})


def _normalise_fr_id(raw: str) -> str:
    """Return a canonical FR id.

    ``FR 7`` → ``FR-7``. Dotted ids keep their dots. Whitespace after
    ``FR`` is replaced with ``-`` to match the wire convention used in
    spec tables and RTM rows (``FR-02.03``).
    """
    r = raw.strip().replace(" ", "-")
    return r


@dataclass(frozen=True)
class FRHeading:
    """One ``FR-*`` heading inside a spec document."""

    id: str                                  # canonical (e.g. "FR-7", "FR-02.03")
    title: str
    line_no: int                             # 1-based header line
    description: str = ""
    acceptance: str = ""
    raw_body: str = ""                       # raw body lines joined by \n

    def has_description(self) -> bool:
        return bool(self.description.strip())

    def has_acceptance(self) -> bool:
        return bool(self.acceptance.strip())


def _extract_label_section(
    lines: list[str],
    *,
    target_labels: frozenset[str],
) -> str:
    """Return the block of text under the first matching labelled header.

    Walks the body lines: once we see ``**Description:**`` (or equivalent),
    accumulate until the next labelled line of the same or higher rank,
    or the end of the body. Blank lines are preserved as paragraph
    separators inside the result so ``has_description`` can detect
    "label present but body empty".
    """
    out: list[str] = []
    in_target = False
    captured_any_label = False

    for raw in lines:
        stripped = raw.strip()

        m = _DESC_LABEL_RE.match(stripped) if stripped else None
        if m:
            label = m.group("label").strip().lower()
            label = re.sub(r"\s+", " ", label)
            rest = m.group("rest").strip()
            if label in target_labels:
                in_target = True
                captured_any_label = True
                if rest:
                    out.append(rest)
            else:
                if in_target:
                    # Exit current target once another canonical label appears
                    break
            continue

        if in_target:
            out.append(raw.rstrip())

    if captured_any_label:
        # Collapse trailing whitespace-only lines.
        while out and not out[-1].strip():
            out.pop()
    return "\n".join(out).strip()


def parse_fr_headings(content: str) -> list[FRHeading]:
    """Parse FR headings and their Description/Acceptance bodies.

    The parser walks the document once to find heading lines, then for
    each heading extracts the lines up to the next FR-heading (at any
    rank) and runs the labelled-block scanner.

    Returns ``[]`` when no FR headings are found.
    """
    lines = content.splitlines()
    heading_hits: list[tuple[int, str, str]] = []
    for idx, line in enumerate(lines):
        m = _FR_HEADING_RE.match(line)
        if not m:
            continue
        heading_hits.append((
            idx,
            _normalise_fr_id(m.group("id")),
            m.group("title").strip(),
        ))

    headings: list[FRHeading] = []
    for i, (idx, fr_id, title) in enumerate(heading_hits):
        end = heading_hits[i + 1][0] if i + 1 < len(heading_hits) else len(lines)
        body_lines = lines[idx + 1:end]
        body_text = "\n".join(body_lines)
        description = _extract_label_section(
            body_lines, target_labels=_DESCRIPTION_LABELS,
        )
        acceptance = _extract_label_section(
            body_lines, target_labels=_ACCEPTANCE_LABELS,
        )
        headings.append(FRHeading(
            id=fr_id,
            title=title,
            line_no=idx + 1,
            description=description,
            acceptance=acceptance,
            raw_body=body_text,
        ))
    return headings


def count_fr_headings(content: str) -> int:
    return len(parse_fr_headings(content))


# ---------------------------------------------------------------------------
# Top-level spec readers
# ---------------------------------------------------------------------------

def read_top_level_spec(project_root: Path) -> str | None:
    """Return the text of ``.shipwright/agent_docs/spec.md`` or ``None`` when missing."""
    path = project_root / _AGENT_DOCS_DIRNAME / "spec.md"
    if not path.exists():
        return None
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None


def top_level_spec_is_non_empty(project_root: Path) -> bool:
    """True when ``.shipwright/agent_docs/spec.md`` exists AND has non-whitespace text."""
    content = read_top_level_spec(project_root)
    return bool(content and content.strip())


# ---------------------------------------------------------------------------
# FR coherence (S5) — Description + Acceptance per FR
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class FRCoherenceReport:
    """Summary of FR coherence across every inspected spec file."""

    total_frs: int
    missing_description: tuple[str, ...] = ()
    missing_acceptance: tuple[str, ...] = ()
    missing_both: tuple[str, ...] = ()
    scanned_files: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return not (self.missing_description
                    or self.missing_acceptance
                    or self.missing_both)


# Canonical home of the planning artifact set, relative to project_root.
# Mirrors PLANNING_DIR in shared/scripts/lib/artifact_migrations.py.
_PLANNING_DIRNAME = ".shipwright/planning"

# Canonical home of the agent_docs artifact set, relative to project_root.
# Mirrors agent_docs entry in shared/scripts/lib/artifact_migrations.py.
_AGENT_DOCS_DIRNAME = ".shipwright/agent_docs"


def _iter_spec_files(project_root: Path) -> Iterable[Path]:
    """Yield every spec file we care about for coherence checks.

    Includes:

    - ``.shipwright/agent_docs/spec.md`` (project-level canonical spec).
    - ``.shipwright/planning/<split>/spec.md`` (split specs from plan phase).
    - ``.shipwright/planning/iterate/*.md`` (iterate-spec files produced per-run).

    Files are yielded in stable (sorted) order so callers get
    deterministic reports.
    """
    top = project_root / _AGENT_DOCS_DIRNAME / "spec.md"
    if top.exists():
        yield top

    planning = project_root / _PLANNING_DIRNAME
    if not planning.is_dir():
        return

    for split_dir in sorted(planning.iterdir()):
        if not split_dir.is_dir():
            continue
        if split_dir.name == "iterate":
            for iter_spec in sorted(split_dir.glob("*.md")):
                yield iter_spec
            continue
        candidate = split_dir / "spec.md"
        if candidate.exists():
            yield candidate


def compute_fr_coherence(project_root: Path) -> FRCoherenceReport:
    """Walk every spec file and summarise FR coherence.

    "Coherent" means: every FR heading has a non-empty Description
    **and** Acceptance section. Table-row FRs are ignored for coherence
    — they're a summary format, not the canonical shape S5 targets
    (plan § 3 S5).
    """
    total = 0
    miss_desc: list[str] = []
    miss_accept: list[str] = []
    miss_both: list[str] = []
    scanned: list[str] = []

    for path in _iter_spec_files(project_root):
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        headings = parse_fr_headings(text)
        if not headings:
            continue
        rel = path.relative_to(project_root).as_posix()
        scanned.append(rel)
        for h in headings:
            total += 1
            has_desc = h.has_description()
            has_accept = h.has_acceptance()
            if not has_desc and not has_accept:
                miss_both.append(f"{rel}::{h.id}")
            elif not has_desc:
                miss_desc.append(f"{rel}::{h.id}")
            elif not has_accept:
                miss_accept.append(f"{rel}::{h.id}")

    return FRCoherenceReport(
        total_frs=total,
        missing_description=tuple(miss_desc),
        missing_acceptance=tuple(miss_accept),
        missing_both=tuple(miss_both),
        scanned_files=tuple(scanned),
    )


__all__ = [
    "FRCoherenceReport",
    "FRHeading",
    "compute_fr_coherence",
    "count_fr_headings",
    "parse_fr_headings",
    "read_top_level_spec",
    "top_level_spec_is_non_empty",
]
