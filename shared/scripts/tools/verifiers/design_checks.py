"""Design-phase verifier checks.

Iterate 12.2 brings the ``design`` plugin to Minimum Phase Completion
Canon coverage for the first time. Before 12.2 the plugin had ZERO
finalization calls — no ``record_event``, no dashboard update, no
handoff. Step 9 of [design/SKILL.md] (new in 12.2) calls the 12.0
helpers; this module verifies they ran.

Canon coverage:

- C1 (phase_completed event) — ERROR
- C2 (build_dashboard mentions design) — WARNING
- C3 (session_handoff fresh) — WARNING
- C4 — **SKIPPED BY POLICY**, design is not a decision-taking phase
- C5 (CHANGELOG [Unreleased] Added entry) — ERROR

Phase-own checks:

- ``check_design_manifest_screens_exist`` — every row in the Screens
  table of ``designs/design-manifest.md`` must point at an existing
  ``.html`` file. ERROR.
- ``check_design_fr_coverage`` — every FR in every
  ``planning/<split>/spec.md`` must appear in the ``Linked FRs`` column
  of at least one screen row. ERROR. Adapted from the shipwright-check
  plan Group C1 preventive FR↔UI mapping check.

Plus the standard ``phase_history`` run-id check and ADR integrity
helpers from ``common.py``.
"""

from __future__ import annotations

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
    check_c5_changelog_unreleased_has_phase_entry,
    check_phase_history_has_run,
)

# Add shared/scripts to path for lib imports
import sys
_SHARED_SCRIPTS = Path(__file__).resolve().parent.parent.parent
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

from lib.drift_parsers import collect_requirements_from_planning  # noqa: E402


# ---------------------------------------------------------------------------
# design-manifest.md parser
# ---------------------------------------------------------------------------

# Pipe-delimited Screens table row: "| 01 | Login | screens/01-login.html | complete | FR-01.01, FR-01.02 |"
# Group 1: filename, group 2: FR list (may be empty, "none", or a comma list).
_SCREEN_ROW_RE = re.compile(
    r"^\|\s*\S+\s*\|\s*[^|]+?\s*\|\s*(?P<file>[^|]+?)\s*\|\s*\S+\s*\|\s*(?P<frs>[^|]*?)\s*\|$"
)

# Table header line — used to ignore the "|---|---|" separator row.
_TABLE_SEPARATOR_RE = re.compile(r"^\|[\s:|-]+\|$")


def _parse_screens_table(manifest_body: str) -> list[tuple[str, list[str]]]:
    """Return ``[(screen_file, [linked_frs])]`` for every row inside the
    ``## Screens`` section of a design manifest.

    Stops at the next ``## `` header so trailing ``## User Flows`` and
    ``## Uploads`` tables aren't accidentally merged into the result.
    """
    # Extract the section body between "## Screens" and the next "## " header.
    m = re.search(
        r"##\s+Screens\s*\n(.*?)(?=\n##\s+|\Z)",
        manifest_body,
        re.DOTALL,
    )
    if not m:
        return []
    body = m.group(1)

    out: list[tuple[str, list[str]]] = []
    for line in body.splitlines():
        if _TABLE_SEPARATOR_RE.match(line.strip()):
            continue
        if line.strip().startswith("| #") or line.strip().startswith("|#"):
            continue
        hit = _SCREEN_ROW_RE.match(line.strip())
        if not hit:
            continue
        screen_file = hit.group("file").strip()
        fr_cell = hit.group("frs").strip()
        if not fr_cell or fr_cell.lower() in {"none", "-", "—", "tbd"}:
            frs: list[str] = []
        else:
            frs = [
                f.strip()
                for f in re.split(r"[,\s]+", fr_cell)
                if re.match(r"^FR-[\d.]+$", f.strip())
            ]
        out.append((screen_file, frs))
    return out


# ---------------------------------------------------------------------------
# Phase-own checks
# ---------------------------------------------------------------------------

