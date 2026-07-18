"""Match keys and provenance for accepted-risk convergence.

The vocabulary half of the convergence domain: what an alert is reduced to,
what a register entry claims, and how a machine dismissal is recognised later.
:mod:`alert_convergence` builds the plan on top of it. Pure — no I/O, no ``gh``.

**The match key is ``(tool, rule, path)``.** Not the rule alone, and not the
line. Measured on this repo before the design was fixed: eight *different*
judgments share the rule id ``py/unused-global-variable``, and the one alert
still open at the time shared it too — so a rule-wide match would have swallowed
a brand-new, never-reviewed finding on its first run. The line is excluded for
the opposite reason: it drifts on every edit above the finding, which would
manufacture permanent false drift.

Breadth is **declared, never inferred**. An entry names an explicit path
allowlist or opts into ``match: rule-wide`` in as many words; one that does
neither is refused. There is deliberately no "if it happens to match exactly one
alert, take it" rule — that silently widens the day a second alert appears,
which is the same failure with extra steps.

**Provenance decides what may be undone.** A dismissal this tool writes carries
``[shipwright-accepted-risk: <id>]``. Reopen selects only marked alerts, so a
human's dismissal is never reopened and never overwritten — the 50 dismissals
already on this repo are all unmarked, and all of them must stay untouched.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

#: Machine provenance stamped into every dismissal this tool writes. Absence is
#: the signal that a human wrote it, so the marker must never be optional.
MARKER_RE = re.compile(r"\[shipwright-accepted-risk:\s*([A-Za-z0-9._+-]+)\s*\]")

#: Explicit opt-in for an acceptance covering every path a rule fires on.
MATCH_RULE_WIDE = "rule-wide"

#: GitHub's closed vocabulary for ``dismissed_reason``.
DISMISS_REASONS = ("false positive", "won't fix", "used in tests")
DEFAULT_DISMISS_REASON = "won't fix"

_COMMENT_MAX = 280


@dataclass(frozen=True)
class Alert:
    """One code-scanning alert, reduced to what matching needs."""

    number: int
    tool: str
    rule: str
    path: str
    state: str
    dismissed_comment: str = ""

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.tool, self.rule, self.path)

    @property
    def marker(self) -> str | None:
        """The register-entry id this tool stamped, or ``None`` if human."""
        return marker_in(self.dismissed_comment)


def alert_from_api(payload: Any) -> Alert | None:
    """Reduce a GitHub alert payload to an :class:`Alert`, or ``None``.

    ``None`` rather than a partial object when any component of the match key
    is missing — an alert we cannot key is one we must not act on, and a
    half-built key would match by accident.
    """
    if not isinstance(payload, dict):
        return None
    number = payload.get("number")
    tool = (payload.get("tool") or {}).get("name")
    rule = (payload.get("rule") or {}).get("id")
    instance = payload.get("most_recent_instance") or {}
    path = (instance.get("location") or {}).get("path")
    if not isinstance(number, int) or not all(
        isinstance(v, str) and v for v in (tool, rule, path)
    ):
        return None
    return Alert(
        number=number,
        tool=tool,
        rule=rule,
        path=path,
        state=payload.get("state") or "",
        dismissed_comment=payload.get("dismissed_comment") or "",
    )


def marker_for(entry_id: str) -> str:
    return f"[shipwright-accepted-risk: {entry_id}]"


def marker_in(comment: str | None) -> str | None:
    if not isinstance(comment, str):
        return None
    match = MARKER_RE.search(comment)
    return match.group(1) if match else None


def dismissal_comment(entry: Any) -> str:
    """The comment written onto a dismissed alert.

    Derived from the register entry so the security tab carries the same
    justification the repo does, and always terminated by the marker — the
    marker is what makes the dismissal reversible by this tool and only by it.
    """
    suffix = f" {marker_for(entry.id)}"
    head = f"{entry.statement} (ref {entry.rationale_ref}, expires {entry.expires})"
    room = _COMMENT_MAX - len(suffix)
    if len(head) > room:
        head = head[: room - 1].rstrip() + "…"
    return f"{head}{suffix}"


def scope_problem(entry: Any) -> str | None:
    """Why ``entry`` cannot be resolved to alerts, or ``None`` if it can.

    Ambiguity is refused here rather than resolved by guessing: a loose match
    dismisses unrelated judgments, a strict one manufactures false drift.
    """
    scope = entry.scope or {}
    tool = scope.get("tool")
    if not isinstance(tool, str) or not tool.strip():
        return (
            "scope.tool is required (a rule id is not unique across tools — "
            "CodeQL and Scorecard both emit ids)"
        )
    paths = scope.get("paths")
    rule_wide = scope.get("match") == MATCH_RULE_WIDE
    if paths is None and not rule_wide:
        return (
            "declare breadth explicitly: either scope.paths (an allowlist) or "
            f"scope.match: {MATCH_RULE_WIDE}. Refusing to guess — on this repo "
            "8 unrelated judgments share one rule id."
        )
    if paths is not None:
        if rule_wide:
            return (
                f"scope.paths and scope.match: {MATCH_RULE_WIDE} are mutually "
                "exclusive — one narrows, the other does not"
            )
        if not isinstance(paths, list) or not paths:
            return "scope.paths must be a non-empty list of repo-relative paths"
        if not all(isinstance(p, str) and p.strip() for p in paths):
            return "scope.paths entries must be non-empty strings"
    reason = scope.get("dismissed_reason", DEFAULT_DISMISS_REASON)
    if reason not in DISMISS_REASONS:
        return (
            f"scope.dismissed_reason {reason!r} is not one of "
            + ", ".join(repr(r) for r in DISMISS_REASONS)
        )
    return None


def dismiss_reason_for(entry: Any) -> str:
    return (entry.scope or {}).get("dismissed_reason", DEFAULT_DISMISS_REASON)


def entry_matches(entry: Any, tool: str, rule: str, path: str) -> bool:
    """Does ``entry`` claim the alert identified by ``(tool, rule, path)``?

    An entry with an unresolvable scope matches nothing — the refusal is
    enforced here too, so a caller that forgets :func:`scope_problem` still
    cannot dismiss anything on an ambiguous entry.
    """
    if scope_problem(entry) is not None:
        return False
    scope = entry.scope or {}
    if scope.get("tool") != tool or entry.rule != rule:
        return False
    if scope.get("match") == MATCH_RULE_WIDE:
        return True
    return path in (scope.get("paths") or [])


def triage_item_key(dedup_key: Any) -> tuple[str, str, str] | None:
    """``{tool}:{check_id}:{file}:{line}`` -> ``(tool, check_id, file)``.

    The line is dropped so the key survives edits above the finding. Parsed
    from both ends because a ``check_id`` may itself contain colons; anything
    that does not yield four parts is unparseable and matches nothing.
    """
    if not isinstance(dedup_key, str) or dedup_key.count(":") < 3:
        return None
    head, _, _line = dedup_key.rpartition(":")
    tool, _, rest = head.partition(":")
    check_id, _, path = rest.rpartition(":")
    if not (tool and check_id and path):
        return None
    return (tool, check_id, path)
