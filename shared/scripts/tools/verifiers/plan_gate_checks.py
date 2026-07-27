"""Plan-phase gates that `SKILL.md` Step 9 claims but never ran.

Step 9 lists seven "verification gates (all must pass)". Several existed only
as instructions to the agent. This module is where they become code.

It lives beside ``plan_checks`` rather than inside it because that module sits
at its bloat baseline; ``run_plan_checks`` appends what is here.

This PR lands the dependency-order gate. The remaining three — requirement
coverage, section→requirement trace, and section quality — follow in the next
PR of the same work unit and join this module.
"""

from __future__ import annotations

import sys
from pathlib import Path

from .common import CheckResult

_SHARED_SCRIPTS = Path(__file__).resolve().parents[2]
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

from lib.plan_manifest import parse_manifest, validate_dependency_order  # noqa: E402

__all__ = [
    "PLANNING_DIRNAME",
    "check_section_dependency_order",
    "find_planning_split_dirs",
]

# Canonical home of the planning artifact set, relative to project_root.
# Mirrors PLANNING_DIR in shared/scripts/lib/artifact_migrations.py.
PLANNING_DIRNAME = ".shipwright/planning"

_NOTHING_TO_VERIFY = "no plan.md under .shipwright/planning/ — nothing to verify"


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
