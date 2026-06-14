"""Phase-Quality triage → one rolling backlog action-unit.

Replaces the prior 1-FAIL-1-item finding-mirror emit with a single rolling
``phaseQuality:backlog:<sig>`` action-unit (memory
``project_triage_launch_surface_redesign`` / ADR-057: producers emit
action-units, not finding-mirrors). Concerns: Layer 1
:func:`phase_is_engaged` (applicability gate, FAIL-OPEN),
:func:`collect_in_scope_fails` (latest finding per phase → Tier-1 FAILs,
filtered), Layer 3 :func:`emit_phase_quality_backlog` (dismiss-stale +
idempotent append / auto-dismiss when empty). See the iterate spec
``2026-05-31-phasequality-triage-bundle`` for the no-leader-election
concurrency rationale (atomic finding writes + deterministic ``<sig>`` +
triage ``_FileLock`` + idempotent ops → converges to one open item).
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

_SCRIPTS_ROOT = Path(__file__).resolve().parents[2]
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from lib.events_log import resolve_events_path  # noqa: E402

from ._aggregates import load_actionable_findings  # noqa: E402
from ._constants import CATEGORIES, DASHBOARD_PATH, STATUS_FAIL  # noqa: E402

BACKLOG_PREFIX = "phaseQuality:backlog:"
# "Live view:" pointer baked into triage detail/launchPayload. Follow the SSoT
# constant so it tracks the FINDING_DIR relocation (iterate-2026-06-09).
DASHBOARD_REL = DASHBOARD_PATH


# ---------------------------------------------------------------------------
# Layer 1 — phase-applicability gate
# ---------------------------------------------------------------------------

def load_engagement_inputs(project_root: Path) -> tuple[dict | None, list[dict]]:
    """Read run-config + event log for the engagement predicate (FAIL-OPEN).

    Returns ``(cfg, events)``. ``cfg`` is ``None`` when
    ``shipwright_run_config.json`` is missing or malformed — callers MUST
    treat ``cfg is None`` as "cannot determine engagement → engaged" so a
    read error never silently suppresses alerts (AC-1b).
    """
    cfg: dict | None = None
    cfg_path = project_root / "shipwright_run_config.json"
    if cfg_path.exists():
        try:
            data = json.loads(cfg_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                cfg = data
        except (json.JSONDecodeError, OSError):
            cfg = None

    events: list[dict] = []
    ev_path = resolve_events_path(project_root)  # SSOT accessor (worktree-aware)
    if ev_path.exists():
        try:
            for raw in ev_path.read_text(encoding="utf-8", errors="ignore").splitlines():
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    obj = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if isinstance(obj, dict):
                    events.append(obj)
        except OSError:
            events = []
    return cfg, events


def phase_is_engaged(phase: str, cfg: dict | None, events: list[dict]) -> bool:
    """Whether ``phase`` is part of THIS project's active lifecycle.

    Engaged iff ANY of:

    * a ``phase_completed`` event, or a ``work_completed`` event with
      ``source == phase``, exists in the event log; OR
    * ``cfg.status == "complete"`` AND ``phase == "iterate"`` (iterate is the
      always-on maintenance phase of a finished project); OR
    * ``cfg.status != "complete"`` AND (``phase ∈ completed_steps`` OR
      ``phase == current_step``).

    ``current_step`` / ``completed_steps`` grant engagement ONLY while the
    project is in progress, so a *stale* ``current_step`` on a completed run
    cannot re-admit a phase (AC-2). FAIL-OPEN: ``cfg is None`` → engaged.
    Status casing is normalized.
    """
    if cfg is None:
        return True  # AC-1b — cannot determine → never suppress

    for e in events or []:
        if not isinstance(e, dict):
            continue
        etype = e.get("type")
        if etype == "phase_completed" and (e.get("source") == phase or e.get("phase") == phase):
            return True
        if etype == "work_completed" and e.get("source") == phase:
            return True

    status = str(cfg.get("status") or "").strip().lower()
    if phase == "iterate" and status == "complete":
        return True
    if status != "complete":
        completed = cfg.get("completed_steps")
        if isinstance(completed, list) and phase in completed:
            return True
        if phase == cfg.get("current_step"):
            return True
    return False


# --- Collect in-scope Tier-1 FAILs (latest finding per phase, filtered) ---

def collect_in_scope_fails(project_root: Path) -> list[dict[str, str]]:
    """Return the open in-scope Tier-1 FAILs across all phases.

    Reads the latest finding per phase via ``load_actionable_findings`` (sorted
    newest-first; degenerate sentinel-run snapshots already excluded), enumerates
    every Tier-1 FAIL across all categories in it (so e.g. design's ``C1`` AND
    ``D1`` both surface), and drops findings whose phase is not engaged (Layer 1).
    Output is sorted by ``(phase, code)`` for a stable signature.
    """
    cfg, events = load_engagement_inputs(project_root)
    seen_phase: set[str] = set()
    out: list[dict[str, str]] = []
    for lf in load_actionable_findings(project_root):
        # source="error" = crashed hook-level audit (empty categories) — skip
        # so it can't mask a real prior FAIL as the latest-per-phase finding.
        if lf.source == "error" or lf.phase in seen_phase:
            continue
        seen_phase.add(lf.phase)
        if not phase_is_engaged(lf.phase, cfg, events):
            continue
        for category in CATEGORIES:
            for f in lf.payload.get(category, []) or []:
                if not isinstance(f, dict) or f.get("status") != STATUS_FAIL:
                    continue
                # Skip Tier-2 (heuristic) and provenance="error" (synthetic
                # category-runner-crash FAIL) — neither is actionable.
                if f.get("tier") == 2 or f.get("provenance") == "error":
                    continue
                code = str(f.get("id") or category)
                out.append({
                    "phase": lf.phase,
                    "code": code,
                    "name": str(f.get("name") or code),
                    "remediation": str(f.get("remediation") or ""),
                })
    out.sort(key=lambda d: (d["phase"], d["code"]))
    return out


# --- Layer 3 — single rolling backlog action-unit ---

def _signature(fails: list[dict[str, str]]) -> str:
    """Stable sha256[:12] of the sorted ``phase:code`` set (the body is a
    pure function of this set, so the signature fully captures the rendered
    body — it can never go stale behind the dedup; AC-16)."""
    key = "\n".join(f"{d['phase']}:{d['code']}" for d in fails)
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:12]


def _phases(fails: list[dict[str, str]]) -> list[str]:
    return sorted({d["phase"] for d in fails})


def _build_title(fails: list[dict[str, str]]) -> str:
    n, m = len(fails), len(_phases(fails))
    return (f"Phase-quality: {n} open Tier-1 FAIL(s) across {m} phase(s)")[:160]


def _build_detail(fails: list[dict[str, str]]) -> str:
    lines = [
        f"{len(fails)} open phase-quality Tier-1 FAIL(s) across "
        f"{len(_phases(fails))} phase(s): {', '.join(_phases(fails))}.",
        "",
    ]
    for d in fails:
        rem = f" — {d['remediation']}" if d["remediation"] else ""
        lines.append(f"- {d['phase']}:{d['code']} ({d['name']}){rem}")
    lines += ["", f"Live view: {DASHBOARD_REL}"]
    return "\n".join(lines)


def _build_launch_payload(fails: list[dict[str, str]]) -> str:
    codes = ", ".join(f"{d['phase']}:{d['code']}" for d in fails)
    return (
        "/shipwright-compliance\n\n"
        f"Context: {len(fails)} open phase-quality Tier-1 FAIL(s): {codes}.\n"
        f"Dashboard: {DASHBOARD_REL}\n"
        "Each FAIL + remediation is listed in this item's detail."
    )


def emit_phase_quality_backlog(
    project_root: Path,
    *,
    run_id: str | None,
    commit: str | None,
) -> dict[str, int]:
    """Emit/refresh the single rolling phase-quality backlog action-unit.

    * No in-scope FAILs → dismiss every open ``phaseQuality:backlog:*`` item
      (``reason="phaseQualityResolved"``); append nothing.
    * Else → dismiss open backlog items whose signature differs from the
      current set (``reason="phaseQualityRefreshed"``) and append the current
      one (idempotent; an open same-signature item suppresses the append).

    Best-effort: returns ``{"appended", "dismissed", "open_fails"}``; all
    errors are swallowed so the Stop hook stays non-blocking.
    """
    try:
        from triage import (  # noqa: PLC0415
            append_triage_item_idempotent,
            mark_status,
            read_all_items,
            should_route_to_outbox,
        )
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(
            f"[phase-quality] backlog triage import failed: "
            f"{type(exc).__name__}: {exc}\n"
        )
        return {"appended": 0, "dismissed": 0, "open_fails": 0}

    # D1 (2026-06-08-triage-outbox-delivery, review cascade): Stop hook is a
    # genuine idle-main background appender — route its append to the outbox on
    # idle main WITH origin; iterate/* + no-origin route False → tracked. The
    # dismiss-pass mark_status is residence-derived (no flag needed).
    to_outbox = should_route_to_outbox(project_root)

    fails = collect_in_scope_fails(project_root)

    try:
        open_backlog = [
            it for it in read_all_items(project_root)
            if it.get("source") == "phaseQuality"
            and it.get("status") == "triage"
            and str(it.get("dedupKey") or "").startswith(BACKLOG_PREFIX)
        ]
    except Exception:  # noqa: BLE001
        open_backlog = []

    def _dismiss(item_id: str, reason: str) -> int:
        try:
            mark_status(
                project_root, item_id, new_status="dismissed",
                by="phaseQualityBacklog", reason=reason,
            )
            return 1
        except Exception:  # noqa: BLE001
            return 0

    if not fails:
        dismissed = sum(_dismiss(it["id"], "phaseQualityResolved") for it in open_backlog)
        return {"appended": 0, "dismissed": dismissed, "open_fails": 0}

    cur_key = BACKLOG_PREFIX + _signature(fails)
    dismissed = sum(
        _dismiss(it["id"], "phaseQualityRefreshed")
        for it in open_backlog if it.get("dedupKey") != cur_key
    )

    new_id: str | None = None
    try:
        new_id = append_triage_item_idempotent(
            project_root,
            source="phaseQuality",
            severity="high",
            kind="bug",
            title=_build_title(fails),
            detail=_build_detail(fails),
            dedup_key=cur_key,
            run_id=run_id,
            commit=commit,
            match_commit=False,
            window_seconds=None,
            launch_payload=_build_launch_payload(fails),
            to_outbox=to_outbox,
        )
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(
            f"[phase-quality] backlog emit failed: {type(exc).__name__}: {exc}\n"
        )

    return {
        "appended": 1 if new_id else 0,
        "dismissed": dismissed,
        "open_fails": len(fails),
    }


__all__ = [
    "BACKLOG_PREFIX",
    "DASHBOARD_REL",
    "collect_in_scope_fails",
    "emit_phase_quality_backlog",
    "load_engagement_inputs",
    "phase_is_engaged",
]
