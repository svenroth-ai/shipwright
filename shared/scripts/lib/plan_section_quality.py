"""What a plan section must say, and how it links back to requirements.

``/shipwright-plan`` Step 9 has long listed a *Section Quality Gate* and an
*FR Coverage Check* among its "verification gates (all must pass)". Neither
existed in code. The FR check that did exist
(``plan_checks.check_fr_orphans_in_plan``) looks only outward — a cited FR must
exist in the spec — so nothing established that every requirement is covered,
and nothing established that a section traces back to a requirement at all. A
plan could therefore quietly add work nobody asked for, which the constitution
forbids in prose and nothing enforced.

Two things live here:

* **shape** — a section says what it is for, lists at least two implementation
  steps, and states how it will be tested (:func:`quality_problems`);
* **linkage** — both coverage directions (:func:`coverage_report`).

Linkage is read from one explicit ``Requirements:`` field, never from a prose
scan for ``FR-NN.NN``. A scan would count an id named in an example, a
rationale, or a retired-history note as coverage, and would teach authors to
sprinkle ids to satisfy the gate. One field, parsed in one place, also gives
``/shipwright-build`` the same linkage the gate uses.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

__all__ = [
    "CoverageReport",
    "PURPOSE_HEADINGS",
    "SectionQuality",
    "STEP_HEADINGS",
    "TEST_HEADINGS",
    "collect_sections",
    "coverage_report",
    "parse_section_file",
    "quality_problems",
]

# Closed synonym sets. Deliberately small: the section-writer prompt and the
# section-splitting template emit the first entry of each, and the rest exist
# so a hand-written section in a reasonable shape is not failed on wording.
PURPOSE_HEADINGS = ("overview", "purpose", "description", "goal")
STEP_HEADINGS = ("implementation steps", "implementation", "steps")
TEST_HEADINGS = ("tests first", "test strategy", "tests", "testing", "test plan")

_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+(?P<title>.+?)\s*#*\s*$")
_LIST_ITEM_RE = re.compile(r"^\s*(?:\d+[.)]|[-*+])\s+\S")
_REQUIREMENTS_RE = re.compile(
    r"^[\s>*_\-]*requirements[\s*_`]*:(?P<ids>.*)$",
    re.IGNORECASE | re.MULTILINE,
)
_FR_ID_RE = re.compile(r"FR-\d{1,3}\.\d{1,3}")


@dataclass(frozen=True)
class SectionQuality:
    """One section file, read for shape and requirement linkage."""

    name: str
    has_purpose: bool = False
    step_count: int = 0
    has_tests: bool = False
    requirements: tuple[str, ...] = ()
    #: The ``Requirements:`` field is present — even if it names nothing. This
    #: is what decides whether a split has adopted the format, deliberately
    #: separate from whether the field is *usable*: a section that writes the
    #: field but leaves it empty has adopted the format and failed it, which
    #: is a very different thing from a plan that predates the field.
    declares_requirements: bool = False

    @property
    def uses_known_shape(self) -> bool:
        """True once **any** of the three parts is recognisable.

        A section with none of them is either empty or written in a shape this
        module does not know, which is what a plan predating the gate looks
        like. A lenient caller uses this to warn instead of fail; the
        in-session gate ignores it, because a section written today complies.
        """
        return self.has_purpose or self.step_count > 0 or self.has_tests


@dataclass
class CoverageReport:
    """Both directions of section↔requirement linkage for one split."""

    uncovered_frs: list[str]
    untraced_sections: list[str]
    unknown_refs: dict[str, list[str]]
    adopted: bool


def _headings(content: str) -> dict[str, str]:
    """Map lower-cased heading title → its body text (up to the next heading)."""
    out: dict[str, str] = {}
    title: str | None = None
    buf: list[str] = []
    for line in content.splitlines():
        m = _HEADING_RE.match(line)
        if m:
            if title is not None:
                out.setdefault(title, "\n".join(buf))
            title = m.group("title").strip().lower()
            buf = []
        elif title is not None:
            buf.append(line)
    if title is not None:
        out.setdefault(title, "\n".join(buf))
    return out


def _body_for(headings: dict[str, str], names: tuple[str, ...]) -> str | None:
    for name in names:
        if name in headings:
            return headings[name]
    return None


def parse_section_file(path: Path | str) -> SectionQuality:
    """Read one ``sections/<id>.md`` file.

    A missing or unreadable file yields an empty result rather than raising —
    "the file is not there" is already reported by the manifest-vs-disk check,
    and one broken file must not hide the rest of the split.
    """
    p = Path(path)
    try:
        content = p.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return SectionQuality(name=p.stem)

    headings = _headings(content)

    purpose_body = _body_for(headings, PURPOSE_HEADINGS)
    steps_body = _body_for(headings, STEP_HEADINGS)
    tests_body = _body_for(headings, TEST_HEADINGS)

    step_count = 0
    if steps_body:
        step_count = sum(1 for line in steps_body.splitlines() if _LIST_ITEM_RE.match(line))

    match = _REQUIREMENTS_RE.search(content)
    requirements = tuple(dict.fromkeys(_FR_ID_RE.findall(match.group("ids")))) if match else ()

    return SectionQuality(
        name=p.stem,
        has_purpose=bool(purpose_body and purpose_body.strip()),
        step_count=step_count,
        has_tests=bool(tests_body and tests_body.strip()),
        requirements=requirements,
        declares_requirements=match is not None,
    )


def collect_sections(split_dir: Path) -> list[SectionQuality]:
    """Read every ``sections/*.md`` under one planning split, name-sorted."""
    sections_dir = Path(split_dir) / "sections"
    if not sections_dir.is_dir():
        return []
    return [parse_section_file(p) for p in sorted(sections_dir.glob("*.md"))]


def quality_problems(section: SectionQuality) -> list[str]:
    """What this section fails to say. Empty means it says all three.

    Each problem names the missing part *and* the heading that would supply
    it, so the fix is obvious from the failure alone.
    """
    problems: list[str] = []
    if not section.has_purpose:
        problems.append(
            f"{section.name}: does not say what it is for "
            f"(expected a non-empty '## Overview')"
        )
    if section.step_count < 2:
        problems.append(
            f"{section.name}: lists {section.step_count} implementation step(s), "
            f"needs at least 2 implementation steps under '## Implementation Steps'"
        )
    if not section.has_tests:
        problems.append(
            f"{section.name}: does not state how it will be tested "
            f"(expected a non-empty '## Tests First')"
        )
    return problems


def coverage_report(
    sections: list[SectionQuality], live_fr_ids: set[str]
) -> CoverageReport:
    """Both coverage directions for one split.

    * ``uncovered_frs`` — live requirements no section declares (AC6);
    * ``untraced_sections`` — sections declaring no live requirement (AC7);
    * ``unknown_refs`` — declared ids that are not live requirements of this
      split, per section;
    * ``adopted`` — whether the split uses the ``Requirements:`` field at all.
      A split that does not pre-dates the field, and a lenient caller reports
      the facts as a warning rather than stranding a plan written before the
      field existed. The facts are computed either way — leniency is the
      caller's decision, not this function's.
    """
    claimed: set[str] = set()
    untraced: list[str] = []
    unknown: dict[str, list[str]] = {}

    for section in sections:
        live = [fr for fr in section.requirements if fr in live_fr_ids]
        stale = [fr for fr in section.requirements if fr not in live_fr_ids]
        if stale:
            unknown[section.name] = sorted(stale)
        if live:
            claimed.update(live)
        else:
            untraced.append(section.name)

    return CoverageReport(
        uncovered_frs=sorted(live_fr_ids - claimed),
        untraced_sections=sorted(untraced),
        unknown_refs=unknown,
        adopted=any(s.declares_requirements for s in sections),
    )
