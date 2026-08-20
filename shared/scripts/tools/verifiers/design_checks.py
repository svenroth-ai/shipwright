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
  table of ``.shipwright/designs/design-manifest.md`` must point at an
  existing ``.html`` file. ERROR.
- ``check_design_fr_coverage`` — every FR in every
  ``.shipwright/planning/<split>/spec.md`` must appear in the ``Linked FRs`` column
  of at least one screen row. ERROR. Adapted from the shipwright-check
  plan Group C1 preventive FR↔UI mapping check.

Plus the standard ``phase_history`` run-id check and ADR integrity
helpers from ``common.py``.
"""

from __future__ import annotations

import json
from pathlib import Path

from .common import (
    CheckResult,
    Severity,
    check_adr_ids_sequential,
    check_adr_status_valid,
    check_adr_supersession_exists,
    check_c1_phase_event_recorded,
    check_c2_dashboard_reflects_phase,
    check_c5_changelog_unreleased_has_phase_entry,
    check_phase_history_has_run,
)
from .design_screens_parser import (
    parse_non_ui_frs,
    parse_screens_table,
    summarize_fr_coverage,
)
from .handoff_phase_canon import check_c3_session_handoff_fresh_after_phase

# Add shared/scripts to path for lib imports
import sys
_SHARED_SCRIPTS = Path(__file__).resolve().parent.parent.parent
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

from lib.drift_parsers import collect_requirements_from_planning  # noqa: E402

# Canonical design artifact directory under .shipwright/. Module-local
# constant per Sub-Iterate B of the designs relocation; the legacy
# top-level path is referenced only by the drift detector / migration
# framework, not by this verifier.
DESIGNS_DIR = ".shipwright/designs"

# Scopes that have no UI surface and therefore cannot have a screen-based
# design manifest. Both phase-own design checks short-circuit to SKIP for
# these — the FR→screen contract is structurally inapplicable, not failing.
# A separate, orthogonal skip (``_design_phase_ran``, applied only by
# ``check_design_fr_coverage``) covers projects whose design phase never ran
# at all — e.g. adopted / brownfield repos (triage trg-d26da6f4).
_NO_UI_SCOPES = frozenset({"library"})


def _is_no_ui_scope(project_root: Path) -> bool:
    """Read ``shipwright_run_config.json`` and return True iff ``scope`` is
    a known no-UI value (currently ``library``).

    Fail-closed: missing file, unreadable file, malformed JSON, or an
    undecodable payload returns False (check runs normally — never silently
    skip on broken state). ``utf-8-sig`` tolerates a hand-edited UTF-8 BOM
    (WP8/F24 config-reader convention) so a BOM'd ``scope=library`` config is
    still detected as library rather than false-failing the check.
    """
    cfg = project_root / "shipwright_run_config.json"
    try:
        data = json.loads(cfg.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return False
    return isinstance(data, dict) and data.get("scope") in _NO_UI_SCOPES


def _design_phase_ran(project_root: Path) -> bool:
    """Return True iff ``"design"`` is in ``completed_steps`` of
    ``shipwright_run_config.json`` — i.e. the design phase is part of this
    project's lifecycle. Adopted (brownfield) projects never run
    ``/shipwright-design`` (``shipwright-adopt`` seeds ``completed_steps`` as
    ``[project, plan, build, test]``), so their design-manifest legitimately
    never existed (triage trg-d26da6f4).

    Fail-loud: a missing / unreadable / malformed / undecodable config, a
    non-dict payload, or a non-list ``completed_steps`` all return True — a
    broken config never buys a silent free pass, and a manifest lost AFTER a
    design phase ran is real drift. ``utf-8-sig`` tolerates a hand-edited BOM
    (WP8/F24 config-reader convention). Callers MUST gate only the
    *manifest-missing* branch on this helper, never as a top-level
    short-circuit: the between-phase validator runs these checks before
    ``"design"`` is appended to ``completed_steps``, but only once the
    manifest is present, so a manifest-gated skip preserves its FR-orphan /
    screen-existence enforcement.
    """
    cfg = project_root / "shipwright_run_config.json"
    try:
        data = json.loads(cfg.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return True
    if not isinstance(data, dict):
        return True
    steps = data.get("completed_steps")
    if not isinstance(steps, list):
        return True
    return "design" in steps


# ---------------------------------------------------------------------------
# Phase-own checks
# ---------------------------------------------------------------------------

def check_design_manifest_screens_exist(project_root: Path) -> CheckResult:
    """Every row in the ``## Screens`` table of ``.shipwright/designs/design-manifest.md``
    must point at an existing HTML file on disk. ERROR — downstream test
    fidelity checks will explode if mockups vanished or were renamed.

    Skips only for a no-UI scope (``scope=library``). Unlike
    ``check_design_fr_coverage`` this check keeps failing loud on an absent
    manifest: it is not part of the detective audit (only the between-phase
    validator runs it, and only once mockups exist), so it never fires on an
    adopted project — and by staying strict it remains the manifest-presence
    sentinel that catches a design phase which wrote mockups but no manifest."""
    name = "design_manifest screens exist on disk"
    if _is_no_ui_scope(project_root):
        return CheckResult(
            name, None,
            "scope=library — no UI surface, design manifest not applicable",
            severity=Severity.SKIPPED.value,
        )
    manifest = project_root / DESIGNS_DIR / "design-manifest.md"
    if not manifest.exists():
        return CheckResult(name, False, f"{DESIGNS_DIR}/design-manifest.md missing")
    try:
        body = manifest.read_text(encoding="utf-8", errors="ignore")
    except OSError as exc:
        return CheckResult(name, False, f"read error: {exc}")

    rows = parse_screens_table(body)
    if not rows:
        return CheckResult(
            name,
            False,
            "no Screens rows parsed (check manifest format)",
        )

    missing: list[str] = []
    for screen_file, _ in rows:
        # Manifest paths are relative to the canonical designs directory.
        full = project_root / DESIGNS_DIR / screen_file
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
    """Every FR declared in ``.shipwright/planning/<split>/spec.md`` must appear in
    the ``Linked FRs`` column of at least one screen row.

    Adapted from the shipwright-check plan Group C1 preventive check:
    design phase is where FR↔UI mapping is decided, so it's the right
    place to fail fast on orphan FRs (test-fidelity drift downstream).
    Skips if there are no planning FRs (early bootstrap, no work to do), if
    the project's scope has no UI surface (``scope=library``), or — when the
    manifest is absent — if the design phase was never part of the project's
    lifecycle (adopted / brownfield; no ``"design"`` in ``completed_steps``),
    so the manifest legitimately never existed (triage trg-d26da6f4). An
    absent manifest AFTER a design phase ran is real drift and still fails.

    A declared FR listed under the manifest's ``## Non-UI FRs`` section is
    exempt — the project-level ``scope=library`` skip (ADR-079) only covers
    a project with NO UI surface at all; a mostly-UI project with a handful
    of legitimately backend-only FRs needs a per-FR marker instead.
    """
    name = "design FR coverage (every FR linked to >=1 screen)"

    if _is_no_ui_scope(project_root):
        return CheckResult(
            name, None,
            "scope=library — no UI surface, FR→screen mapping not applicable",
            severity=Severity.SKIPPED.value,
        )

    frs = collect_requirements_from_planning(project_root)
    if not frs:
        return CheckResult(name, True, "no planning FRs — coverage trivially satisfied")

    manifest = project_root / DESIGNS_DIR / "design-manifest.md"
    if not manifest.exists():
        if not _design_phase_ran(project_root):
            return CheckResult(
                name, None,
                "design phase never ran (no 'design' in completed_steps) — "
                "FR→screen mapping not applicable",
                severity=Severity.SKIPPED.value,
            )
        return CheckResult(name, False, f"{DESIGNS_DIR}/design-manifest.md missing")
    try:
        body = manifest.read_text(encoding="utf-8", errors="ignore")
    except OSError as exc:
        return CheckResult(name, False, f"read error: {exc}")

    rows = parse_screens_table(body)
    non_ui = parse_non_ui_frs(body)
    declared = {f.id for f in frs}
    ok, detail = summarize_fr_coverage(declared, rows, non_ui)
    return CheckResult(name, ok, detail)


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
