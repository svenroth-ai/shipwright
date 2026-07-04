"""authoritative — grade a target from its OWN ``.shipwright/`` records (G4).

When routing detects a healthy ``.shipwright/`` event log + RTM (plan §4 C-R4),
the honest grade is the one Shipwright itself would compute — not a heuristic
projection from git history. :func:`try_authoritative_grade` reuses the compliance
adapter (``collect_all`` → ``build_grade_inputs``) and the **same** ``compute_grade``
engine the dashboard uses, so an authoritative grader-grade equals the dashboard
grade by construction.

Fail-safe by design: **any** failure — the adapter is unavailable, ``collect_all``
raises on a corrupt/partial log, or the collected data carries no gradeable
records (an empty/stale ``.shipwright/`` that merely looked structurally valid) —
returns ``None`` so the caller falls back to the labelled heuristic path. It never
raises and never grades authoritatively off degenerate data.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any

from engine_bridge import Engine
from report_model import ReportModel, build_report_model
from repo_context import RepoContext
from reuse_bridge import load_compliance_ingest
from routing import RoutingDecision

_MODE_AUTHORITATIVE = "authoritative"

# Authoritative ingestion routes the TARGET's event log into the cross-plugin
# compliance ``collect_all`` reader, which was written for a TRUSTED, self-owned
# ``.shipwright/`` and reads the event log unbounded. A hostile CLONE could ship a
# giant ``shipwright_events.jsonl`` to amplify it into multi-GB of Python objects
# (OOM). We refuse the authoritative path above this size and fall back to the
# heuristic projection (whose reads are byte-bounded). A real Shipwright log is a
# few hundred KB per year of history, so 10 MB is a generous ceiling.
_MAX_AUTHORITATIVE_EVENTLOG_BYTES = 10_000_000

# Per-dimension authoritative provenance sources (replace the heuristic
# "deferred to G2" placeholders in report_model._DIM_META). ``disabled`` is empty:
# in authoritative mode the target's own records are read directly, so a dimension
# is n/a only because the records genuinely carry no such signal — not "dark".
_AUTHORITATIVE_SOURCES: dict[str, str] = {
    "requirement_traceability": "Shipwright RTM + event log (authoritative)",
    "test_health": "Shipwright test-run events (authoritative)",
    "change_traceability": "Shipwright event-log provenance (authoritative)",
    "change_reconciliation": "Shipwright per-FR behaviour reconciliation (authoritative)",
    "security": "Shipwright CI security summary (authoritative)",
    "maintainability": "Shipwright bloat ratchet baseline (authoritative)",
    "dependency_hygiene": "Shipwright SBOM (authoritative)",
}


def _has_gradeable_records(data: Any) -> bool:
    """True when the collected data carries something real to grade.

    A structurally-valid-but-empty/stale ``.shipwright/`` (no work events and no
    declared requirements) is NOT authoritatively gradeable — grading it off the
    engine's all-n/a defaults would misrepresent an empty log as a real posture.
    """
    events = getattr(data, "work_events", None) or []
    requirements = getattr(data, "requirements", None) or []
    return bool(events) or bool(requirements)


def _authoritative_provenance() -> dict[str, dict]:
    return {key: {"source": src, "disabled": ()}
            for key, src in _AUTHORITATIVE_SOURCES.items()}


def _eventlog_over_cap(root: Path) -> bool:
    """True when the target's event log exceeds the authoritative size ceiling."""
    for cand in (root / "shipwright_events.jsonl", root / ".shipwright" / "events.jsonl"):
        try:
            if cand.is_file() and cand.stat().st_size > _MAX_AUTHORITATIVE_EVENTLOG_BYTES:
                return True
        except OSError:  # pragma: no cover - defensive
            continue
    return False


def try_authoritative_grade(
    context: RepoContext, engine: Engine, routing: RoutingDecision,
) -> ReportModel | None:
    """Grade ``context`` from its own ``.shipwright/`` records, or ``None``.

    Returns ``None`` (→ heuristic fallback) on any adapter/collection failure,
    an oversize event log (untrusted-clone OOM guard), or records that carry
    nothing gradeable.
    """
    # Bound the cross-plugin exposure BEFORE handing the log to the unbounded
    # compliance reader — a hostile clone could otherwise OOM the process.
    if _eventlog_over_cap(context.root):
        return None
    try:
        collect_all, build_grade_inputs = load_compliance_ingest()
        data = collect_all(context.root)
        if not _has_gradeable_records(data):
            return None
        inputs = build_grade_inputs(data)
        report = engine.compute_grade(inputs)
        authoritative_routing = dataclasses.replace(
            routing,
            effective_mode=_MODE_AUTHORITATIVE,
            reason="graded from the target's own .shipwright/ records (authoritative)",
        )
        return build_report_model(
            grade_report=report,
            routing=authoritative_routing,
            target_display=context.root.name or "repository",
            head_sha=context.head_sha,
            events_truncated=context.events_truncated,
            features_truncated=context.features_truncated,
            # The engine's dimension details ARE the authoritative signal — no
            # heuristic detail overrides; only the provenance source strings change.
            provenance_overrides=_authoritative_provenance(),
            static_test_inventory="",
            network_enabled=False,
            network_note="authoritative — graded from the target's own .shipwright/ records",
        )
    except Exception:  # noqa: BLE001 — fail safe to the heuristic path on ANY error
        return None
