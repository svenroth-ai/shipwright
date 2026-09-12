"""FR-01.06 #6 (floor half): "a project with no browser tests gets them
written from the plan's journeys." Split out of ``_test_gate_extras.py`` the
moment that file crossed 300 lines with #5 and #6 both present (sub-iterate
``e3-checks-test-security``, ``.shipwright/planning/campaigns/
2026-07-23-req3-ac-evidence-ledger-mono.md``) — mirrors the earlier split of
the design-fidelity gate into ``_test_gate_fidelity.py``.

:func:`check_e2e_specs_exist_when_journeys_planned` — the *coverage-matching*
half of this promise already shipped as criterion 14 (``journey_coverage.py``,
iterate-2026-07-27-test-phase-record-honesty) and is enforced+tested there.
What was still bare prose is the *generation* half: step 2.5 is agent-driven,
and nothing stops a run from completing with a planned flow and zero
generated specs if the agent simply never runs it. **This is a floor, not
full coverage of criterion 6** — external review (both reviewers) correctly
named it a weak oracle (one arbitrary ``*.spec.ts`` satisfies it, regardless
of which journey it names): the per-journey name-matching half stays
criterion 14's job on purpose, so this check only closes "did *anything* get
generated for a plan that declares at least one flow", never "does the
generated spec name the right journey". Recorded as such on the ledger row,
not as a full close, with the real fix (wiring in ``journey_coverage.py``)
filed as follow-up triage ``trg-2f7a840a`` — it needs relocating that
module's shared logic to ``shared/scripts/lib/`` first (ADR-045: a shared
verifier never reaches into a single plugin's own ``scripts/lib``), which is
a producer-side design change outside this checks-only sub-iterate's scope.
"""

from __future__ import annotations

import re
from pathlib import Path

from ._test_gate_extras import _is_within
from .common import CheckResult, Severity

# Mirrors journey_plan.py's own heading grammar (plugins/shipwright-test/
# scripts/lib/journey_plan.py: `_USER_FLOWS_SECTION`) at the coarse level this
# check needs — presence of at least one flow heading, not per-journey
# title/slug extraction, which stays that module's job. Deliberately
# CASE-SENSITIVE, matching `_USER_FLOWS_SECTION` exactly (verified by
# reading it before writing this) — external review round 2 (GLM) correctly
# flagged that a case-insensitive floor could count a heading the real
# generator (`journey_plan.py`) does not, making this "does the plan declare
# a flow" answer disagree with the tool it is floor-checking; a false SKIP
# from case-sensitivity is preferable to a floor that answers a different
# question than the pipeline it verifies. ``_NEXT_H2_RE`` terminates the
# section on ANY subsequent H2, including a duplicate ``## User Flows`` —
# this ONE line is a deliberate, narrow divergence from `journey_plan.py`'s
# own negative-lookahead (which does not terminate on a repeat heading): a
# repeated heading is not a valid terminator either way, and fixing it here
# only makes this floor check stricter (fewer false "declares a flow"
# answers), never looser. `journey_plan.py` itself is out of scope for a
# checks-only sub-iterate to change.
_USER_FLOWS_HEADING_RE = re.compile(r"^##\s+User Flows\s*$", re.MULTILINE)
_NEXT_H2_RE = re.compile(r"^##\s+\S", re.MULTILINE)
_H3_HEADING_RE = re.compile(r"^###\s+\S", re.MULTILINE)


def _plan_declares_a_flow(plan_text: str) -> bool:
    match = _USER_FLOWS_HEADING_RE.search(plan_text)
    if not match:
        return False
    section = plan_text[match.end():]
    next_h2 = _NEXT_H2_RE.search(section)
    if next_h2:
        section = section[: next_h2.start()]
    return bool(_H3_HEADING_RE.search(section))


def check_e2e_specs_exist_when_journeys_planned(project_root: Path) -> CheckResult:
    """FR-01.06 #6 (floor, not full coverage): a project with no browser
    tests gets SOMETHING written from the plan's journeys.

    Deliberately coarse — existence, not per-journey matching (criterion
    14's ``journey_coverage.py`` job, enforced+tested separately). A single
    unrelated spec file satisfies this check; it exists to catch total
    non-generation, not to verify the generated spec names the right
    journey.

    SKIPPED when there is no E2E plan to generate from, or the plan(s) found
    declare no flows under ``## User Flows`` (a planning-phase concern, not
    this one's).
    """
    name = "e2e specs exist when the plan declares user flows (floor check)"
    planning = project_root / ".shipwright" / "planning"
    if not planning.is_dir():
        return CheckResult(
            name, True, "no .shipwright/planning/ — nothing to generate from",
            severity=Severity.SKIPPED.value,
        )

    plan_files = sorted(planning.rglob("claude-plan-e2e.md"))
    if not plan_files:
        return CheckResult(
            name, True, "no claude-plan-e2e.md found — nothing to generate from",
            severity=Severity.SKIPPED.value,
        )

    plans_with_flows = 0
    for plan_file in plan_files:
        try:
            if not plan_file.is_file() or not _is_within(project_root, plan_file):
                continue  # missing, or a symlink escaping the project root
            # ``utf-8-sig`` (not ``utf-8``): a plan file saved with a
            # leading UTF-8 BOM (Notepad, some Windows editors) otherwise
            # keeps the BOM as the first character of the first line, so
            # ``^##`` never matches a heading that happens to open the
            # file — a real empirical probe (Step 3.8, confidence
            # calibration) caught this false-negative before it shipped.
            text = plan_file.read_text(encoding="utf-8-sig")
        except OSError:
            continue
        if _plan_declares_a_flow(text):
            plans_with_flows += 1

    if not plans_with_flows:
        return CheckResult(
            name, True,
            f"{len(plan_files)} E2E plan(s) found but none declare a flow under "
            f"'## User Flows'",
            severity=Severity.SKIPPED.value,
        )

    e2e_dir = project_root / "e2e"
    all_spec_files = sorted(e2e_dir.rglob("*.spec.ts")) if e2e_dir.is_dir() else []
    # External review round 2 (openai, low/security): a repo-controlled
    # symlink under e2e/ pointing outside the project could otherwise
    # satisfy this gate without any real project-local browser test — same
    # escape class `_is_within` already closes for the plan files above.
    spec_files = [f for f in all_spec_files if _is_within(project_root, f)]
    if not spec_files:
        return CheckResult(
            name, False,
            f"{plans_with_flows} E2E plan(s) declare user flows, but no *.spec.ts "
            f"exists under e2e/ — step 2.5 generation never produced them",
        )
    return CheckResult(
        name, True,
        f"{len(spec_files)} e2e spec file(s) present against {plans_with_flows} "
        f"plan(s) with flows",
    )


__all__ = [
    "check_e2e_specs_exist_when_journeys_planned",
]
