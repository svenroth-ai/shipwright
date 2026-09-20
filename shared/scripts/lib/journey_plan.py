"""Read planned user journeys from ``claude-plan-e2e.md``.

This is shared because both the test-phase producer and the phase verifier
must answer the same question about what an E2E plan promises (ADR-045).
"""

from __future__ import annotations

import re
import os
from dataclasses import dataclass
from pathlib import Path

from .text_safety import sanitize

_JOURNEY_HEADING = re.compile(r"^###[ \t]*(?!#)(?P<title>[^\r\n]*)[ \t]*$", re.MULTILINE)
_FLOW_PREFIX = re.compile(r"^Flow[ \t]+\d+[ \t]*:[ \t]*", re.IGNORECASE)
_USER_FLOWS_SECTION = re.compile(r"^##[ \t]+User Flows[ \t]*$", re.MULTILINE)
_NEXT_H2 = re.compile(r"^##(?!#)[ \t]+(?!User Flows[ \t]*$)[^\r\n]*$", re.MULTILINE)


def _is_within(project_root: Path, candidate: Path) -> bool:
    """Keep plan/spec symlinks from making project-local coverage claim external files."""
    try:
        root = str(project_root.resolve())
        return os.path.commonpath([root, str(candidate.resolve())]) == root
    except (OSError, ValueError):
        return False


@dataclass(frozen=True)
class Journey:
    """One planned user journey, uniquely identified by position and slug."""

    index: int
    title: str
    slug: str

    @property
    def identity(self) -> str:
        return f"{self.index:02d}-{self.slug}"


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", sanitize(text).lower()).strip("-")


def _journey_section(plan_text: str, *, require_user_flows_section: bool) -> str:
    match = _USER_FLOWS_SECTION.search(plan_text)
    if require_user_flows_section and not match:
        return ""
    section = plan_text[match.end():] if match else plan_text
    end = _NEXT_H2.search(section)
    return section[:end.start()] if end else section


def malformed_flow_headings(
    plan_text: str, *, require_user_flows_section: bool = False,
) -> int:
    """Count User Flows H3 headings whose title normalizes unusably."""
    malformed = 0
    for match in _JOURNEY_HEADING.finditer(
        _journey_section(plan_text, require_user_flows_section=require_user_flows_section)
    ):
        raw_title = (match.group("title") or "").strip()
        title = sanitize(_FLOW_PREFIX.sub("", raw_title))
        if not title or not slugify(title):
            malformed += 1
    return malformed


def parse_journeys(
    plan_text: str, *, require_user_flows_section: bool = False,
) -> list[Journey]:
    """Read every H3 journey inside the plan's ``## User Flows`` section."""
    section = _journey_section(plan_text, require_user_flows_section=require_user_flows_section)

    journeys: list[Journey] = []
    for i, match in enumerate(_JOURNEY_HEADING.finditer(section), start=1):
        title = sanitize(_FLOW_PREFIX.sub("", (match.group("title") or "").strip()))
        slug = slugify(title)
        if title and slug:
            journeys.append(Journey(index=i, title=title, slug=slug))
    return journeys


def plan_files(project_root: Path) -> list[Path]:
    """Return every E2E plan below ``.shipwright/planning`` in stable order."""
    planning = project_root / ".shipwright" / "planning"
    return (
        [path for path in sorted(planning.rglob("claude-plan-e2e.md")) if _is_within(project_root, path)]
        if planning.exists() else []
    )


def spec_files(project_root: Path) -> list[Path]:
    """Return every Playwright spec below ``e2e`` in stable order."""
    e2e = project_root / "e2e"
    return (
        [path for path in sorted(e2e.rglob("*.spec.ts")) if _is_within(project_root, path)]
        if e2e.exists() else []
    )


__all__ = ["Journey", "malformed_flow_headings", "parse_journeys", "plan_files", "slugify", "spec_files"]
