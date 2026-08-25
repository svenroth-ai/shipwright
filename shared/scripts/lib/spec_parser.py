"""Spec parser for the Phase-Quality spec category (PR 4 — S1-S10).

Pure parsers for Shipwright spec documents (``.shipwright/agent_docs/spec.md`` plus
per-split ``.shipwright/planning/<split>/spec.md``). Used by
``tools/verifiers/spec_checks.py`` so every S* check operates on the
same normalised view of an FR.

Supports the three shapes Shipwright writes today:

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

3. **Shipped form** (``/shipwright-project``/``/shipwright-adopt`` output)::

       ### FR-01.01 — Title
       - (E) Given ..., when ..., then ...

   No bold label — bare bullets under the heading, description in the FR
   table instead. When labelled extraction finds nothing,
   ``parse_fr_headings`` falls back to ``lib.fr_criteria.leading_criteria``
   (same reader as ``_layer_coverage_ac``/I6 — see its docstring for the
   shape + adjacency rule). A table-row heading is a detail section, not
   a definition (see ``compute_fr_coherence``).

Everything in this module is pure, read-only, and greenfield-safe —
missing inputs return empty results instead of raising.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

# Package import is safe here (unlike drift_parsers): every consumer reaches this
# module as ``lib.spec_parser``, so ``lib`` is always the SHARED package (ADR-045).
from lib import fr_criteria, fr_table_reader
from lib.planning_discovery import iter_spec_files, iter_split_dirs


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
    """``FR 7`` → ``FR-7``; dotted ids keep their dots (wire convention
    used in spec tables and RTM rows, e.g. ``FR-02.03``)."""
    return raw.strip().replace(" ", "-")


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
    """Return the text under the first matching labelled header.

    Accumulates from ``**Description:**`` (or equivalent) to the next
    labelled line or end-of-body; blank lines are kept as paragraph
    separators so ``has_description`` can see "label present but empty".
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

    Walks the document once for heading lines, then per heading extracts
    up to the next FR-heading (any rank) and runs the labelled-block
    scanner. Returns ``[]`` when no FR headings are found.
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
        if not acceptance:
            # Shipped form (S2) — see fr_criteria's docstring.
            fallback = fr_criteria.leading_criteria(body_lines)
            if fallback:
                acceptance = "\n".join(fallback)
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
    """Return the text of the project's top-level spec, or ``None``.

    Reads ``.shipwright/agent_docs/spec.md`` (greenfield canonical,
    ``/shipwright-project``); falls back to the first deterministically-
    sorted ``.shipwright/planning/*/spec.md`` (``/shipwright-adopt``
    brownfield layout). ``None`` only when neither location has a spec.
    """
    path = project_root / _AGENT_DOCS_DIRNAME / "spec.md"
    if path.exists():
        try:
            return path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return None
    # Adopt layout: the spec lives under a planning split, not agent_docs.
    planning = project_root / _PLANNING_DIRNAME
    for candidate in iter_spec_files(planning):   # was sorted(glob("*/spec.md"))
        try:
            return candidate.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
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
    """Yield every spec file for coherence checks, in stable sorted order:
    ``.shipwright/agent_docs/spec.md``, each ``.shipwright/planning/<split>/spec.md``,
    and every ``.shipwright/planning/iterate/*.md`` (per-run iterate specs)."""
    top = project_root / _AGENT_DOCS_DIRNAME / "spec.md"
    if top.exists():
        yield top

    planning = project_root / _PLANNING_DIRNAME
    # Still a generator (corpus records "generator"); iterate/ stays special-cased.
    for split_dir in iter_split_dirs(planning):
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
    **and** Acceptance section — except a heading whose id is ALSO a row
    of the file's own FR table (S3): that's a detail section, not a
    definition, so its table-cell description exempts it from
    ``missing_description`` regardless of its own body.
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
        # Only a NON-EMPTY cell exempts a heading (external review 2026-08-25).
        table_row_ids = {r.id for r in fr_table_reader.read_fr_rows(text) if r.text.strip()}
        for h in headings:
            total += 1
            has_desc = h.has_description() or h.id in table_row_ids
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
