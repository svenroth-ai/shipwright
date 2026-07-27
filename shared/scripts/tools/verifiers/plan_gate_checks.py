"""Plan-phase gates that `SKILL.md` Step 9 claims but never ran.

Step 9 lists seven "verification gates (all must pass)". Several existed only
as instructions to the agent. This module is where they become code.

It lives beside ``plan_checks`` rather than inside it because that module sits
at its bloat baseline; ``run_plan_checks`` appends what is here.

All four now live here: dependency order, requirement coverage,
section→requirement trace, and section quality.

**Leniency for plans written before the formats existed.** ``run_plan_checks``
walks every planning split, so completing split 03 re-checks splits written
months earlier. Those sections declare no ``Requirements:`` field and may use
headings this module does not know — enforcing strictly would strand them. A
split showing no sign of a format therefore produces a ``WARNING`` naming the
migration, marked ``strict_exempt`` so ``--strict`` cannot mass-false-red it;
once **any** section in a split adopts the format, every section in it is held
to it. The in-session gate
(``plugins/shipwright-plan/scripts/checks/check-plan-gates.py``) is strict
regardless: a plan being written today complies.
"""

from __future__ import annotations

import sys
from pathlib import Path

from .common import CheckResult, Severity

_SHARED_SCRIPTS = Path(__file__).resolve().parents[2]
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

from lib.drift_parsers import collect_requirements_from_planning  # noqa: E402
from lib.plan_manifest import parse_manifest, validate_dependency_order  # noqa: E402
from lib.plan_section_quality import (  # noqa: E402
    collect_sections,
    coverage_report,
    quality_problems,
)

__all__ = [
    "PLANNING_DIRNAME",
    "check_fr_coverage_in_sections",
    "check_section_dependency_order",
    "check_section_quality",
    "check_section_traces_to_requirement",
    "find_planning_split_dirs",
]

# Canonical home of the planning artifact set, relative to project_root.
# Mirrors PLANNING_DIR in shared/scripts/lib/artifact_migrations.py.
PLANNING_DIRNAME = ".shipwright/planning"

_NOTHING_TO_VERIFY = "no plan.md under .shipwright/planning/ — nothing to verify"
_MIGRATION_HINT = (
    "add a 'Requirements: FR-..' line to each section (see "
    "shipwright-plan/skills/plan/references/section-index.md)"
)


def find_planning_split_dirs(project_root: Path) -> list[Path]:
    """Every ``.shipwright/planning/<split>/`` directory that contains a
    ``plan.md``. These are the canonical plan roots to iterate over."""
    planning = Path(project_root) / PLANNING_DIRNAME
    if not planning.is_dir():
        return []
    return [
        d for d in sorted(planning.iterdir())
        if d.is_dir() and not d.name.startswith(".") and d.name != "iterate"
        and (d / "plan.md").exists()
    ]


def check_section_dependency_order(project_root: Path) -> CheckResult:
    """A section's declared prerequisites must be numbered before it.

    ``SECTION_MANIFEST`` documents the numbering as the build order, but until
    a line could name what it presupposes, nothing could establish that the
    order was right — a section could be scheduled before the one that produces
    what it needs and no check would notice.

    No leniency branch is needed: a manifest that declares no dependencies
    promises nothing, so the rule is vacuously satisfied for every plan written
    before dependencies were expressible.
    """
    name = "section dependency order matches the numbering"
    splits = find_planning_split_dirs(Path(project_root))
    if not splits:
        return CheckResult(name, True, _NOTHING_TO_VERIFY)

    drift: list[str] = []
    declared = 0
    for split in splits:
        parsed = parse_manifest(split / "plan.md")
        if not parsed.is_valid:
            continue  # covered by check_section_files_match_manifest / id validity
        declared += sum(1 for e in parsed.entries if e.dependencies)
        drift.extend(f"{split.name}: {err}" for err in validate_dependency_order(parsed.entries))

    if drift:
        return CheckResult(name, False, "; ".join(drift))
    return CheckResult(
        name, True,
        f"{declared} declared dependenc(ies) across {len(splits)} split(s), order consistent",
    )