def check_design_manifest_screens_exist(project_root: Path) -> CheckResult:
    """Every row in the ``## Screens`` table of ``designs/design-manifest.md``
    must point at an existing HTML file on disk. ERROR — downstream test
    fidelity checks will explode if mockups vanished or were renamed."""
    name = "design_manifest screens exist on disk"
    manifest = project_root / "designs" / "design-manifest.md"
    if not manifest.exists():
        return CheckResult(name, False, "designs/design-manifest.md missing")
    try:
        body = manifest.read_text(encoding="utf-8", errors="ignore")
    except OSError as exc:
        return CheckResult(name, False, f"read error: {exc}")

    rows = _parse_screens_table(body)
    if not rows:
        return CheckResult(
            name,
            False,
            "no Screens rows parsed (check manifest format)",
        )

    missing: list[str] = []
    for screen_file, _ in rows:
        # Manifest paths are relative to `designs/`.
        full = project_root / "designs" / screen_file
        if not full.exists():
            missing.append(screen_file)

    if missing:
        return CheckResult(
            name,
            False,
            f"{len(missing)} missing screen file(s): {missing[:3]}"
            + (" …" if len(missing) > 3 else ""),
        )
    return CheckResult(name, True, f"{len(rows)} screen(s), all files present")


def check_design_fr_coverage(project_root: Path) -> CheckResult:
    """Every FR declared in ``planning/<split>/spec.md`` must appear in
    the ``Linked FRs`` column of at least one screen row.

    Adapted from the shipwright-check plan Group C1 preventive check:
    design phase is where FR↔UI mapping is decided, so it's the right
    place to fail fast on orphan FRs (test-fidelity drift downstream).
    Skips if there are no planning FRs (early bootstrap, no work to do).
    """
    name = "design FR coverage (every FR linked to >=1 screen)"

    frs = collect_requirements_from_planning(project_root)
    if not frs:
        return CheckResult(name, True, "no planning FRs — coverage trivially satisfied")

    manifest = project_root / "designs" / "design-manifest.md"
    if not manifest.exists():
        return CheckResult(name, False, "designs/design-manifest.md missing")
    try:
        body = manifest.read_text(encoding="utf-8", errors="ignore")
    except OSError as exc:
        return CheckResult(name, False, f"read error: {exc}")

    rows = _parse_screens_table(body)
    linked: set[str] = set()
    for _, row_frs in rows:
        linked.update(row_frs)

    declared = {f.id for f in frs}
    orphans = sorted(declared - linked)

    if orphans:
        return CheckResult(
            name,
            False,
            f"{len(orphans)} FR(s) with no screen mapping: {orphans[:5]}"
            + (" …" if len(orphans) > 5 else ""),
        )
    return CheckResult(
        name,
        True,
        f"{len(declared)} FR(s) linked across {len(rows)} screen(s)",
    )


# ---------------------------------------------------------------------------
# Canon dispatcher
# ---------------------------------------------------------------------------

def run_design_checks(
    project_root: Path,
    *,
    run_id: str = "",
) -> list[CheckResult]:
    """Run the full design-phase verifier suite in stable order."""
    results: list[CheckResult] = []

    # Phase-own
    results.append(check_design_manifest_screens_exist(project_root))
    results.append(check_design_fr_coverage(project_root))

    # Canon (C4 skipped by policy)
    results.append(check_c1_phase_event_recorded(project_root, "design"))
    results.append(check_c2_dashboard_reflects_phase(project_root, "design"))
    results.append(check_c3_session_handoff_fresh_after_phase(project_root, "design"))
    results.append(check_c5_changelog_unreleased_has_phase_entry(project_root, "design", "Added"))

    # Phase history
    results.append(check_phase_history_has_run(project_root, "design", run_id))

    # ADR integrity (phase-agnostic)
    results.append(check_adr_ids_sequential(project_root))
    results.append(check_adr_status_valid(project_root))
    results.append(check_adr_supersession_exists(project_root))

    return results


def run_all_checks(project_root: Path, run_id: str = "") -> list[CheckResult]:
    """Alias for uniformity with other phase modules."""
    return run_design_checks(project_root, run_id=run_id)


# Keep ``Severity`` re-exported so downstream wiring (phase_validators)
# can tell ERROR/WARNING apart when deciding ask-vs-inform.
__all__ = [
    "Severity",
    "check_design_fr_coverage",
    "check_design_manifest_screens_exist",
    "run_all_checks",
    "run_design_checks",
]
