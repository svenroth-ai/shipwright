"""Four /shipwright-plan Step-6/Step-9 gates the ledger walk found nowhere in
code (``.shipwright/planning/campaigns/2026-07-23-req3-ac-evidence-ledger-mono.md``,
FR-01.03). Each function below is named for, and enforces, exactly one
criterion row:

* :func:`review_key_honesty` — **#1b** "No review key ⇒ stops and asks." The
  ledger's own gap: ``is_external_review_enabled``/``get_external_review_status``
  had no production caller, so nothing ever caught a marker that silently
  skipped review while a key was actually available.
* :func:`decisions_recorded` — **#8** "Design decisions recorded with
  reasoning." ``write_decision_log.py`` exists; nothing required calling it.
* :func:`findings_addressed` — **#10** "Review findings addressed or
  rejected-with-reason." A recorded ``findings_count`` was never checked
  against what actually got logged.
* :func:`e2e_journeys_named` — **#11** "UI project's plan names the
  end-to-end journeys." ``e2e_exists`` was checked for file *presence* only;
  nothing required the file to actually name a flow.

Each check takes plain data (marker dict, decision-log text, file content) so
it composes into ``check-plan-gates.py`` without re-reading the filesystem
itself — the caller already has these artifacts on hand.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

__all__ = [
    "GateResult",
    "decisions_recorded",
    "e2e_journeys_named",
    "findings_addressed",
    "review_key_honesty",
]


@dataclass(frozen=True)
class GateResult:
    ok: bool
    detail: str


# --------------------------------------------------------------------------- #
# #1 — review key honesty
# --------------------------------------------------------------------------- #


def review_key_honesty(marker: dict[str, Any] | None, computed_status: str) -> GateResult:
    """The converse the ledger names: a route WAS available and the marker
    still records a skip.

    ``computed_status`` is ``get_external_review_status()``'s three-way
    answer, read fresh at check time. If it says ``available`` (a key is
    present and ``feedback_iterations > 0``), a ``skipped_*`` marker means
    Branch A never ran even though nothing stopped it — the STOP-and-ask
    promise for the missing-key case is only honest if the present-key case
    is never silently skipped either. ``missing_keys``/``user_disabled``
    place no obligation on the marker: those are exactly the branches a skip
    is legitimate for.
    """
    if computed_status != "available":
        return GateResult(True, f"computed_status={computed_status} — a skip is not held to this rule")
    if not isinstance(marker, dict):
        return GateResult(True, "no marker yet to check for a false skip")
    status = str(marker.get("status") or "")
    if status.startswith("skipped_"):
        return GateResult(
            False,
            f"external review keys are available (feedback_iterations>0) but the "
            f"marker records {status!r} — Branch A must run, not be silently skipped",
        )
    return GateResult(True, f"marker status={status!r} is consistent with an available route")


# --------------------------------------------------------------------------- #
# #8 / #10 — decision-log trail
# --------------------------------------------------------------------------- #

_SECTION_LINE_RE = re.compile(r"-\s*\*\*Section:\*\*\s*(.+)$", re.MULTILINE)

#: Section-tag prefixes Step 2 / Step 5 / Step 5a / Self-Review write, per
#: `step-5-external-review.md` and SKILL.md Step 2. A planning session that
#: never wrote any of these logged no decision at all.
_PLAN_DECISION_PREFIXES = (
    "Plan Interview",
    "Internal Plan Review",
    "External Review",
    "Architecture Review",
    "Self-Review",
)


def _sections_for_split(decision_log_text: str, split_name: str) -> list[str]:
    """Every ``**Section:**`` value in ``decision_log_text`` naming this split
    (``"{prefix} — {split_name}"``, em-dash per ``write_decision_log.py``)."""
    return [
        s.strip() for s in _SECTION_LINE_RE.findall(decision_log_text)
        if s.strip().endswith(f"— {split_name}") or s.strip().endswith(f"- {split_name}")
    ]


def decisions_recorded(decision_log_text: str, split_name: str) -> GateResult:
    """**#8** — at least one planning decision was logged for this split,
    under any of the section tags the plan phase itself writes."""
    sections = _sections_for_split(decision_log_text, split_name)
    plan_sections = [
        s for s in sections
        if any(s.startswith(prefix) for prefix in _PLAN_DECISION_PREFIXES)
    ]
    if not plan_sections:
        return GateResult(
            False,
            f"decision_log.md has no entry tagged for {split_name!r} under any of "
            f"{_PLAN_DECISION_PREFIXES} — no design decision was recorded with its reasoning",
        )
    return GateResult(True, f"{len(plan_sections)} decision(s) logged for {split_name!r}")


def findings_addressed(decision_log_text: str, split_name: str, findings_count: int) -> GateResult:
    """**#10** — a nonzero recorded ``findings_count`` must be matched by at
    least that many logged entries. Step 5b sets ``findings_count`` from
    whichever review actually carried the gate: Branch A's external review
    logs under ``"External Review — {split_name}"``, but when the Pre-5b
    Checkpoint found the internal review (opus-plan-reviewer) carrying the
    gate instead (no external keys, or a degraded external run),
    ``findings_count`` is the *internal* review's count and its entries are
    logged under ``"Internal Plan Review — {split_name}"``
    (`step-5-external-review.md`). Counting only the external tag would
    false-fail every plan that took that path.
    ``findings_count == 0`` has nothing to check — this gate is silent then."""
    if findings_count <= 0:
        return GateResult(True, "findings_count=0 — nothing to reconcile")
    logged = [
        s for s in _sections_for_split(decision_log_text, split_name)
        if s.startswith("External Review") or s.startswith("Internal Plan Review")
    ]
    if len(logged) < findings_count:
        return GateResult(
            False,
            f"marker records findings_count={findings_count} but only {len(logged)} "
            f"'External Review — {split_name}' / 'Internal Plan Review — {split_name}' "
            f"entr{'y' if len(logged) == 1 else 'ies'} logged — every finding must be "
            "addressed or rejected-with-reason",
        )
    return GateResult(True, f"{len(logged)} finding(s) logged, >= findings_count={findings_count}")


# --------------------------------------------------------------------------- #
# #11 — E2E journeys named
# --------------------------------------------------------------------------- #

_FLOW_HEADING_RE = re.compile(r"^\s{0,3}#{2,6}\s+.*flow.*$", re.IGNORECASE | re.MULTILINE)


def e2e_journeys_named(e2e_plan_path: Path, expect_e2e: bool) -> GateResult:
    """**#11** — a UI project's E2E plan must actually name a journey, not
    merely exist. ``setup-planning-session.py`` only ever checked
    ``e2e_exists`` for resume routing; nothing required content."""
    if not expect_e2e:
        return GateResult(True, "not a UI project (or e2e_test_plan disabled) — no journeys required")
    if not e2e_plan_path.exists():
        return GateResult(False, f"{e2e_plan_path.name} is required for a UI project but does not exist")
    try:
        content = e2e_plan_path.read_text(encoding="utf-8", errors="ignore")
    except OSError as exc:
        return GateResult(False, f"{e2e_plan_path.name} unreadable: {exc}")
    if not _FLOW_HEADING_RE.search(content):
        return GateResult(
            False,
            f"{e2e_plan_path.name} exists but names no flow (expected a "
            "'### Flow N: ...' heading) — an empty file satisfies presence but not the promise",
        )
    return GateResult(True, f"{e2e_plan_path.name} names at least one flow")
