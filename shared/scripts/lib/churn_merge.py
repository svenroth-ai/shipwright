"""Pure logic for churn-artifact merge reconciliation (no git / no IO).

Split out of ``tools/resolve_churn_conflicts.py`` so the allowlist + the
classify / dedup / validate rules are unit-testable in isolation and the tool
stays under the 300-LOC source guideline. See
``.shipwright/planning/iterate/2026-05-31-churn-merge-resolver.md``.
"""

from __future__ import annotations

import json

# --- the churn allowlist (POSIX relpaths) -----------------------------------

COMPLIANCE_MDS: frozenset[str] = frozenset(
    f".shipwright/compliance/{name}.md"
    for name in ("dashboard", "sbom", "test-evidence", "traceability-matrix", "change-history")
)
AGENT_DOC_MDS: frozenset[str] = frozenset(
    f".shipwright/agent_docs/{name}.md"
    for name in ("build_dashboard", "session_handoff", "triage_inbox")
)
DERIVED_MDS: frozenset[str] = COMPLIANCE_MDS | AGENT_DOC_MDS

EVENTS_LOG = "shipwright_events.jsonl"
TEST_RESULTS = "shipwright_test_results.json"
#: The triage backlog — an append-only JSONL log tracked since campaign
#: 2026-06-05-track-triage-jsonl (C). Reconciled like ``EVENTS_LOG`` but with
#: a triage-specific dedup (no id-collision warning — see
#: :func:`dedup_triage_lines`).
TRIAGE_LOG = ".shipwright/triage.jsonl"

#: Everything the resolver may auto-resolve. A conflict outside this set aborts.
#: NOTE: ``.shipwright/agent_docs/architecture.md`` is intentionally absent
#: (curated prose — must reach a human; folds external-review G4/O1).
CHURN_ALLOWLIST: frozenset[str] = DERIVED_MDS | {EVENTS_LOG, TEST_RESULTS, TRIAGE_LOG}


def norm(rel: str) -> str:
    """Normalise a git path to forward-slash POSIX form."""
    return rel.strip().replace("\\", "/")


def classify(conflicted: object) -> tuple[list[str], list[str]]:
    """Split conflicted paths into ``(resolvable, blocking)``.

    ``resolvable`` ⊆ :data:`CHURN_ALLOWLIST`; ``blocking`` is everything else
    (real source). Both lists are normalised + de-duplicated + sorted. The
    pre-flight gate aborts whenever ``blocking`` is non-empty (AC-3).
    """
    resolvable: list[str] = []
    blocking: list[str] = []
    for raw in conflicted:  # type: ignore[union-attr]
        rel = norm(str(raw))
        if not rel:
            continue
        (resolvable if rel in CHURN_ALLOWLIST else blocking).append(rel)
    return sorted(set(resolvable)), sorted(set(blocking))


def dedup_event_lines(lines: list[str]) -> tuple[list[str], list[str]]:
    """Exact-line dedup preserving first-seen order (never drops a *distinct*
    line). Returns ``(deduped, warnings)``; a warning is emitted — never a drop —
    when two *distinct* lines share an ``evt`` ``id`` (32-bit ids can collide;
    folds external-review G2/O6).
    """
    seen_lines: set[str] = set()
    id_to_line: dict[str, str] = {}
    out: list[str] = []
    warnings: list[str] = []
    for line in lines:
        if not line.strip():
            continue
        if line in seen_lines:
            continue
        seen_lines.add(line)
        out.append(line)
        try:
            ev_id = json.loads(line).get("id")
        except (json.JSONDecodeError, AttributeError):
            ev_id = None
        if ev_id:
            if ev_id in id_to_line and id_to_line[ev_id] != line:
                warnings.append(
                    f"evt id {ev_id!r} shared by two DISTINCT event lines "
                    "(kept both — verify no real duplication)"
                )
            id_to_line.setdefault(ev_id, line)
    return out, warnings