def _live_frs_by_split(project_root: Path) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for fr in collect_requirements_from_planning(project_root):
        out.setdefault(fr.split, set()).add(fr.id)
    return out


def _verdict(name: str, drift: list[str], legacy: list[str], ok_detail: str) -> CheckResult:
    """Hard-fail on drift in an adopting split; warn (strict-exempt) for a split
    that pre-dates the format; pass otherwise."""
    if drift:
        return CheckResult(name, False, "; ".join(drift))
    if legacy:
        return CheckResult(
            name, False, "; ".join(legacy),
            severity=Severity.WARNING.value, strict_exempt=True,
        )
    return CheckResult(name, True, ok_detail)


def check_fr_coverage_in_sections(project_root: Path) -> CheckResult:
    """Every live requirement of a split must land in at least one section."""
    name = "every requirement lands in a section"
    root = Path(project_root)
    splits = find_planning_split_dirs(root)
    if not splits:
        return CheckResult(name, True, _NOTHING_TO_VERIFY)

    frs = _live_frs_by_split(root)
    drift: list[str] = []
    legacy: list[str] = []
    for split in splits:
        sections = collect_sections(split)
        if not sections:
            continue
        report = coverage_report(sections, frs.get(split.name, set()))
        if not report.uncovered_frs:
            continue
        message = (
            f"{split.name}: {len(report.uncovered_frs)} requirement(s) in no section: "
            f"{report.uncovered_frs[:5]}"
        )
        (drift if report.adopted else legacy).append(
            message if report.adopted else f"{message} — {_MIGRATION_HINT}"
        )

    return _verdict(name, drift, legacy, f"{len(splits)} split(s) fully covered")


def check_section_traces_to_requirement(project_root: Path) -> CheckResult:
    """Every section must name at least one live requirement it serves.

    The mirror of FR coverage, and the one that stops a plan quietly adding work
    nobody asked for — which the constitution forbids in prose and nothing
    enforced.
    """
    name = "every section traces back to a requirement"
    root = Path(project_root)
    splits = find_planning_split_dirs(root)
    if not splits:
        return CheckResult(name, True, _NOTHING_TO_VERIFY)

    frs = _live_frs_by_split(root)
    drift: list[str] = []
    legacy: list[str] = []
    checked = 0
    for split in splits:
        sections = collect_sections(split)
        checked += len(sections)
        if not sections:
            continue
        report = coverage_report(sections, frs.get(split.name, set()))
        if not report.untraced_sections:
            continue
        message = (
            f"{split.name}: section(s) naming no live requirement: "
            f"{report.untraced_sections[:5]}"
        )
        if report.unknown_refs:
            message += f" (unrecognised ids: {report.unknown_refs})"
        (drift if report.adopted else legacy).append(
            message if report.adopted else f"{message} — {_MIGRATION_HINT}"
        )

    return _verdict(name, drift, legacy, f"{checked} section(s) trace to a requirement")


def check_section_quality(project_root: Path) -> CheckResult:
    """Every section says what it is for, lists >=2 steps, and states how it
    will be tested."""
    name = "sections state purpose, steps and test strategy"
    splits = find_planning_split_dirs(Path(project_root))
    if not splits:
        return CheckResult(name, True, _NOTHING_TO_VERIFY)

    drift: list[str] = []
    legacy: list[str] = []
    checked = 0
    for split in splits:
        sections = collect_sections(split)
        checked += len(sections)
        # Adoption is decided once PER SPLIT, matching the Requirements rule: as
        # soon as one section is written in a shape this module recognises, the
        # split has adopted the format and every section in it is held to it.
        # Deciding per section would let one unrecognised file in an otherwise
        # modern split slip by as "legacy".
        adopted = any(s.uses_known_shape for s in sections)
        for section in sections:
            problems = quality_problems(section)
            if not problems:
                continue
            target = drift if adopted else legacy
            target.extend(f"{split.name}/{p}" for p in problems)

    if legacy and not drift:
        legacy = [
            f"{len(legacy)} problem(s) in section(s) written before this gate "
            f"(none use a recognised heading) — {_MIGRATION_HINT}; first: {legacy[0]}"
        ]
    return _verdict(name, drift, legacy, f"{checked} section(s) well-formed")
