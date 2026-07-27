#!/usr/bin/env python3
"""Reading planned user journeys out of ``claude-plan-e2e.md``.

Split from ``journey_coverage`` (which compares them against the spec tree) so
each file stays inside the 300-line guideline: this one answers *what did the
plan promise*, the other answers *is it tested*.

The heading grammar is a superset of the one the compliance RTM already counts
flows with (``rtm_generator._collect_e2e_coverage_by_split`` matches
``### Flow N``): every h3 inside ``## User Flows`` is a journey, with the
canonical ``Flow N:`` prefix stripped when present. Same vocabulary, wider
tolerance — a plan that heads its journeys plainly must not silently report
``undetermined``, which would hand back the all-or-nothing behaviour this
module exists to remove.

iterate-2026-07-27-test-phase-record-honesty, FR-01.06.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from text_safety import sanitize

# Inside `## User Flows`, EVERY h3 is a journey. The canonical generator emits
# `### Flow N: Title` (`e2e-test-plan.md`), which is what the compliance RTM
# counts — but a hand-written or older plan may head a journey plainly, and
# reporting those as `undetermined` would silently return the all-or-nothing
# behaviour this module exists to remove. The `Flow N:` prefix is stripped when
# present so both spellings yield the same slug.
_JOURNEY_HEADING = re.compile(r"^###\s+(?P<title>.+?)\s*$", re.MULTILINE)
_FLOW_PREFIX = re.compile(r"^Flow\s+\d+\s*:\s*", re.IGNORECASE)
_USER_FLOWS_SECTION = re.compile(r"^##\s+User Flows\s*$", re.MULTILINE)
_NEXT_H2 = re.compile(r"^##\s+(?!User Flows)", re.MULTILINE)

# Numbered list items are NOT read as journeys. In the canonical plan shape the
# numbered/bulleted lines under a heading are the journey's *steps* ("Navigate
# to /signup", "Fill email"), so treating them as journeys would manufacture a
# dozen phantom gaps per plan — worse than the gap being missed.


@dataclass(frozen=True)
class Journey:
    """One planned user journey.

    ``identity`` is position + slug, so two journeys that happen to share a
    title stay two distinct items rather than collapsing into one.
    """

    index: int
    title: str
    slug: str

    @property
    def identity(self) -> str:
        return f"{self.index:02d}-{self.slug}"


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", sanitize(text).lower()).strip("-")


def parse_journeys(plan_text: str) -> list[Journey]:
    """Read journey headings from the plan's ``## User Flows`` section.

    Every h3 inside that section is a journey; the canonical ``Flow N:`` prefix
    is stripped when present. Headings outside the section (Page Object Model,
    Test Environment, ...) are not journeys.
    """
    match = _USER_FLOWS_SECTION.search(plan_text)
    section = plan_text[match.end():] if match else plan_text
    end = _NEXT_H2.search(section)
    if end:
        section = section[: end.start()]

    journeys: list[Journey] = []
    for i, m in enumerate(_JOURNEY_HEADING.finditer(section), start=1):
        title = sanitize(_FLOW_PREFIX.sub("", m.group("title").strip()))
        slug = slugify(title)
        if title and slug:
            journeys.append(Journey(index=i, title=title, slug=slug))
    return journeys


def plan_files(project_root: Path) -> list[Path]:
    """Every E2E plan under ``.shipwright/planning/``, in a stable order."""
    planning = project_root / ".shipwright" / "planning"
    if not planning.exists():
        return []
    return sorted(planning.rglob("claude-plan-e2e.md"))


def spec_files(project_root: Path) -> list[Path]:
    """Every Playwright spec under ``e2e/``, at any depth."""
    e2e = project_root / "e2e"
    if not e2e.exists():
        return []
    return sorted(e2e.rglob("*.spec.ts"))


__all__ = ["Journey", "parse_journeys", "plan_files", "slugify", "spec_files"]
