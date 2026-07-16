"""Group D — FR coverage detectives (event-log + traceability manifest).

Cross-references ``shipwright_events.jsonl`` (and, for D-orphan/D-layer, the TT1
test-traceability manifest) against the project's spec table FRs (via
``drift_parsers.collect_requirements_from_planning``). All checks are detective-only.

- D1 — Spec FR uncovered. Needs a *tested* event (tests.total>0) naming it AND, for an
  explicit/post-rollout FR, a real manifest test link (TT2 hardening, two SEPARATE proofs
  — an untested 0/0 commit or a missing link no longer marks it covered; §2 false-green).
  Severity priority-driven: Must=HIGH, Should=MEDIUM, May=LOW.
- D2 — Stale FR reference: ``affected_frs`` FR-IDs not in the current spec. MEDIUM.
- D3 — Promised FR (``new_frs``) never reaffirmed via ``affected_frs``. MEDIUM.
- D4 — Latest covering event has ``tests.passed < tests.total``. LOW.
- D5 — FEATURE/CHANGE iterate event with no FR linkage and no ``spec_impact=none``. MEDIUM.
- D-orphan / D-layer — manifest-driven (see ``_group_d_traceability``): a test tagged with
  a removed/absent FR; an active FR missing an executed-passing test at a required layer.

**Epoch floor (D2 only):** the most recent ``spec_updated`` event is a watermark.
D1 dropped it (BP-1, all-time coverage); D3/D4 are time-invariant.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from scripts.audit import _group_d_traceability as _traceability
from scripts.audit.audit_adapters import (
    SOURCE_DETECTIVE_ONLY,
    Finding,
    load_shared_lib,
)

# Pollution-free import — see group_a.py for the rationale. Loads
# ``shared/scripts/lib/drift_parsers.py`` under a sentinel module name
# without touching the ``lib`` namespace.
drift_parsers = load_shared_lib("drift_parsers")
events_amend = load_shared_lib("events_amend")  # honor event_amended corrections
fr_classification = load_shared_lib("fr_classification")  # D5↔write-gate SSOT parity


# ---------------------------------------------------------------------------
# Suggested-iterate hint
# ---------------------------------------------------------------------------

def _suggest(check_id: str, label: str) -> str:
    return (
        f"/shipwright-iterate --type change "
        f"\"reconcile {check_id} ({label}) "
        f"— see .shipwright/compliance/audit-report.md\""
    )


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------


def _load_events(project_root: Path) -> list[dict] | None:
    """Read ``shipwright_events.jsonl`` line by line. Return ``None`` when
    the file is absent. Malformed lines are skipped (event log is append-
    only and the audit must not crash on a single bad row)."""
    path = project_root / "shipwright_events.jsonl"
    if not path.exists():
        return None
    out: list[dict] = []
    try:
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    except OSError:
        return None
    return out


def _load_spec_frs(project_root: Path) -> list[drift_parsers.FunctionalRequirement]:
    return drift_parsers.collect_requirements_from_planning(project_root)


# ---------------------------------------------------------------------------
# Epoch floor
# ---------------------------------------------------------------------------


def _watermark_ts(events: Iterable[dict]) -> str | None:
    """Return the highest ``ts`` of any event that carries a non-empty
    ``spec_updated`` field, or ``None`` when no such event exists.

    Comparison is done as plain ISO-8601 strings — the timestamps record_event
    writes are always ``isoformat()`` UTC, so lexical comparison agrees with
    chronological comparison. Tolerant of missing/empty values."""
    best: str | None = None
    for ev in events:
        if not ev.get("spec_updated"):
            continue
        ts = ev.get("ts")
        if not isinstance(ts, str):
            continue
        if best is None or ts > best:
            best = ts
    return best


def _filter_after_watermark(events: list[dict], watermark: str | None) -> list[dict]:
    if watermark is None:
        return events
    return [ev for ev in events if isinstance(ev.get("ts"), str) and ev["ts"] > watermark]


# ---------------------------------------------------------------------------
# D1 — Spec FR uncovered
# ---------------------------------------------------------------------------


_PRIORITY_TO_SEVERITY = {"Must": "HIGH", "Should": "MEDIUM", "May": "LOW"}


def _check_d1(
    spec_frs: list[drift_parsers.FunctionalRequirement],
    events: list[dict] | None,
    project_root: Path,
) -> tuple[str, str, str, list[str]]:
    """Returns (status, severity, detail, evidence)."""
    if not spec_frs:
        return "skip", "LOW", "no FR table rows in any spec.md", []
    if events is None:
        return "skip", "LOW", "shipwright_events.jsonl not present", []

    work_completed = [ev for ev in events if ev.get("type") == "work_completed"]
    if not work_completed:
        return "skip", "LOW", "no work_completed events recorded", []

    # TT2 hardening (Spec §5 — two SEPARATE proofs, never joined into one false-green):
    # (1) event proof — only a *tested* event (tests.total>0) counts; a 0/0 docs/refactor
    # commit no longer marks an FR covered (§2). (2) link proof — an explicit/post-rollout
    # FR ALSO needs a real manifest test link (refine_d1_covered), provenance-gated (§9).
    covered: set[str] = set()
    for ev in work_completed:
        tests = ev.get("tests") or {}
        if not (isinstance(tests.get("total"), int) and tests["total"] > 0):
            continue
        for fr in ev.get("affected_frs", []) or []:
            if isinstance(fr, str):
                covered.add(fr)
    covered, _d1_note = _traceability.refine_d1_covered(covered, project_root)

    uncovered = [fr for fr in spec_frs if fr.id not in covered]
    if not uncovered:
        return "pass", "LOW", "every spec FR has a covering event" + _d1_note, []

    # Severity = highest priority among uncovered FRs.
    severities = {_PRIORITY_TO_SEVERITY.get(fr.priority, "LOW") for fr in uncovered}
    severity = "HIGH" if "HIGH" in severities else (
        "MEDIUM" if "MEDIUM" in severities else "LOW"
    )

    by_priority = {"Must": [], "Should": [], "May": []}
    for fr in uncovered:
        by_priority.setdefault(fr.priority, []).append(fr.id)
    parts: list[str] = []
    for prio in ("Must", "Should", "May"):
        ids = by_priority.get(prio, [])
        if not ids:
            continue
        head = ", ".join(ids[:3])
        if len(ids) > 3:
            head += f", … (+{len(ids) - 3})"
        parts.append(f"{prio}: {head}")
    detail = "uncovered FRs — " + "; ".join(parts) + _d1_note
    evidence = [f"{fr.id} ({fr.priority}, in {fr.spec_path})" for fr in uncovered]
    return "fail", severity, detail, evidence


# ---------------------------------------------------------------------------
# D2 — Stale FR references in events
# ---------------------------------------------------------------------------


def _check_d2(
    spec_frs: list[drift_parsers.FunctionalRequirement],
    events: list[dict] | None,
) -> tuple[str, str, str, list[str]]:
    if not spec_frs:
        return "skip", "MEDIUM", "no FR table rows in any spec.md", []
    if events is None:
        return "skip", "MEDIUM", "shipwright_events.jsonl not present", []

    spec_ids = {fr.id for fr in spec_frs}

    watermark = _watermark_ts(events)
    in_window = _filter_after_watermark(events, watermark)

    # D2 scans every event with an ``affected_frs`` field, regardless of
    # event type. Some non-work_completed event types (task_created,
    # event_amended) can also carry FR references — a stale FR-ID on
    # those is just as much a drift signal as on a work_completed event.
    stale: dict[str, int] = {}
    for ev in in_window:
        for fr in ev.get("affected_frs", []) or []:
            if not isinstance(fr, str) or fr in spec_ids:
                continue
            stale[fr] = stale.get(fr, 0) + 1

    if not stale:
        return "pass", "MEDIUM", "every event FR-ref exists in the current spec", []

    items = sorted(stale.items(), key=lambda kv: (-kv[1], kv[0]))
    head = ", ".join(f"{k} (×{v})" for k, v in items[:3])
    if len(items) > 3:
        head += f", … (+{len(items) - 3})"
    detail = f"events reference FR-IDs not in current spec — {head}"
    evidence = [f"{k}: {v} event(s)" for k, v in items]
    return "fail", "MEDIUM", detail, evidence


# ---------------------------------------------------------------------------
# D3 — Promised FRs (new_frs) never delivered
# ---------------------------------------------------------------------------


def _check_d3(
    events: list[dict] | None,
) -> tuple[str, str, str, list[str]]:
    if events is None:
        return "skip", "MEDIUM", "shipwright_events.jsonl not present", []

    promised: dict[str, str] = {}  # fr_id -> earliest ts where it appeared in new_frs
    delivered_after: dict[str, list[str]] = {}  # fr_id -> ts list of affected_frs hits

    for ev in events:
        if ev.get("type") != "work_completed":
            continue
        ts = ev.get("ts")
        if not isinstance(ts, str):
            continue
        for fr in ev.get("new_frs", []) or []:
            if not isinstance(fr, str):
                continue
            if fr not in promised or ts < promised[fr]:
                promised[fr] = ts
        for fr in ev.get("affected_frs", []) or []:
            if not isinstance(fr, str):
                continue
            delivered_after.setdefault(fr, []).append(ts)

    if not promised:
        return "skip", "MEDIUM", "no events introduced FRs via new_frs", []

    pending: list[str] = []
    for fr_id, promised_ts in promised.items():
        delivered_ts_list = delivered_after.get(fr_id, [])
        # ``>=`` (not ``>``): an FR present in both ``new_frs`` and
        # ``affected_frs`` of the SAME event (ts == promised_ts) — the normal
        # single-iterate "introduce + deliver" case — counts as delivered.
        # Strictly-later was the FR-01.33 webui false-positive: a same-event
        # delivery stayed "pending" forever until some unrelated later event
        # happened to touch the FR (iterate-2026-06-05-fr-linkage-lifecycle).
        if any(ts >= promised_ts for ts in delivered_ts_list):
            continue
        pending.append(fr_id)

    if not pending:
        return "pass", "MEDIUM", "every promised FR has a follow-up affected_frs event", []

    pending.sort()
    head = ", ".join(pending[:5])
    if len(pending) > 5:
        head += f", … (+{len(pending) - 5})"
    detail = f"FRs introduced via new_frs but never reaffirmed — {head}"
    evidence = [f"{fr_id}: promised on {promised[fr_id]}" for fr_id in pending]
    return "fail", "MEDIUM", detail, evidence


# ---------------------------------------------------------------------------
# D4 — Latest covering event has failing tests
# ---------------------------------------------------------------------------


def _check_d4(
    spec_frs: list[drift_parsers.FunctionalRequirement],
    events: list[dict] | None,
) -> tuple[str, str, str, list[str]]:
    """Check that each spec FR's latest covering event has tests.passed >= total.

    Design choice: only ``work_completed`` events are considered as
    "covering" (the test_run / phase_completed event types don't carry
    ``affected_frs`` in their canonical schema). Events lacking a
    parseable ``tests`` dict are skipped silently — most work_completed
    events legitimately omit the field (planning-phase commits, doc-only
    iterates, infra refactors). Flagging every test-less event as
    failing would generate noise that drowns out the real signal.
    Operators wanting strict enforcement can enable Group F or wire a
    follow-up rule once tests are mandatory across the event log.
    """
    if not spec_frs:
        return "skip", "LOW", "no FR table rows in any spec.md", []
    if events is None:
        return "skip", "LOW", "shipwright_events.jsonl not present", []

    spec_ids = {fr.id for fr in spec_frs}
    latest_event_for: dict[str, dict] = {}
    for ev in events:
        if ev.get("type") != "work_completed":
            continue
        ts = ev.get("ts")
        if not isinstance(ts, str):
            continue
        for fr in ev.get("affected_frs", []) or []:
            if not isinstance(fr, str) or fr not in spec_ids:
                continue
            current = latest_event_for.get(fr)
            if current is None or current.get("ts", "") < ts:
                latest_event_for[fr] = ev

    if not latest_event_for:
        return "skip", "LOW", "no FR has a covering event yet", []

    failing: list[tuple[str, int, int]] = []
    for fr_id, ev in latest_event_for.items():
        tests = ev.get("tests")
        if not isinstance(tests, dict):
            continue
        passed = tests.get("passed")
        total = tests.get("total")
        if not isinstance(passed, int) or not isinstance(total, int):
            continue
        if passed < total:
            failing.append((fr_id, passed, total))

    if not failing:
        return "pass", "LOW", "every covered FR's latest event passed its tests", []

    failing.sort()
    head = ", ".join(f"{fr_id} ({p}/{t})" for fr_id, p, t in failing[:3])
    if len(failing) > 3:
        head += f", … (+{len(failing) - 3})"
    detail = f"FRs last touched in failing builds — {head}"
    evidence = [f"{fr_id}: {p}/{t} passed" for fr_id, p, t in failing]
    return "fail", "LOW", detail, evidence


# ---------------------------------------------------------------------------
# D5 — FEATURE/CHANGE iterate event with no FR linkage (inverse drift)
# ---------------------------------------------------------------------------


def _check_d5(
    events: list[dict] | None,
) -> tuple[str, str, str, list[str]]:
    """(status, severity, detail, evidence). Inverse of D1: flags FEATURE/CHANGE
    iterate ``work_completed`` events touching no FR. Exempt when
    ``spec_impact=none`` OR an exempt ``change_type`` + ``none_reason``
    (record_event ADR-C.1 parity). BUG/build out of scope; time-invariant.
    """
    if events is None:
        return "skip", "MEDIUM", "shipwright_events.jsonl not present", []

    iterate_changes = [
        ev for ev in events
        if ev.get("type") == "work_completed"
        and ev.get("source") == "iterate"
        and str(ev.get("intent", "")).lower() in ("feature", "change")
    ]
    if not iterate_changes:
        return "skip", "MEDIUM", "no feature/change iterate events recorded", []

    unlinked: list[dict] = []
    for ev in iterate_changes:
        affected = [f for f in (ev.get("affected_frs") or []) if isinstance(f, str)]
        new = [f for f in (ev.get("new_frs") or []) if isinstance(f, str)]
        if affected or new:
            continue
        if str(ev.get("spec_impact", "")).lower() == "none":
            continue  # explicit, justified no-op
        # Write-gate parity (BP-1): exempt only a *satisfied* no-FR change
        # (behavior-affecting must link an FR — matches the record_event gate).
        if fr_classification.is_satisfied_no_fr(
                ev.get("change_type"), ev.get("none_reason"),
                ev.get("spec_impact")):
            continue
        unlinked.append(ev)

    if not unlinked:
        return "pass", "MEDIUM", "every feature/change iterate event links an FR", []

    def _label(ev: dict) -> str:
        commit = str(ev.get("commit", ""))[:8] or "?"
        desc = str(ev.get("description", "")).strip()
        if len(desc) > 60:
            desc = desc[:57] + "…"
        return f"{ev.get('intent', '?')} {commit}: {desc or '(no description)'}"

    head = "; ".join(_label(ev) for ev in unlinked[:3])
    if len(unlinked) > 3:
        head += f", … (+{len(unlinked) - 3})"
    detail = (
        f"{len(unlinked)} feature/change iterate event(s) with no FR linkage "
        f"and no spec_impact=none — {head}"
    )
    evidence = [_label(ev) for ev in unlinked]
    return "fail", "MEDIUM", detail, evidence


# ---------------------------------------------------------------------------
# Top-level run()
# ---------------------------------------------------------------------------


_NAME_BY_CHECK = {
    "D1": "Spec FR coverage in events",
    "D2": "Event FR-refs exist in spec",
    "D3": "Promised FRs delivered",
    "D4": "Latest covering event passed tests",
    "D5": "Iterate feature/change events link an FR",
}


def run(
    project_root: Path,
    _config: dict[str, Any] | None,
    _data: Any,
) -> list[Finding]:
    """Run D1-D4 and return Findings."""
    spec_frs = _load_spec_frs(project_root)
    events = events_amend.apply_amendments(raw) if (raw := _load_events(project_root)) is not None else None

    plan: list[tuple[str, callable]] = [
        ("D1", lambda: _check_d1(spec_frs, events, project_root)),
        ("D2", lambda: _check_d2(spec_frs, events)),
        ("D3", lambda: _check_d3(events)),
        ("D4", lambda: _check_d4(spec_frs, events)),
        ("D5", lambda: _check_d5(events)),
    ]

    out: list[Finding] = []
    for check_id, fn in plan:
        try:
            status, severity, detail, evidence = fn()
        except Exception as exc:  # noqa: BLE001 — never crash the whole group
            out.append(Finding(
                group="D", check_id=check_id, name=_NAME_BY_CHECK[check_id],
                severity="HIGH", source=SOURCE_DETECTIVE_ONLY,
                status="fail",
                detail=f"check raised {type(exc).__name__}: {exc}",
            ))
            continue
        out.append(Finding(
            group="D", check_id=check_id, name=_NAME_BY_CHECK[check_id],
            severity=severity, source=SOURCE_DETECTIVE_ONLY,
            status=status, detail=detail, evidence=list(evidence),
            suggested_iterate_cmd=(
                _suggest(check_id, _NAME_BY_CHECK[check_id])
                if status == "fail" else None
            ),
        ))
    # D-orphan + D-layer consume the TT1 manifest (self-contained + fail-closed).
    out.extend(_traceability.traceability_findings(project_root))
    return out
