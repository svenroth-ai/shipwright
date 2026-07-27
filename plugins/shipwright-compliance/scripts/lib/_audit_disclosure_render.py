"""Rendering for "when did the cross-check last run?".

Two shapes, one fact (:mod:`scripts.lib.audit_disclosure` owns the fact):

- :func:`format_note` — the one-line suffix on every evidence document's
  ``Generated:`` header, so a reader who opens one document in isolation can
  weigh it without hunting for the dashboard.
- :func:`render_consistency_audit` — the dashboard's full section (AR-03).

Both are pure functions of *(durable record, reference date)* — no wall-clock, no
gitignored transient. Regenerating a document therefore only changes it when the
event log or the audit record changed, which is the property the tracked-doc
staleness check depends on. Note the record IS a render input: running the audit
between two regens legitimately changes the documents. That is the feature.

Four states, kept distinct because collapsing them would produce exactly the
false confidence this exists to remove:

===============  ==========================================================
never run        no audit has ever been recorded
unknown          a record exists but is unreadable — *not* "never run"
partial only     runs happened, but the whole project was never checked
checked          the last whole-project cross-check, with its age
===============  ==========================================================
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

# RELATIVE, deliberately (ADR-045). ``collect_all`` reaches this module as
# ``lib._audit_disclosure_render`` when a caller puts ``…/scripts`` on sys.path —
# the traceability/FR-table tooling does exactly that — and under that package
# root an absolute ``scripts.lib.…`` import does not resolve.
from .audit_disclosure import (
    ABSENT,
    VALID,
    AuditFreshness,
    AuditRecord,
    load_audit_freshness,
)

_LEAD = "Consistency-audit: "
_NEVER = "never run"
_UNKNOWN = "last-run record unreadable (status unknown)"
_ON_DEMAND = (
    "_On demand by design: the audit has no schedule and no CI trigger, so it "
    "never runs on its own"
)


def _age_phrase(ran_at: str, as_of: str) -> str:
    """How long before ``as_of`` the run happened; ``""`` when undeterminable.

    Clamped at zero: ``as_of`` is the event-pinned render reference, which can
    legitimately trail a just-completed audit, and a negative age would read as
    nonsense ("checked in 2 days").
    """
    try:
        ran = date.fromisoformat(ran_at[:10])
        ref = date.fromisoformat((as_of or "")[:10])
    except (ValueError, TypeError):
        return ""
    days = (ref - ran).days
    if days <= 0:
        return "same day"
    return "1 day earlier" if days == 1 else f"{days} days earlier"


def _when(record: AuditRecord, as_of: str) -> str:
    age = _age_phrase(record.ran_at, as_of)
    return f"{record.ran_at[:10]}{f' ({age})' if age else ''}"


def _verdict(record: AuditRecord) -> str:
    return "FAIL" if record.verdict == "fail" else "PASS"


def _groups(record: AuditRecord) -> str:
    return f"groups {record.scope}" if record.scope else "scope unspecified"


def format_note(freshness: AuditFreshness, *, as_of: str) -> str:
    """The third provenance line of every evidence document.

    Terse by design — it sits beside ``Generated:`` and ``Source-State:``, and the
    dashboard's Consistency Audit section carries the long form. Always non-empty
    and always single-line: silence is the state this exists to abolish, and a
    newline would break the header block it rides in. A partial run never
    displaces the last full cross-check — it is reported alongside it.
    """
    if freshness.status != VALID or freshness.latest is None:
        return f"{_LEAD}{_NEVER if freshness.status == ABSENT else _UNKNOWN}"

    latest, full = freshness.latest, freshness.latest_full
    if latest.is_full:
        return f"{_LEAD}last run {_when(latest, as_of)} — {_verdict(latest)}"
    if full is None:
        return (
            f"{_LEAD}never fully run; latest {_when(latest, as_of)} "
            f"partial ({_groups(latest)})"
        )
    return (
        f"{_LEAD}last full run {_when(full, as_of)} — {_verdict(full)}; "
        f"latest {latest.ran_at[:10]} partial ({_groups(latest)})"
    )


def freshness_note(project_root: Path, *, as_of: str) -> str:
    """:func:`format_note` over the project's durable record."""
    return format_note(load_audit_freshness(project_root), as_of=as_of)


def _checks_sentence(record: AuditRecord) -> str:
    checks = record.checks
    total = checks.get("total") if isinstance(checks, dict) else None
    if not isinstance(total, int) or total <= 0:
        return ""
    return (
        f" · {total} checks — {checks.get('pass', 0)} pass, "
        f"{checks.get('fail', 0)} fail, {checks.get('skip', 0)} skip."
    )


def _headline(freshness: AuditFreshness, as_of: str) -> list[str]:
    latest, full = freshness.latest, freshness.latest_full
    if latest is not None and latest.is_full:
        return [
            f"**Last run {_when(latest, as_of)}: {_verdict(latest)}**"
            f"{_checks_sentence(latest)}",
        ]
    if full is None:
        return [
            "**Never fully run — no cross-check has covered the whole project.**",
            "",
            f"The latest run ({_when(latest, as_of)}) checked only "
            f"{_groups(latest)}: {_verdict(latest)}{_checks_sentence(latest)}",
        ]
    return [
        f"**Last full run {_when(full, as_of)}: {_verdict(full)}**"
        f"{_checks_sentence(full)}",
        "",
        f"Since then the only run was a partial one ({_when(latest, as_of)}, "
        f"{_groups(latest)}: {_verdict(latest)}), which does not re-check the "
        "rest of the project.",
    ]


def render_consistency_audit(project_root: Path, *, as_of: str) -> list[str]:
    """The dashboard's Consistency Audit section (AR-03).

    Rendered from the durable record ONLY — never from the gitignored
    ``audit-report.*`` transients — so the tracked dashboard reads identically on
    a developer's machine, in CI, and on the public repo.
    """
    lines = ["## 🔎 Consistency Audit", ""]
    freshness = load_audit_freshness(project_root)

    if freshness.status != VALID or freshness.latest is None:
        if freshness.status == ABSENT:
            head = (
                "**Never run — nothing has cross-checked this evidence against "
                "the project's actual state.**"
            )
            tail = f"{_ON_DEMAND} — invoke `/shipwright-compliance` to establish a first reading._"
        else:
            head = (
                "**Unknown — the last-run record is unreadable, so whether this "
                "evidence was ever cross-checked cannot be established.**"
            )
            tail = (
                f"{_ON_DEMAND}. Re-run `/shipwright-compliance` to replace the "
                "damaged record with a real reading._"
            )
        lines.extend([head, "", tail, ""])
        return lines

    lines.extend(_headline(freshness, as_of))
    lines.extend([
        "",
        f"{_ON_DEMAND}, so this date is how far back the last cross-check "
        "reaches — anything that drifted after it is unmeasured._",
        "",
    ])
    return lines


__all__ = ["format_note", "freshness_note", "render_consistency_audit"]
