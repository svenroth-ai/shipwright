"""FR-01.06 journey coverage gate.

The parser and name-matching heuristic live in ``shared/scripts/lib`` so the
test producer and this verifier cannot drift (ADR-045). A generic spec is no
longer enough: every plan journey must have a matching filename or mention in
a spec body. Brownfield gaps retain the shared mechanism's non-blocking,
follow-up-oriented policy.
"""

from __future__ import annotations

from pathlib import Path

from lib.journey_coverage import check_journey_coverage

from .common import CheckResult, Severity


def check_e2e_specs_exist_when_journeys_planned(project_root: Path) -> CheckResult:
    """Verify each plan journey has a matching project-local browser spec."""
    name = "planned user journeys have matching e2e coverage"
    report = check_journey_coverage(
        project_root, emit_triage=False, require_user_flows_section=True,
    )
    status = report["status"]
    if report.get("unreadable_plans"):
        return CheckResult(
            name, False,
            "cannot verify every planned journey because "
            f"{report['unreadable_plans']} E2E plan(s) could not be read",
        )
    if report.get("unreadable_specs"):
        return CheckResult(
            name, False,
            "cannot verify every planned journey because "
            f"{report['unreadable_specs']} E2E spec(s) could not be read",
        )
    if report.get("malformed_flow_headings"):
        return CheckResult(
            name, False,
            "cannot verify every planned journey because "
            f"{report['malformed_flow_headings']} User Flows heading(s) omit a journey title",
        )
    if status == "undetermined":
        return CheckResult(name, True, report["diagnostic"], severity=Severity.SKIPPED.value)
    if status == "covered":
        return CheckResult(name, True, report["diagnostic"])
    if status == "no_specs":
        if report["mode"] == "brownfield":
            return CheckResult(
                name, False, report["diagnostic"], severity=Severity.WARNING.value,
                strict_exempt=True,
            )
        return CheckResult(name, False, report["diagnostic"])

    uncovered = ", ".join(item["identity"] for item in report["uncovered"])
    detail = f"{report['diagnostic']}; uncovered: {uncovered}"
    if report["blocking"]:
        return CheckResult(name, False, detail)
    return CheckResult(
        name, False, detail, severity=Severity.WARNING.value, strict_exempt=True,
    )


__all__ = ["check_e2e_specs_exist_when_journeys_planned"]
