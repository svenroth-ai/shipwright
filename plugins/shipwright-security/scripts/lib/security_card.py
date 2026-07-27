#!/usr/bin/env python3
"""The security-scan card the operator receives and executes.

The operator's workflow is: a card arrives in the Triage Inbox, they launch it,
and the work happens. So the point of work is the card — that is where the
severity split and the scope question belong. A card that carries only a total
leaves the executing agent to decide silently whether the twenty low-severity
findings matter.

This module builds one collapsed action unit per repository carrying:

- the count at EVERY severity, not a bare total;
- what the scan did NOT check (from the coverage manifest), so a card reporting
  three findings from one tool cannot read as a whole-repository verdict;
- a launch payload that instructs the executing agent to state those counts and
  ASK how far to go before changing anything.

Inbox hygiene is the same contract the ``gh-security`` producer follows: only
aggregated counts and stable paths reach ``title`` / ``detail`` /
``launch_payload`` — never a rule id, a description, or an affected file. A
security card is read in a shared surface; it must not become the leak.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

_LIB_DIR = Path(__file__).resolve().parent
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

from coverage_report import coverage_summary_line  # noqa: E402
from scan_coverage import class_label, is_complete, unchecked_classes  # noqa: E402

SCAN_CARD_PREFIX = "security-scan:"

# The launch payload is read back as INSTRUCTIONS by the agent that executes the
# card, so any caller-supplied value spliced into it is an injection surface —
# `--repo` and the report path are both caller-controlled. A newline followed by
# imperative text would read as a new instruction line. Every such value goes
# through _safe_field: control characters (newline included) collapse to a
# space, and the result is length-capped.
_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]+")
_FIELD_MAX_LEN = 200

SEVERITY_ORDER: tuple[str, ...] = ("critical", "high", "medium", "low", "info")

# Same mapping the per-finding mirrors use, so one scan cannot classify the
# same severity two different ways on two surfaces.
_KIND_FROM_SEVERITY = {
    "critical": "bug",
    "high": "bug",
    "medium": "improvement",
    "low": "improvement",
    "info": "improvement",
}

# Matches the ``gh-security`` producer's cap so no producer can bloat the inbox.
_DETAIL_MAX_LEN = 1024


def _safe_field(value: Any) -> str:
    """Flatten a caller-supplied value for splicing into the launch payload.

    Collapses every control character (newlines above all) to a single space and
    caps the length, so a repository name or report path cannot open a new
    instruction line in a payload an agent will execute.
    """
    flattened = _CONTROL_CHARS.sub(" ", str(value)).strip()
    return flattened[:_FIELD_MAX_LEN]


def severity_counts(findings: list[dict[str, Any]] | None) -> dict[str, int]:
    """Count findings per severity, with every bucket present even at zero.

    A missing or unrecognized severity buckets as ``medium`` — the same
    conservative fallback the per-finding triage mirrors apply, so the card's
    arithmetic always agrees with the items beside it.
    """
    counts = {sev: 0 for sev in SEVERITY_ORDER}
    for f in findings or []:
        if not isinstance(f, dict):
            continue
        sev = str(f.get("severity") or "").strip().lower()
        counts[sev if sev in counts else "medium"] += 1
    return counts


def top_severity(counts: dict[str, int]) -> str | None:
    """The most severe bucket that has anything in it, or ``None``."""
    return next((s for s in SEVERITY_ORDER if counts.get(s, 0) > 0), None)


def format_counts(counts: dict[str, int]) -> str:
    """``critical: 2, high: 3, medium: 10, low: 7, info: 0``."""
    return ", ".join(f"{sev}: {counts.get(sev, 0)}" for sev in SEVERITY_ORDER)


def scope_options(counts: dict[str, int]) -> str:
    """Render the concrete choices of how far to go, most severe first.

    ``everything (22), critical and above (2), high and above (5)`` — the
    operator picks a line, rather than being asked an abstract "how far?".
    Only severities that actually have findings become options, so the
    question never offers an empty bucket.
    """
    total = sum(counts.values())
    options = [f"everything ({total})"]
    cumulative = 0
    for sev in SEVERITY_ORDER:
        cumulative += counts.get(sev, 0)
        if counts.get(sev, 0) == 0 or cumulative == total:
            # An empty tier is not a choice, and a tier that already covers
            # everything is just "everything" under another name.
            continue
        options.append(f"{sev} and above ({cumulative})")
    return ", or ".join(options) if len(options) > 1 else options[0]


def _title(counts: dict[str, int], worst: str, total: int) -> str:
    """Lead with the split, not a bare total.

    "2 critical, 20 below" is actionable; "22 findings" is not.
    """
    below = total - counts.get(worst, 0)
    head = f"Security scan: {counts[worst]} {worst}"
    tail = f", {below} below" if below else ""
    return f"{head}{tail} ({total} total)"[:160]


def build_scan_action_unit(
    *,
    findings: list[dict[str, Any]] | None,
    coverage: list[dict[str, Any]] | None,
    repo: str,
    report_path: str | None = None,
) -> dict[str, Any] | None:
    """One collapsed card for a local scan, or ``None`` when there is nothing
    to act on.

    A clean scan emits no card — the Triage Inbox is a work list, and an
    absence of findings is not work. (What the scan did *not* check is carried
    by the report and by any card that does fire; see ``coverage_report``.)
    """
    live = [f for f in (findings or []) if isinstance(f, dict)]
    if not live:
        return None

    counts = severity_counts(live)
    worst = top_severity(counts) or "medium"
    total = len(live)
    breakdown = format_counts(counts)
    coverage_line = coverage_summary_line(coverage)
    unchecked = unchecked_classes(coverage)
    safe_repo = _safe_field(repo)

    detail = f"Repo {safe_repo} | {breakdown} | {coverage_line}"
    if report_path:
        detail += f" | report: {_safe_field(report_path)}"
    if len(detail) > _DETAIL_MAX_LEN:
        detail = detail[: _DETAIL_MAX_LEN - 1] + "…"

    # "every class was checked" is claimed ONLY on a fully-covered manifest.
    # unchecked_classes() deliberately excludes degraded rows, so keying the
    # all-clear off it alone would tell the operator everything was checked
    # when a leg had in fact fataled — the reassuring-payload failure this card
    # exists to prevent.
    if unchecked:
        coverage_note = (
            "Coverage — not checked: "
            + ", ".join(class_label(c) for c in unchecked)
            + ". Those classes are not clean, they are unexamined.\n"
        )
    elif is_complete(coverage):
        coverage_note = "Coverage — every class was checked.\n"
    else:
        coverage_note = (
            f"Coverage — INCOMPLETE ({coverage_summary_line(coverage)}). "
            "See the scan errors before trusting any class as clean.\n"
        )
    report_note = f"Report: {_safe_field(report_path)}\n" if report_path else ""

    payload = (
        f"/shipwright-security\n"
        f"\n"
        f"Context: the local security scan reports {total} open finding(s) "
        f"for {safe_repo}.\n"
        f"Severity breakdown — {breakdown}.\n"
        f"{coverage_note}"
        f"{report_note}"
        f"\n"
        f"Before changing anything: state these per-severity counts to the "
        f"operator and ask how far to go — {scope_options(counts)}? "
        f"Do not decide silently that the less severe findings do not matter.\n"
        f"Source: triage item {SCAN_CARD_PREFIX}{safe_repo}"
    )

    return {
        "severity": worst,
        "kind": _KIND_FROM_SEVERITY[worst],
        "title": _title(counts, worst, total),
        "detail": detail,
        # Sanitized here too: the dedup key must stay a single stable line, and
        # it is what the payload's "Source:" footer already names.
        "dedup_key": f"{SCAN_CARD_PREFIX}{safe_repo}",
        "launch_payload": payload,
    }
