#!/usr/bin/env python3
"""Per-journey browser-test coverage — is every planned user journey tested?

Browser-test generation is skipped once ``e2e/`` contains any ``.spec.ts`` file
at all. That is correct for *generation* — you do not regenerate a suite that
exists — but it meant the first journey got a test and every journey added to
the plan afterwards got nothing, with nothing reporting the gap.

This asks the question per journey instead, and routes the answer by how the
project was onboarded (FR-01.06,
iterate-2026-07-27-test-phase-record-honesty):

* **greenfield** — a planned journey with no test is a gap in work this
  pipeline is responsible for. It blocks.
* **brownfield** — the gap predates onboarding. It files a follow-up carrying a
  ``/shipwright-adopt`` launch payload and does not block.

Matching a journey to a spec is a **name heuristic**, and the report says so:
``covered`` / ``uncovered`` / ``undetermined`` / ``no_specs``. Nothing here
claims the spec actually exercises the journey — there is no oracle for that.

Usage:
    uv run journey_coverage.py --project-root . [--json] [--no-triage]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_SHARED_SCRIPTS = Path(__file__).resolve().parents[4] / "shared" / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

from journey_plan import (  # noqa: E402 — re-exported: one public entry point
    Journey,
    parse_journeys,
    plan_files,
    slugify,
    spec_files,
)

_TITLE_CAP = 160
_DETAIL_CAP = 2000


def _report(status: str, mode: str, diagnostic: str, **extra) -> dict:
    base = {
        "status": status, "mode": mode, "blocking": False,
        "covered": [], "uncovered": [], "triage_appended": 0,
        "diagnostic": diagnostic,
    }
    base.update(extra)
    return base


def _is_covered(journey: Journey, specs: list[tuple[str, str]]) -> bool:
    """A journey is *apparently* covered when a spec names it.

    Two signals, both name-based: the spec's filename slug contains the
    journey's slug, or the spec body mentions the journey title.
    """
    title_lower = journey.title.lower()
    for name_slug, body_lower in specs:
        if journey.slug and journey.slug in name_slug:
            return True
        if title_lower and title_lower in body_lower:
            return True
    return False


def _emit_gap_followups(
    project_root: Path,
    uncovered: list[Journey],
    *,
    run_id: str | None,
    commit: str | None,
) -> int:
    """One durable follow-up per uncovered journey, routed to onboarding.

    ``match_commit=False`` + ``window_seconds=None``: an untested journey is
    the same issue until somebody writes the test, so it stays exactly one open
    item rather than re-firing on every commit.
    """
    try:
        from triage import append_triage_item_idempotent  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(
            f"[journey-coverage] triage import failed: {type(exc).__name__}: {exc}\n")
        return 0

    appended = 0
    for journey in uncovered:
        try:
            new_id = append_triage_item_idempotent(
                project_root,
                source="journey-coverage",
                severity="medium",
                kind="improvement",
                title=f"[test] no browser test for journey: {journey.title}"[:_TITLE_CAP],
                detail=(
                    f"The E2E plan describes journey {journey.index} "
                    f"({journey.title!r}) but no spec under e2e/ names it. This "
                    f"project was onboarded from an existing codebase, so the gap "
                    f"predates the pipeline and does not block the run — it is "
                    f"backlog. Matching is by name (filename slug, or a title "
                    f"mention in the spec body); if a spec does cover this "
                    f"journey under another name, renaming it closes this item."
                )[:_DETAIL_CAP],
                dedup_key=f"journey-coverage:{journey.identity}",
                evidence_path=".shipwright/planning/**/claude-plan-e2e.md",
                run_id=run_id,
                commit=commit,
                match_commit=False,
                window_seconds=None,
                launch_payload=(
                    "/shipwright-adopt\n\n"
                    f"Context: planned journey {journey.index} ({journey.title}) "
                    f"has no browser test. Write a spec for it, or record why the "
                    f"journey is not testable here."
                ),
                fr_id="FR-01.06",
            )
            if new_id is not None:
                appended += 1
        except Exception as exc:  # noqa: BLE001
            sys.stderr.write(
                f"[journey-coverage] triage emit failed ({journey.identity}): "
                f"{type(exc).__name__}: {exc}\n"
            )
    return appended


def check_journey_coverage(
    project_root: Path | str,
    *,
    emit_triage: bool = True,
    run_id: str | None = None,
    commit: str | None = None,
) -> dict:
    """Report per-journey coverage. Never raises into the phase."""
    from project_facts import is_adopted_project  # noqa: PLC0415

    root = Path(project_root)
    adopted = is_adopted_project(root)
    mode = "brownfield" if adopted else "greenfield"

    plans = plan_files(root)
    if not plans:
        return _report("undetermined", mode, (
            "no claude-plan-e2e.md under .shipwright/planning/ — there are no "
            "planned journeys to check coverage against"
        ))

    journeys: list[Journey] = []
    for plan in plans:
        try:
            text = plan.read_text(encoding="utf-8")
        except OSError as exc:
            return _report("undetermined", mode, f"could not read {plan}: {exc}")
        journeys.extend(parse_journeys(text))

    # Re-index across plans so identities stay unique and positional.
    journeys = [
        Journey(index=i, title=j.title, slug=j.slug)
        for i, j in enumerate(journeys, start=1)
    ]

    if not journeys:
        return _report("undetermined", mode, (
            "no user journeys parsed from the E2E plan(s) — expected "
            "'### Flow N: Title' headings under '## User Flows'"
        ))

    spec_paths = spec_files(root)
    if not spec_paths:
        # Nothing generated yet — that is step-2.5's own job, not a gap.
        return _report("no_specs", mode, (
            f"{len(journeys)} planned journey(s) and no spec files yet — "
            f"generate them from the plan"
        ))

    specs: list[tuple[str, str]] = []
    for path in spec_paths:
        try:
            body = path.read_text(encoding="utf-8").lower()
        except OSError:
            body = ""
        specs.append((slugify(path.name.replace(".spec.ts", "")), body))

    covered = [j for j in journeys if _is_covered(j, specs)]
    uncovered = [j for j in journeys if j not in covered]

    appended = 0
    if uncovered and adopted and emit_triage:
        appended = _emit_gap_followups(root, uncovered, run_id=run_id, commit=commit)

    return _report(
        "gaps" if uncovered else "covered", mode,
        (
            f"{len(covered)}/{len(journeys)} planned journeys apparently covered "
            f"(name heuristic — an indication, not proof the journey is exercised)"
        ),
        blocking=bool(uncovered) and not adopted,
        covered=[{"identity": j.identity, "title": j.title} for j in covered],
        uncovered=[{"identity": j.identity, "title": j.title} for j in uncovered],
        triage_appended=appended,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Per-journey E2E coverage check")
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--commit", default=None)
    parser.add_argument("--no-triage", action="store_true",
                        help="report only; do not file follow-ups")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args()

    report = check_journey_coverage(
        Path(args.project_root).resolve(),
        emit_triage=not args.no_triage,
        run_id=args.run_id,
        commit=args.commit,
    )

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"Journey coverage: {report['status']} ({report['mode']})")
        print(f"  {report['diagnostic']}")
        for j in report["uncovered"]:
            print(f"  UNCOVERED  {j['identity']}  {j['title']}")
        if report["triage_appended"]:
            print(f"  {report['triage_appended']} follow-up(s) filed")

    return 1 if report["blocking"] else 0


__all__ = ["Journey", "check_journey_coverage", "parse_journeys"]


if __name__ == "__main__":
    sys.exit(main())
