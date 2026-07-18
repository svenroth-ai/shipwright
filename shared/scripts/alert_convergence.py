"""Resolve accepted-risk register entries onto the surfaces that still show red.

Phase 1 (``accepted_risks``) made an acceptance a recorded, validated,
time-bounded object and gated it both directions. It deliberately did **not**
quiet the code-scanning alerts, so the repo could still show red for a
consciously accepted risk — the root cause of webui #285, where the red got
cleared by hand, without a record, by whoever was annoyed by it first.

This module is the pure core that closes that gap: plain dicts in, a
:class:`Plan` out. Every ``gh`` call lives in ``github_code_scanning`` and every
operator decision in ``tools/accepted_risks_cli``. The split is the
``watch_pr_delivery`` shape — the part worth testing is the part with no network
in it. Match keys and provenance live in :mod:`alert_match`.

Two surfaces resolve from the one key: GitHub code-scanning alerts, and the
per-finding triage items ``generate_security_report`` keys as
``{tool}:{check_id}:{file}:{line}``. Note what is deliberately *absent* — the
``gh-security:{owner}/{repo}`` action-unit is a repo-wide aggregate, so
dismissing it because one alert was accepted would silence every security
finding in the repo. It is left alone on purpose.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from alert_match import (
    Alert,
    entry_matches,
    scope_problem,
    triage_item_key,
)

#: Triage status tokens. Registered in ``triage_gc.MACHINE_DISMISSERS`` /
#: ``MACHINE_REASONS`` in the same diff — that pair is a decoupled SSoT, and a
#: reason absent from it escapes the dismissed-pile GC and accumulates forever.
#: The ``Resolved`` suffix is load-bearing: ``test_triage_wp9_gc`` derives the
#: expected reason set by scanning producers for ``*Resolved``/``*Refreshed``
#: literals, so this name is what makes the coupling enforced rather than
#: remembered.
TRIAGE_DISMISSER = "acceptedRiskConverger"
TRIAGE_REASON = "acceptedRiskResolved"

#: Only this target reaches the live GitHub surface. The others
#: (``trivy-ignore``, ``semgrep-*``) are reconciled offline by Phase 1.
TARGET_GITHUB_DISMISSAL = "github-dismissal"


@dataclass
class Plan:
    """What convergence would do.

    Every disposition is reported separately. Collapsing "not actionable" into
    "clean" is how a gate lies, and an incomplete listing that reads as
    converged is the specific failure this plan exists to make impossible.
    """

    to_dismiss: list[tuple[Any, Alert]] = field(default_factory=list)
    to_reopen: list[tuple[str, Alert]] = field(default_factory=list)
    satisfied: list[tuple[Any, Alert]] = field(default_factory=list)
    ambiguous: list[tuple[Any, str]] = field(default_factory=list)
    conflicted: list[tuple[Alert, list[str]]] = field(default_factory=list)
    stale: list[Any] = field(default_factory=list)
    human_dismissed: list[Alert] = field(default_factory=list)
    triage_dismiss: list[tuple[Any, dict]] = field(default_factory=list)
    #: Set when the triage store exists but could not be read. Distinct from an
    #: empty list: unread is not the same as none, and only one of them may be
    #: reported as converged.
    triage_unreadable: str | None = None

    @property
    def mutates(self) -> bool:
        return bool(self.to_dismiss or self.to_reopen or self.triage_dismiss)

    @property
    def ok(self) -> bool:
        """Converged: nothing to do, nothing refused, nothing unread."""
        return (
            not self.mutates and not self.ambiguous and not self.stale
            and not self.conflicted and self.triage_unreadable is None
        )


def _plan_alerts(plan: Plan, entry: Any, alerts: list[Alert], expired: bool) -> None:
    """Dispose of every alert one entry claims."""
    for alert in alerts:
        if expired:
            # Expiry restores visibility through the same door it left by —
            # but only for what this tool dismissed. A human's dismissal under
            # an expired entry is still REPORTED: dropping it here would let a
            # lapsed acceptance quietly hide a live suppression, which is the
            # same silence this plan exists to break.
            if alert.state != "dismissed":
                continue
            if alert.marker == entry.id:
                plan.to_reopen.append((entry.id, alert))
            else:
                plan.human_dismissed.append(alert)
        elif alert.state != "dismissed":
            plan.to_dismiss.append((entry, alert))
        elif alert.marker == entry.id:
            plan.satisfied.append((entry, alert))
        else:
            # Dismissed by a human, or under another entry's authority.
            # Recorded, never rewritten.
            plan.human_dismissed.append(alert)


def plan_convergence(
    entries: list[Any],
    alerts: list[Alert],
    *,
    now: date,
    triage_items: list[dict] | None = None,
) -> Plan:
    """Compute the convergence plan for ``entries`` against live state.

    Only ``github-dismissal`` targets reach the alert surface. An alert is only
    ever dismissed because some entry claims it, so "never dismiss an alert
    with no backing register entry" holds by construction rather than by a
    check that could be forgotten.
    """
    plan = Plan()
    live = [e for e in entries if e.target == TARGET_GITHUB_DISMISSAL]

    # Resolve claims FIRST, so an alert claimed by two entries is caught before
    # anything acts on it. Overlap is a genuine ambiguity, not a merge: acting
    # on it would PATCH the alert twice (the second comment overwriting the
    # first entry's marker), and then a lapse in EITHER entry would reopen an
    # alert the other one still legitimately covers.
    claims: dict[int, list[Any]] = {}
    for entry in live:
        problem = scope_problem(entry)
        if problem is not None:
            plan.ambiguous.append((entry, problem))
            continue
        matched = [a for a in alerts if entry_matches(entry, *a.key)]
        if not matched:
            plan.stale.append(entry)
            continue
        for alert in matched:
            claims.setdefault(alert.number, []).append(entry)

    by_number = {a.number: a for a in alerts}
    claimed: set[int] = set(claims)
    for number, owners in claims.items():
        if len(owners) > 1:
            plan.conflicted.append((by_number[number], [e.id for e in owners]))
            continue
        entry = owners[0]
        _plan_alerts(plan, entry, [by_number[number]], entry.is_expired(now))

    # Marked alerts whose entry vanished from the register entirely — the same
    # loss of authority as expiry, so the same restoration.
    known = {e.id for e in live}
    for alert in alerts:
        if alert.state != "dismissed" or alert.number in claimed:
            continue
        mark = alert.marker
        if mark is None:
            plan.human_dismissed.append(alert)
        elif mark not in known:
            plan.to_reopen.append((mark, alert))

    for entry in live:
        if scope_problem(entry) is not None or entry.is_expired(now):
            continue
        for item in triage_items or []:
            key = triage_item_key(item.get("dedupKey"))
            if key and entry_matches(entry, *key):
                plan.triage_dismiss.append((entry, item))

    return plan


def format_plan(plan: Plan) -> list[str]:
    """The operator-facing rendering of a plan, one block per disposition.

    Everything the tool declines to touch is printed, not omitted. A gate that
    silently narrows its own scope reads as "all clear" — the same reasoning
    that made Phase 1 print its UNCHECKED rows.
    """
    lines: list[str] = []
    for entry, alert in plan.to_dismiss:
        lines.append(
            f"DISMISS     #{alert.number} {alert.tool}/{alert.rule} "
            f"@ {alert.path}\n    backed by {entry.id} (expires {entry.expires})"
        )
    for entry_id, alert in plan.to_reopen:
        lines.append(
            f"REOPEN      #{alert.number} {alert.tool}/{alert.rule} "
            f"@ {alert.path}\n    authority for {entry_id} lapsed (expired or "
            "removed from the register); restoring visibility."
        )
    for entry, item in plan.triage_dismiss:
        lines.append(
            f"TRIAGE      {item.get('id')} ({item.get('dedupKey')})\n"
            f"    accepted by {entry.id}; filed before the acceptance was "
            "recorded, so ingest-time suppression cannot retract it."
        )
    for entry, problem in plan.ambiguous:
        lines.append(f"AMBIGUOUS   {entry.id}: {problem}")
    for alert, owners in plan.conflicted:
        lines.append(
            f"CONFLICTED  #{alert.number} {alert.tool}/{alert.rule} @ {alert.path}\n"
            f"    claimed by {len(owners)} entries ({', '.join(owners)}). Acting "
            "would dismiss it twice and let a lapse in either one reopen an alert\n"
            "    the other still covers. Narrow their scopes so exactly one applies."
        )
    if plan.triage_unreadable:
        lines.append(
            f"UNREAD      triage store: {plan.triage_unreadable}\n"
            "    Matching triage items could not be checked, so this run cannot "
            "claim the triage surface is converged."
        )
    for entry in plan.stale:
        lines.append(
            f"STALE       {entry.id}: matches no alert. The register claims an "
            "acceptance for something that is not being reported."
        )
    return lines


def format_untouched(plan: Plan) -> list[str]:
    """The two "recorded, not acted on" summaries — never silently dropped."""
    lines: list[str] = []
    if plan.satisfied:
        lines.append(f"  {len(plan.satisfied)} alert(s) already converged.")
    if plan.human_dismissed:
        lines.append(
            f"  {len(plan.human_dismissed)} alert(s) dismissed WITHOUT this "
            "tool's provenance — human judgments, left untouched. They carry no "
            "expiry and no recorded rationale; converting them to register "
            "entries is a person's call."
        )
    return lines
