#!/usr/bin/env python3
"""Run the plan phase's own gates, in session.

`SKILL.md` listed these as things the agent should verify. An instruction is
not a gate — this is the command, so Step 6's "STOP" and Step 9's
"verification gates (all must pass)" have something to run.

    uv run check-plan-gates.py --planning-dir <path> [--gate review|sections|all]

``--gate review`` (Step 6)
    The external review step must have ended by a recorded route, and any
    disagreement between the two reviewers must have been decided. The
    judgement comes from ``review_marker.evaluate_review_state`` — the same
    function the resume gate and the ``W5`` compliance check use.

``--gate sections`` (Step 9)
    Section files exist for the manifest; the numbering agrees with the
    declared dependencies; every requirement lands in a section; every
    section traces back to a requirement; every section says what it is for,
    lists at least two steps, and states how it is tested.

Strict by design — unlike the phase verifier, which is lenient toward plans
written before these formats existed, this runs against the plan being
written *now*, which has no excuse.

Exit codes: ``0`` all gates passed · ``1`` a gate failed · ``2`` bad usage.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
# parents[0]=checks, [1]=scripts, [2]=shipwright-plan, [3]=plugins, [4]=repo root.
_SHARED_LIB = Path(__file__).resolve().parents[4] / "shared" / "scripts" / "lib"
if str(_SHARED_LIB) not in sys.path:
    sys.path.append(str(_SHARED_LIB))

from lib.sections import (  # noqa: E402
    get_missing_sections,
    parse_section_manifest,
    validate_dependency_order,
)
from drift_parsers import parse_fr_table  # noqa: E402
from plan_section_quality import (  # noqa: E402
    collect_sections,
    coverage_report,
    quality_problems,
)
from review_marker import (  # noqa: E402
    REVIEW_STATE_FILE,
    STATE_OK,
    evaluate_review_state,
)

GATES = ("review", "sections", "all")


def _gate(name: str, ok: bool, detail: str, problems: list[str] | None = None) -> dict:
    """A failing gate always names at least one problem — an empty list would
    read as "nothing wrong" to anyone rendering the result."""
    if not ok and not problems:
        problems = [detail]
    return {"gate": name, "ok": ok, "detail": detail, "problems": problems or []}


def review_gate(planning_dir: Path) -> dict:
    """Step 6 — dividing the plan into sections refuses to begin while no
    review route is on record, or while a reviewer disagreement is undecided."""
    path = planning_dir / REVIEW_STATE_FILE
    if not path.exists():
        return _gate(
            "review", False,
            f"{REVIEW_STATE_FILE} missing — Step 5 did not run to completion",
            [
                f"{REVIEW_STATE_FILE} missing — Step 5 did not run to completion",
                f"expected {path}",
            ],
        )
    try:
        marker = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return _gate("review", False, f"{REVIEW_STATE_FILE} unreadable: {exc}")

    # STATE_LEGACY blocks here. W5 only warns on it because it audits plans of
    # any age, but the marker this gate reads was written moments ago by this
    # same session: "completed, but no verdicts recorded" means Step 5b was
    # run without --verdict, which would bypass the disagreement check
    # entirely. Treating it as a pass would make the whole gate optional.
    state, reason = evaluate_review_state(marker)
    return _gate("review", state == STATE_OK, reason)


def _live_frs(planning_dir: Path) -> set[str]:
    spec = planning_dir / "spec.md"
    if not spec.exists():
        return set()
    try:
        content = spec.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return set()
    return {fr.id for fr in parse_fr_table(content, planning_dir.name, str(spec))}


def sections_gate(planning_dir: Path) -> dict:
    """Step 9 — everything that must be true of the section set."""
    parsed = parse_section_manifest(planning_dir / "plan.md")
    if not parsed.is_valid:
        return _gate("sections", False, "SECTION_MANIFEST unusable", parsed.errors)

    problems: list[str] = []

    missing = get_missing_sections(planning_dir, parsed.sections)
    problems += [f"declared but not written: {name}" for name in missing]
    problems += validate_dependency_order(parsed.entries)

    sections = collect_sections(planning_dir)
    report = coverage_report(sections, _live_frs(planning_dir))
    problems += [
        f"{fr}: named by no section — every requirement must land in one"
        for fr in report.uncovered_frs
    ]
    problems += [
        f"{name}: names no live requirement — add a 'Requirements: FR-..' line"
        for name in report.untraced_sections
    ]
    for name, refs in sorted(report.unknown_refs.items()):
        problems.append(f"{name}: declares unrecognised requirement id(s) {refs}")
    for section in sections:
        problems += quality_problems(section)

    return _gate(
        "sections", not problems,
        f"{len(sections)} section(s), {len(parsed.sections)} declared, "
        f"{len(problems)} problem(s)",
        problems,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the plan phase's own gates")
    parser.add_argument("--planning-dir", required=True)
    parser.add_argument("--gate", choices=GATES, default="all")
    args = parser.parse_args()

    planning_dir = Path(args.planning_dir).resolve()
    if not planning_dir.is_dir():
        print(json.dumps({
            "success": False, "error": "planning_dir_not_found",
            "message": f"not a directory: {planning_dir}",
        }, indent=2))
        return 2

    results = []
    if args.gate in ("review", "all"):
        results.append(review_gate(planning_dir))
    if args.gate in ("sections", "all"):
        results.append(sections_gate(planning_dir))

    failed = [r["gate"] for r in results if not r["ok"]]
    print(json.dumps({
        "success": not failed,
        "planning_dir": str(planning_dir),
        "gates": results,
        "failed": failed,
    }, indent=2))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