def dedup_triage_lines(lines: list[str]) -> tuple[list[str], list[str]]:
    """Exact-line dedup for the triage log, preserving first-seen order.

    Returns ``(deduped, warnings)`` for interface parity with
    :func:`dedup_event_lines`, but ``warnings`` is **always empty**: triage
    ``append`` and ``status`` events INTENTIONALLY share an item ``id`` (the
    status event flips the status of an existing item), so the event-log
    "distinct lines share an id → warn" heuristic would false-fire on every
    item that was ever promoted / dismissed. Only byte-identical duplicate
    lines (the same event recorded on both merge sides) are dropped.
    """
    seen: set[str] = set()
    out: list[str] = []
    for line in lines:
        if not line.strip() or line in seen:
            continue
        seen.add(line)
        out.append(line)
    return out, []


def validate_triage_text(text: str) -> list[str]:
    """Return a list of error strings (empty = valid) for the triage log.

    Checks: (a) the first non-blank line is the ``{"schema":"triage",...}``
    header; (b) every non-blank line parses as JSON; (c) no duplicate ``append``
    for one id; (d) no ``status`` event without a preceding ``append`` (the
    reader silently DROPS such orphans — ``triage.read_all_items`` skips a
    status for an unknown id — so a merge that lost an append would otherwise
    pass validation while silently dropping triage state). Parallel to
    :func:`validate_events_text` but triage-specific.
    """
    errors: list[str] = []
    header_seen = False
    append_ids: set[str] = set()
    status_ids: list[tuple[int, str]] = []
    for n, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append(
                f"line {n}: not valid JSON ({exc.msg}) — union may have corrupted a historic line"
            )
            continue
        if not header_seen:
            header_seen = True
            if not (isinstance(obj, dict) and obj.get("schema") == "triage" and "v" in obj):
                errors.append(
                    f"line {n}: first non-blank line is not the triage header "
                    '({"v":...,"schema":"triage",...}) — the merge reordered or dropped it'
                )
            continue
        if not isinstance(obj, dict):
            continue
        event, iid = obj.get("event"), obj.get("id")
        if event == "append":
            if iid in append_ids:
                errors.append(f"line {n}: duplicate append for id {iid!r} — the merge double-counted an item")
            append_ids.add(iid)
        elif event == "status":
            status_ids.append((n, iid))
    # Second pass: status ids are checked against the FULL append set, NOT only
    # appends seen earlier in file order — ``merge=union`` may legitimately
    # interleave lines so a status precedes its append while both are present
    # (order-sensitive validation would false-fail `triage_invalid`). Only a
    # status whose append is absent ANYWHERE is a real merge drop.
    for n, iid in status_ids:
        if iid not in append_ids:
            errors.append(f"line {n}: status for id {iid!r} has no append anywhere — the merge dropped it")
    if not header_seen:
        errors.append("triage log is empty after merge — the header was dropped")
    return errors


def validate_events_text(text: str, *, require_run_id: str | None = None) -> list[str]:
    """Return a list of error strings (empty = valid).

    Checks: (a) every non-blank line parses as JSON; (b) if ``require_run_id``
    is given, a ``work_completed`` event whose ``adr_id`` == that run id exists
    (so F11 ``check_events_has_commit`` stays green). Folds G5/O4/O5.
    """
    errors: list[str] = []
    run_id_seen = False
    for n, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append(
                f"line {n}: not valid JSON ({exc.msg}) — union may have corrupted a historic line"
            )
            continue
        if (
            require_run_id
            and isinstance(obj, dict)
            and obj.get("type") == "work_completed"
            and obj.get("adr_id") == require_run_id
        ):
            run_id_seen = True
    if require_run_id and not run_id_seen:
        errors.append(
            f"this run's work_completed event (adr_id={require_run_id}) is absent — "
            "the merge dropped it; F11 would fail"
        )
    return errors
