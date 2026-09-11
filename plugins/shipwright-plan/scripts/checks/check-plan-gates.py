#!/usr/bin/env python3
"""Run the plan phase's own gates, in session.

`SKILL.md` listed these as things the agent should verify. An instruction is
not a gate — this is the command, so Step 6's "STOP" and Step 9's
"verification gates (all must pass)" have something to run.

    uv run check-plan-gates.py --planning-dir <path> --project-root <path> \
        --plugin-root <path> [--gate review|sections|boundary|all]

``--gate review`` (Step 6)
    The external review step must have ended by a recorded route, and any
    disagreement between the two reviewers must have been decided. The
    judgement comes from ``review_marker.evaluate_review_state`` — the same
    function the resume gate and the ``W5`` compliance check use. Also runs
    the **key-honesty** check (FR-01.03 #1): if external-review keys are
    actually available right now, the marker may not record a silent skip.

``--gate sections`` (Step 9, requires ``--plugin-root`` — usage error without it)
    Manifest/dependency/coverage/trace/quality checks (#9); a planning
    decision was logged (#8); every review finding — external or internal,
    whichever carried the gate — addressed or rejected-with-reason (#10);
    a UI project's E2E plan names >=1 flow, via config.json (#11).

``--gate boundary`` (#7 — planning writes no production code)
    Every changed path must fall under an allowed planning-phase prefix (see
    ``PLAN_ALLOWED_PREFIXES``). Non-git ``--project-root`` skips it (nothing
    to check against).

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

from lib.config import is_e2e_enabled, load_global_config  # noqa: E402
from lib.sections import (  # noqa: E402
    get_missing_sections,
    parse_section_manifest,
    validate_dependency_order,
)
from drift_parsers import parse_fr_table  # noqa: E402
from external_review_config import (  # noqa: E402
    get_external_review_status,
    load_review_config,
)
from phase_write_boundary import find_boundary_violations, git_dirty_paths  # noqa: E402
from plan_gate_extras import (  # noqa: E402
    decisions_recorded,
    e2e_journeys_named,
    findings_addressed,
    review_key_honesty,
)
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

GATES = ("review", "sections", "boundary", "all")

#: FR-01.03 #7 — a planning session may write into these prefixes and
#: nowhere else, per `step-9-completion.md` / `docs/hooks-and-pipeline.md`.
#: Includes `shipwright_plan_config.json`: SKILL.md's First Action E writes
#: it at project root every session, not only at completion.
PLAN_ALLOWED_PREFIXES = (
    ".shipwright/",
    "shipwright_run_config.json",
    "shipwright_project_config.json",
    "shipwright_plan_config.json",
    "CHANGELOG-unreleased.d/",
)


def _gate(name: str, ok: bool, detail: str, problems: list[str] | None = None) -> dict:
    """A failing gate always names >=1 problem — else it reads as clean."""
    if not ok and not problems:
        problems = [detail]
    return {"gate": name, "ok": ok, "detail": detail, "problems": problems or []}


def review_gate(planning_dir: Path, project_root: Path) -> dict:
    """Step 6 — dividing the plan into sections refuses to begin while no
    review route is on record, or while a reviewer disagreement is undecided.

    Also runs FR-01.03 #1's key-honesty check: a route recorded as skipped
    while a key is actually available right now is a false skip.
    """
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
    problems = [] if state == STATE_OK else [reason]

    computed_status = get_external_review_status(load_review_config(project_root=project_root))
    honesty = review_key_honesty(marker, computed_status)
    if not honesty.ok:
        problems.append(honesty.detail)

    ok = state == STATE_OK and honesty.ok
    detail = reason if state != STATE_OK else (honesty.detail if not honesty.ok else reason)
    return _gate("review", ok, detail, problems if not ok else [])


def _live_frs(planning_dir: Path) -> set[str]:
    spec = planning_dir / "spec.md"
    if not spec.exists():
        return set()
    try:
        content = spec.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return set()
    return {fr.id for fr in parse_fr_table(content, planning_dir.name, str(spec))}


def _decision_log_text(project_root: Path) -> str:
    path = project_root / ".shipwright" / "agent_docs" / "decision_log.md"
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def _marker_findings_count(planning_dir: Path) -> int:
    path = planning_dir / REVIEW_STATE_FILE
    if not path.exists():
        return 0
    try:
        marker = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return 0
    try:
        return int(marker.get("findings_count") or 0)
    except (TypeError, ValueError):
        return 0


def sections_gate(planning_dir: Path, project_root: Path, plugin_root: Path) -> dict:
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

    # FR-01.03 #8 / #10 — the decision-log trail for this split.
    split_name = planning_dir.name
    decision_log_text = _decision_log_text(project_root)
    decisions = decisions_recorded(decision_log_text, split_name)
    if not decisions.ok:
        problems.append(decisions.detail)
    findings = findings_addressed(decision_log_text, split_name, _marker_findings_count(planning_dir))
    if not findings.ok:
        problems.append(findings.detail)

    # FR-01.03 #11 — a UI project's E2E plan names its journeys.
    expect_e2e = is_e2e_enabled(load_global_config(plugin_root))
    e2e = e2e_journeys_named(planning_dir / "claude-plan-e2e.md", expect_e2e)
    if not e2e.ok:
        problems.append(e2e.detail)

    return _gate(
        "sections", not problems,
        f"{len(sections)} section(s), {len(parsed.sections)} declared, "
        f"{len(problems)} problem(s)",
        problems,
    )


def boundary_gate(project_root: Path) -> dict:
    """FR-01.03 #7 — planning writes no production code, runs no tests.
    Reads the session's own uncommitted change set; a non-git project
    yields no evidence and passes trivially, not a violation."""
    changed = git_dirty_paths(project_root)
    violations = find_boundary_violations(changed, list(PLAN_ALLOWED_PREFIXES))
    if violations:
        return _gate(
            "boundary", False,
            f"{len(violations)} change(s) outside the planning phase's allowed paths",
            [f"outside allowed paths: {p}" for p in violations],
        )
    return _gate("boundary", True, f"{len(changed)} changed path(s), all within bounds")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the plan phase's own gates")
    parser.add_argument("--planning-dir", required=True)
    parser.add_argument(
        "--project-root", required=True,
        help="Project root for decision_log.md, git evidence, and review-config "
             "overrides — a cwd default let --gate boundary false-pass on "
             "empty git evidence (external review, iterate-2026-09-11-e1).",
    )
    parser.add_argument(
        "--plugin-root", default=None,
        help="Plugin root, for gate #11's config.json. Required for --gate "
             "sections/all (usage error if omitted).",
    )
    parser.add_argument("--gate", choices=GATES, default="all")
    args = parser.parse_args()

    planning_dir = Path(args.planning_dir).resolve()
    if not planning_dir.is_dir():
        print(json.dumps({
            "success": False, "error": "planning_dir_not_found",
            "message": f"not a directory: {planning_dir}",
        }, indent=2))
        return 2

    project_root = Path(args.project_root).resolve()
    plugin_root = Path(args.plugin_root).resolve() if args.plugin_root else None
    if plugin_root is None and args.gate in ("sections", "all"):
        print(json.dumps({
            "success": False, "error": "plugin_root_required",
            "message": "--plugin-root is required for --gate sections/all: "
                       "gate #11 must not silently skip (external review).",
        }, indent=2))
        return 2
    if plugin_root is not None and not plugin_root.is_dir():
        print(json.dumps({
            "success": False, "error": "plugin_root_not_found",
            "message": f"not a directory: {plugin_root}",
        }, indent=2))
        return 2

    results = []
    if args.gate in ("review", "all"):
        results.append(review_gate(planning_dir, project_root))
    if args.gate in ("sections", "all"):
        results.append(sections_gate(planning_dir, project_root, plugin_root))
    if args.gate in ("boundary", "all"):
        results.append(boundary_gate(project_root))

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
