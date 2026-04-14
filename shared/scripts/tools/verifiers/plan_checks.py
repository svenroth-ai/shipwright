"""Plan-phase verifier checks.

Iterate 12.2 brings the ``plan`` plugin to full canon coverage for the
decision-taking + phase-history parts of the Minimum Phase Completion
Canon, and adds two preventive checks adapted from the shipwright-check
plan (Group C2 FR-orphan detection + Group C4 section-id validity).

Canon coverage:

- C1 (phase_completed event) — ERROR
- C2 (build_dashboard mentions plan) — WARNING
- C3 (session_handoff fresh) — WARNING  [NEW in 12.2]
- C4 (decision_log has plan ADR) — ERROR  [already written in Steps 2/5]
- C5 — **SKIPPED BY POLICY**, plan is an internal decomposition, not
  user-facing. No CHANGELOG entry.

Phase-own checks:

- ``check_plan_config_status_complete`` — ERROR
- ``check_section_files_match_manifest`` — wraps the ``SECTION_MANIFEST``
  parser used by ``plugins/shipwright-plan/scripts/checks/check-sections.py``.
  ERROR. Preventive equivalent of shipwright-check Group C3.
- ``check_fr_orphans_in_plan`` — every ``FR-XX.YY`` mentioned in
  ``plan.md`` or ``sections/*.md`` must exist in the parent spec.md
  for the split. ERROR. Adapted from shipwright-check Group C2.
- ``check_section_id_validity`` — section names match the zero-padded
  numeric prefix convention (``^\\d{2}-[a-z0-9-]+$``), are unique, and
  form a gap-free sequence starting at 01. ERROR. Adapted from
  shipwright-check Group C4.

Plus the standard ``phase_history`` run-id check and ADR integrity
helpers from ``common.py``.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from .common import (
    CheckResult,
    Severity,
    check_adr_ids_sequential,
    check_adr_status_valid,
    check_adr_supersession_exists,
    check_c1_phase_event_recorded,
    check_c2_dashboard_reflects_phase,
    check_c3_session_handoff_fresh_after_phase,
    check_c4_decision_log_has_phase_adr,
    check_phase_history_has_run,
)

# Add shared/scripts to path for lib imports.
import sys
_SHARED_SCRIPTS = Path(__file__).resolve().parent.parent.parent
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

from lib.drift_parsers import collect_requirements_from_planning  # noqa: E402


# ---------------------------------------------------------------------------
# Section manifest + section-file parsers
# ---------------------------------------------------------------------------

_SECTION_MANIFEST_RE = re.compile(
    r"<!--\s*SECTION_MANIFEST\s*\n(?P<body>.*?)\nEND_MANIFEST\s*-->",
    re.DOTALL,
)
_SECTION_NAME_RE = re.compile(r"^(?P<num>\d{2})-[a-z0-9]+(?:-[a-z0-9]+)*$")
_FR_REF_RE = re.compile(r"FR-\d{1,3}\.\d{1,3}")


def _parse_section_manifest(plan_path: Path) -> list[str]:
    """Return the ordered list of section names from the SECTION_MANIFEST
    block of ``plan.md``, or an empty list if missing/malformed."""
    if not plan_path.exists():
        return []
    try:
        content = plan_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []
    m = _SECTION_MANIFEST_RE.search(content)
    if not m:
        return []
    names: list[str] = []
    for line in m.group("body").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        names.append(line)
    return names


def _find_planning_split_dirs(project_root: Path) -> list[Path]:
    """Return every ``planning/<split>/`` directory that contains a
    ``plan.md``. These are the canonical plan roots to iterate over."""
    planning = project_root / "planning"
    if not planning.is_dir():
        return []
    out: list[Path] = []
    for d in sorted(planning.iterdir()):
        if not d.is_dir():
            continue
        if d.name.startswith("."):
            continue
        if d.name == "iterate":
            continue
        if (d / "plan.md").exists():
            out.append(d)
    return out


# ---------------------------------------------------------------------------
# Phase-own checks
# ---------------------------------------------------------------------------

def check_plan_config_status_complete(project_root: Path) -> CheckResult:
    """``shipwright_plan_config.json::status`` must be ``complete``."""
    name = "plan_config status=complete"
    path = project_root / "shipwright_plan_config.json"
    if not path.exists():
        return CheckResult(name, False, "shipwright_plan_config.json missing")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return CheckResult(name, False, f"malformed plan config: {exc}")
    status = data.get("status")
    if status != "complete":
        return CheckResult(name, False, f"status={status!r}, expected 'complete'")
    return CheckResult(name, True, "status=complete")


def check_section_files_match_manifest(project_root: Path) -> CheckResult:
    """For every ``planning/<split>/`` that has a ``plan.md``, the
    section names declared in ``SECTION_MANIFEST`` must match the
    ``.md`` files present in ``planning/<split>/sections/``.

    Wraps the same logic as
    ``plugins/shipwright-plan/scripts/checks/check-sections.py`` so the
    verifier's view and the plan plugin's own gate stay in sync.
    """
    name = "section files match SECTION_MANIFEST"
    splits = _find_planning_split_dirs(project_root)
    if not splits:
        return CheckResult(name, True, "no plan.md under planning/ — nothing to verify")

    drift: list[str] = []
    total_declared = 0
    for split in splits:
        declared = _parse_section_manifest(split / "plan.md")
        total_declared += len(declared)
        sections_dir = split / "sections"
        if not sections_dir.is_dir():
            if declared:
                drift.append(f"{split.name}: sections/ dir missing (declared {len(declared)})")
            continue
        on_disk = {
            p.stem for p in sections_dir.glob("*.md")
        }
        declared_set = set(declared)
        missing = sorted(declared_set - on_disk)
        extra = sorted(on_disk - declared_set)
        if missing:
            drift.append(f"{split.name}: missing {missing}")
        if extra:
            drift.append(f"{split.name}: extra {extra}")

    if drift:
        return CheckResult(name, False, "; ".join(drift))
    return CheckResult(name, True, f"{total_declared} section(s) across {len(splits)} split(s)")


def check_fr_orphans_in_plan(project_root: Path) -> CheckResult:
    """Every ``FR-XX.YY`` mentioned in a plan or section file must exist
    in the parent split's ``spec.md``. Adapted from shipwright-check
    Group C2: plan phase is where FRs are assigned to sections, so
    catching orphans here prevents downstream drift.
    """
    name = "plan FR references exist in spec.md"
    splits = _find_planning_split_dirs(project_root)
    if not splits:
        return CheckResult(name, True, "no plan.md under planning/ — nothing to verify")

    all_frs = collect_requirements_from_planning(project_root)
    frs_by_split: dict[str, set[str]] = {}
    for fr in all_frs:
        frs_by_split.setdefault(fr.split, set()).add(fr.id)

    orphans_by_split: dict[str, list[str]] = {}
    for split in splits:
        declared = frs_by_split.get(split.name, set())

        mentioned: set[str] = set()
        plan_path = split / "plan.md"
        if plan_path.exists():
            try:
                mentioned.update(_FR_REF_RE.findall(plan_path.read_text(encoding="utf-8", errors="ignore")))
            except OSError:
                pass
        sections_dir = split / "sections"
        if sections_dir.is_dir():
            for sec in sections_dir.glob("*.md"):
                try:
                    mentioned.update(_FR_REF_RE.findall(sec.read_text(encoding="utf-8", errors="ignore")))
                except OSError:
                    continue

        orphans = sorted(mentioned - declared)
        if orphans:
            orphans_by_split[split.name] = orphans

    if orphans_by_split:
        first = next(iter(orphans_by_split.items()))
        summary = f"{len(orphans_by_split)} split(s) with orphan FRs; e.g. {first[0]}: {first[1][:5]}"
        return CheckResult(name, False, summary)

    return CheckResult(name, True, "all FR references resolve in their split spec.md")


def check_section_id_validity(project_root: Path) -> CheckResult:
    r"""Section names must match ``^\d{2}-[a-z0-9-]+$``, be unique, and
    form a gap-free zero-padded sequence starting at 01.

    Adapted from shipwright-check Group C4. Preventive because fixing
    section id drift after build has started is expensive — the
    downstream ``update_section_state.py`` key-by-name lookups all
    depend on the manifest order.
    """
    name = "section ids unique + sequential + well-formed"
    splits = _find_planning_split_dirs(project_root)
    if not splits:
        return CheckResult(name, True, "no plan.md under planning/ — nothing to verify")

    drift: list[str] = []
    for split in splits:
        declared = _parse_section_manifest(split / "plan.md")
        if not declared:
            continue  # covered by check_section_files_match_manifest
        bad_format = [n for n in declared if not _SECTION_NAME_RE.match(n)]
        if bad_format:
            drift.append(f"{split.name}: invalid names {bad_format}")
            continue

        dupes = [n for n in declared if declared.count(n) > 1]
        if dupes:
            drift.append(f"{split.name}: duplicate names {sorted(set(dupes))}")
            continue

        numbers = sorted(int(n.split("-", 1)[0]) for n in declared)
        expected = list(range(1, len(numbers) + 1))
        if numbers != expected:
            gaps = [i for i in expected if i not in numbers]
            drift.append(f"{split.name}: gaps in sequence {gaps}")

    if drift:
        return CheckResult(name, False, "; ".join(drift))
    return CheckResult(name, True, f"{len(splits)} split(s) checked, all section ids valid")


# ---------------------------------------------------------------------------
# Canon dispatcher
# ---------------------------------------------------------------------------

def run_plan_checks(
    project_root: Path,
    *,
    run_id: str = "",
) -> list[CheckResult]:
    """Run the full plan-phase verifier suite in stable order."""
    results: list[CheckResult] = []

    # Phase-own
    results.append(check_plan_config_status_complete(project_root))
    results.append(check_section_files_match_manifest(project_root))
    results.append(check_fr_orphans_in_plan(project_root))
    results.append(check_section_id_validity(project_root))

    # Canon (C5 skipped by policy)
    results.append(check_c1_phase_event_recorded(project_root, "plan"))
    results.append(check_c2_dashboard_reflects_phase(project_root, "plan"))
    results.append(check_c3_session_handoff_fresh_after_phase(project_root, "plan"))
    results.append(check_c4_decision_log_has_phase_adr(project_root, "plan"))

    # Phase history
    results.append(check_phase_history_has_run(project_root, "plan", run_id))

    # ADR integrity (phase-agnostic)
    results.append(check_adr_ids_sequential(project_root))
    results.append(check_adr_status_valid(project_root))
    results.append(check_adr_supersession_exists(project_root))

    return results


def run_all_checks(project_root: Path, run_id: str = "") -> list[CheckResult]:
    """Alias for uniformity with other phase modules."""
    return run_plan_checks(project_root, run_id=run_id)


__all__ = [
    "Severity",
    "check_fr_orphans_in_plan",
    "check_plan_config_status_complete",
    "check_section_files_match_manifest",
    "check_section_id_validity",
    "run_all_checks",
    "run_plan_checks",
]
