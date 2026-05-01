"""Prior-art harvester: copy existing decision/convention docs forward.

Brownfield repos almost always carry maintainer-written knowledge that
adopt's old pipeline silently dropped — leaving operators with an empty
ADR-0001 decision log and a thin auto-conventions doc despite a perfectly
good `docs/adr/` next door.

This module is deterministic, regex-based, and best-effort:

- File paths and section headings only — no NLP, no LLM extraction.
- First hit wins. Higher-signal sources outrank lower-signal ones.
- Absence is silent: callers fall back to today's behavior when None
  is returned.

Two public entry points: `harvest_decision_log()` and
`harvest_conventions()`. Both return a `HarvestResult` or `None`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class HarvestResult:
    """One successful harvest. `content` is markdown ready to embed verbatim
    into the target artifact. `source_path` is relative to `project_root`,
    used for the attribution header. `entry_count` is best-effort (used for
    audit trail / test assertions; not critical to consumers)."""

    content: str
    source_path: str
    entry_count: int


# ---------------------------------------------------------------------------
# decision_log harvesting
# ---------------------------------------------------------------------------


# Higher index = higher priority. The order encodes "richest signal first".
_ADR_DIR_CANDIDATES: tuple[str, ...] = (
    "docs/adr",
    "docs/architecture/decisions",
    "docs/decisions",
    "ADRs",
)

_ADR_FILE_CANDIDATES: tuple[str, ...] = (
    "decision_log.md",
    "agent_docs/decision_log.md",  # artifact-path-canon: legacy
    # Pre-Shipwright brownfield projects may carry an ADR at the pre-shipwright
    # location — adopting them is exactly the migration path moving away from.
    # We MUST keep looking for it during /shipwright-adopt's harvest pass.
)

_README_CANDIDATES: tuple[str, ...] = ("README.md", "readme.md", "Readme.md")

_README_DECISION_HEADINGS = re.compile(
    r"^#{2,3}\s+(Architecture|Design decisions|Architecture decisions|"
    r"Architectural decisions|System design)\s*$",
    re.IGNORECASE | re.MULTILINE,
)


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def _harvest_adr_directory(directory: Path, source_label: str) -> HarvestResult | None:
    """Concatenate every *.md file in the directory in sorted order."""
    if not directory.is_dir():
        return None
    files = sorted(p for p in directory.iterdir() if p.is_file() and p.suffix == ".md")
    if not files:
        return None
    blocks: list[str] = []
    for f in files:
        body = _read_text(f).strip()
        if not body:
            continue
        blocks.append(f"<!-- source: {source_label}/{f.name} -->\n\n{body}\n")
    if not blocks:
        return None
    content = "\n---\n\n".join(blocks)
    return HarvestResult(content=content, source_path=source_label, entry_count=len(blocks))


def _harvest_adr_file(file_path: Path, source_label: str) -> HarvestResult | None:
    if not file_path.is_file():
        return None
    body = _read_text(file_path).strip()
    if not body:
        return None
    # Count `## ADR-NNN` or `## NNN.` style headings; fall back to 1.
    adr_re = re.compile(r"^##\s+(ADR-\d+|\d+\.)", re.MULTILINE)
    count = max(1, len(adr_re.findall(body)))
    return HarvestResult(content=body, source_path=source_label, entry_count=count)


def _harvest_readme_section(
    project_root: Path, heading_re: re.Pattern[str], source_label_suffix: str = ""
) -> HarvestResult | None:
    """Pull a labeled section out of the project's README.

    Captures everything between the matched heading and the next H1/H2/H3.
    `source_label_suffix` is appended to the source path for clarity in
    attribution headers (e.g. README.md#architecture)."""
    for name in _README_CANDIDATES:
        readme = project_root / name
        if not readme.is_file():
            continue
        body = _read_text(readme)
        match = heading_re.search(body)
        if not match:
            continue
        section_start = match.start()
        # Find next sibling heading (H1/H2/H3) AFTER our match. If our heading
        # is H3 we still stop at the next H2, etc. — simplest safe rule.
        next_heading = re.search(
            r"^#{1,3}\s+\S",
            body[match.end():],
            re.MULTILINE,
        )
        section_end = (
            match.end() + next_heading.start() if next_heading else len(body)
        )
        section = body[section_start:section_end].strip()
        if not section:
            continue
        label = name + (f"#{source_label_suffix}" if source_label_suffix else "")
        return HarvestResult(content=section, source_path=label, entry_count=1)
    return None


def harvest_decision_log(project_root: Path) -> HarvestResult | None:
    """Look for an existing decision log and return its content for embedding.

    Priority: directory layouts (richest) → root files → README section.
    """
    # Directories first (richest signal)
    for rel in _ADR_DIR_CANDIDATES:
        result = _harvest_adr_directory(project_root / rel, rel)
        if result is not None:
            return result
    # Single-file logs
    for rel in _ADR_FILE_CANDIDATES:
        result = _harvest_adr_file(project_root / rel, rel)
        if result is not None:
            return result
    # README section as last resort
    return _harvest_readme_section(
        project_root,
        _README_DECISION_HEADINGS,
        source_label_suffix="architecture",
    )


# ---------------------------------------------------------------------------
# conventions harvesting
# ---------------------------------------------------------------------------


_CONVENTIONS_FILE_CANDIDATES: tuple[str, ...] = (
    "CONTRIBUTING.md",
    "STYLEGUIDE.md",
    "docs/conventions.md",
    "docs/CONVENTIONS.md",
)

_README_CONVENTION_HEADINGS = re.compile(
    r"^#{2,3}\s+(Conventions|Code style|Coding standards|Style|"
    r"Architecture rules|DO[\s\-]NOT|Do not)\s*$",
    re.IGNORECASE | re.MULTILINE,
)

# AGENTS.md / CLAUDE.md sections worth lifting.
_AGENT_DOC_HEADINGS = re.compile(
    r"^#{1,3}\s+(Conventions|Coding standards|Style|Architecture rules|"
    r"DO[\s\-]NOT|Do not)\s*$",
    re.IGNORECASE | re.MULTILINE,
)


def _harvest_agent_doc_section(
    project_root: Path, filenames: tuple[str, ...]
) -> HarvestResult | None:
    """Pull an explicit `## Conventions` (or similar) section out of AGENTS.md
    or CLAUDE.md. Whole-file harvest is wrong here — these files carry lots
    of unrelated content."""
    for fname in filenames:
        path = project_root / fname
        if not path.is_file():
            continue
        body = _read_text(path)
        match = _AGENT_DOC_HEADINGS.search(body)
        if not match:
            continue
        # Stop at the next sibling heading (any H1-H3).
        next_heading = re.search(
            r"^#{1,3}\s+\S",
            body[match.end():],
            re.MULTILINE,
        )
        end = match.end() + next_heading.start() if next_heading else len(body)
        section = body[match.start():end].strip()
        if section:
            return HarvestResult(
                content=section,
                source_path=f"{fname}#conventions",
                entry_count=1,
            )
    return None


def harvest_conventions(project_root: Path) -> HarvestResult | None:
    """Look for an existing conventions document and return its content.

    Priority: dedicated files (richest) → README section → AGENTS/CLAUDE
    sections (sparse, often most reliable when they exist).
    """
    for rel in _CONVENTIONS_FILE_CANDIDATES:
        path = project_root / rel
        if not path.is_file():
            continue
        body = _read_text(path).strip()
        if not body:
            continue
        return HarvestResult(content=body, source_path=rel, entry_count=1)

    readme_result = _harvest_readme_section(
        project_root,
        _README_CONVENTION_HEADINGS,
        source_label_suffix="conventions",
    )
    if readme_result is not None:
        return readme_result

    return _harvest_agent_doc_section(project_root, ("AGENTS.md", "CLAUDE.md"))
