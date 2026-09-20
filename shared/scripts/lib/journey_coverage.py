"""Per-journey browser-test coverage shared by test producers and verifiers."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .journey_plan import (
    Journey, malformed_flow_headings, parse_journeys, plan_files, slugify, spec_files,
)

_TITLE_CAP = 160
_DETAIL_CAP = 2000
_SHARED_SCRIPTS = Path(__file__).resolve().parents[1]

if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))


def _report(status: str, mode: str, diagnostic: str, **extra) -> dict:
    report = {
        "status": status, "mode": mode, "blocking": False,
        "covered": [], "uncovered": [], "triage_appended": 0,
        "diagnostic": diagnostic,
    }
    report.update(extra)
    return report


def _is_covered(journey: Journey, specs: list[tuple[str, str]]) -> bool:
    title_lower = journey.title.lower()
    return any(
        (journey.slug and journey.slug in name_slug)
        or (title_lower and title_lower in body_lower)
        for name_slug, body_lower in specs
    )


def _emit_gap_followups(
    project_root: Path, uncovered: list[Journey], *, run_id: str | None, commit: str | None,
) -> int:
    """File one durable onboarding follow-up per inherited uncovered journey."""
    try:
        from triage import append_triage_item_idempotent  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(f"[journey-coverage] triage import failed: {type(exc).__name__}: {exc}\n")
        return 0

    appended = 0
    for journey in uncovered:
        try:
            new_id = append_triage_item_idempotent(
                project_root, source="journey-coverage", severity="medium", kind="improvement",
                title=f"[test] no browser test for journey: {journey.title}"[:_TITLE_CAP],
                detail=(
                    f"The E2E plan describes journey {journey.index} ({journey.title!r}) but no "
                    "spec under e2e/ names it. This project was onboarded from an existing "
                    "codebase, so the gap predates the pipeline and does not block the run — it "
                    "is backlog. Matching is by name (filename slug, or a title mention in the "
                    "spec body); if a spec does cover this journey under another name, renaming "
                    "it closes this item."
                )[:_DETAIL_CAP],
                dedup_key=f"journey-coverage:{journey.identity}",
                evidence_path=".shipwright/planning/**/claude-plan-e2e.md",
                run_id=run_id, commit=commit, match_commit=False, window_seconds=None,
                launch_payload=(
                    "/shipwright-adopt\n\n"
                    f"Context: planned journey {journey.index} ({journey.title}) has no browser "
                    "test. Write a spec for it, or record why the journey is not testable here."
                ),
                fr_id="FR-01.06",
            )
            appended += new_id is not None
        except Exception as exc:  # noqa: BLE001
            sys.stderr.write(
                f"[journey-coverage] triage emit failed ({journey.identity}): "
                f"{type(exc).__name__}: {exc}\n"
            )
    return appended


def check_journey_coverage(
    project_root: Path | str, *, emit_triage: bool = True,
    run_id: str | None = None, commit: str | None = None,
    require_user_flows_section: bool = False,
) -> dict:
    """Report coverage per planned journey; never raise into the phase."""
    from project_facts import is_adopted_project  # noqa: PLC0415

    root = Path(project_root)
    adopted = is_adopted_project(root)
    mode = "brownfield" if adopted else "greenfield"
    plans = plan_files(root)
    if not plans:
        return _report("undetermined", mode, "no claude-plan-e2e.md under .shipwright/planning")

    journeys: list[Journey] = []
    unreadable_plans = 0
    malformed_flows = 0
    for plan in plans:
        try:
            plan_text = plan.read_text(encoding="utf-8-sig")
            malformed_flows += malformed_flow_headings(
                plan_text, require_user_flows_section=require_user_flows_section,
            )
            journeys.extend(parse_journeys(
                plan_text,
                require_user_flows_section=require_user_flows_section,
            ))
        except (OSError, UnicodeDecodeError):
            unreadable_plans += 1
            continue
    journeys = [Journey(i, journey.title, journey.slug) for i, journey in enumerate(journeys, 1)]
    if not journeys:
        diagnostic = "no user journeys parsed from the readable E2E plan(s)"
        if unreadable_plans:
            diagnostic += f"; {unreadable_plans} E2E plan(s) could not be read"
        return _report(
            "invalid" if malformed_flows else "undetermined", mode,
            (f"{malformed_flows} User Flows heading(s) omit a journey title" if malformed_flows else diagnostic),
            unreadable_plans=unreadable_plans, malformed_flow_headings=malformed_flows,
        )

    unreadable_note = (
        f"; {unreadable_plans} E2E plan(s) could not be read" if unreadable_plans else ""
    )

    paths = spec_files(root)
    if not paths:
        appended = (
            _emit_gap_followups(root, journeys, run_id=run_id, commit=commit)
            if adopted and emit_triage
            else 0
        )
        return _report(
            "no_specs", mode,
            f"{len(journeys)} planned journey(s) and no spec files yet{unreadable_note}",
            covered=[],
            uncovered=[
                {"identity": journey.identity, "title": journey.title}
                for journey in journeys
            ],
            triage_appended=appended,
            unreadable_plans=unreadable_plans,
            malformed_flow_headings=malformed_flows,
        )

    specs: list[tuple[str, str]] = []
    unreadable_specs = 0
    for path in paths:
        try:
            specs.append((slugify(path.name.removesuffix(".spec.ts")), path.read_text(encoding="utf-8-sig").lower()))
        except (OSError, UnicodeDecodeError):
            unreadable_specs += 1
    covered = [journey for journey in journeys if _is_covered(journey, specs)]
    uncovered = [journey for journey in journeys if journey not in covered]
    appended = _emit_gap_followups(root, uncovered, run_id=run_id, commit=commit) if uncovered and adopted and emit_triage else 0
    return _report(
        "gaps" if uncovered else "covered", mode,
        f"{len(covered)}/{len(journeys)} planned journeys apparently covered "
        f"(name heuristic — an indication, not proof the journey is exercised){unreadable_note}"
        + (f"; {unreadable_specs} E2E spec(s) could not be read" if unreadable_specs else ""),
        blocking=bool(uncovered) and not adopted,
        covered=[{"identity": journey.identity, "title": journey.title} for journey in covered],
        uncovered=[{"identity": journey.identity, "title": journey.title} for journey in uncovered],
        triage_appended=appended,
        unreadable_plans=unreadable_plans,
        unreadable_specs=unreadable_specs,
        malformed_flow_headings=malformed_flows,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Per-journey E2E coverage check")
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--commit", default=None)
    parser.add_argument("--no-triage", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    report = check_journey_coverage(
        Path(args.project_root).resolve(), emit_triage=not args.no_triage,
        run_id=args.run_id, commit=args.commit,
    )
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"Journey coverage: {report['status']} ({report['mode']})")
        print(f"  {report['diagnostic']}")
        for journey in report["uncovered"]:
            print(f"  UNCOVERED  {journey['identity']}  {journey['title']}")
        if report["triage_appended"]:
            print(f"  {report['triage_appended']} follow-up(s) filed")
    return 1 if report["blocking"] else 0


__all__ = [
    "Journey", "check_journey_coverage", "parse_journeys", "plan_files", "slugify", "spec_files",
]
