"""Compliance triage → one rolling backlog action-unit.

Replaces the prior per-failing-check mirror (one ``source=compliance`` item per
failing Group A-G check) with a single rolling ``compliance:backlog:<sig>``
action-unit. Per ``project_triage_launch_surface_redesign`` / ADR-057 —
producers emit action-units, not finding-mirrors; mirrors the phaseQuality
backlog shape (``shared/scripts/lib/phase_quality/_triage_bundle.py``).

Kept compliance-local (two callers is not three — Simplicity First); a shared
helper waits for a third producer.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from typing import Any

BACKLOG_PREFIX = "compliance:backlog:"
DASHBOARD_REL = ".shipwright/compliance/dashboard.md"

_SEVERITY_RANK = {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}
# Self-contained (no back-import of audit_detector) so this module loads
# whether audit_detector is imported as a package or via spec_from_file_location.
_SEVERITY_MAP = {
    "CRITICAL": "critical", "HIGH": "high", "MEDIUM": "medium",
    "LOW": "low", "INFO": "info",
}


def _triage_api():
    """(append_idempotent, mark_status, read_all_items) or (None, None, None)."""
    shared_scripts = Path(__file__).resolve().parents[4] / "shared" / "scripts"
    if str(shared_scripts) not in sys.path:
        sys.path.insert(0, str(shared_scripts))
    try:
        from triage import (  # noqa: PLC0415
            append_triage_item_idempotent,
            mark_status,
            read_all_items,
        )
        return append_triage_item_idempotent, mark_status, read_all_items
    except ImportError:
        return None, None, None


def _normalize_fails(report: Any) -> list[dict[str, str]]:
    """Map failing findings → sorted normalized dicts (stable signature input)."""
    out: list[dict[str, str]] = []
    for f in report.findings:
        if f.status != "fail":
            continue
        parts: list[str] = []
        if f.detail:
            parts.append(str(f.detail))
        if f.suggested_iterate_cmd:
            parts.append(f"hint: {f.suggested_iterate_cmd}")
        out.append({
            "key": f"{f.group}/{f.check_id}",
            "name": str(f.name),
            "sev": _SEVERITY_MAP.get((f.severity or "").upper(), "medium"),
            "detail": " | ".join(parts),
        })
    out.sort(key=lambda d: d["key"])
    return out


def _signature(fails: list[dict[str, str]]) -> str:
    return hashlib.sha256(
        "\n".join(d["key"] for d in fails).encode("utf-8")
    ).hexdigest()[:12]


def _max_severity(fails: list[dict[str, str]]) -> str:
    best = "low"
    for d in fails:
        if _SEVERITY_RANK.get(d["sev"], 1) > _SEVERITY_RANK.get(best, 1):
            best = d["sev"]
    return best


def _build_detail(fails: list[dict[str, str]]) -> str:
    lines = [
        f"{len(fails)} open compliance finding(s): "
        + ", ".join(d["key"] for d in fails),
        "",
    ]
    for d in fails:
        extra = f" — {d['detail']}" if d["detail"] else ""
        lines.append(f"- {d['key']}: {d['name']}{extra}")
    lines += ["", f"Live view: {DASHBOARD_REL}"]
    return "\n".join(lines)


def _build_launch_payload(fails: list[dict[str, str]]) -> str:
    keys = ", ".join(d["key"] for d in fails)
    return (
        "/shipwright-compliance\n\n"
        f"Context: {len(fails)} open compliance finding(s): {keys}.\n"
        f"Dashboard: {DASHBOARD_REL}\n"
        "Each finding + hint is listed in this item's detail."
    )


def emit_compliance_backlog(
    project_root: Path,
    report: Any,
    *,
    run_id: str | None,
    commit: str | None,
) -> dict[str, int]:
    """Emit/refresh ONE ``compliance:backlog:<sig>`` item + retire legacy items.

    * No failing findings → dismiss every open ``compliance:backlog:*``
      (``complianceResolved``) and append nothing.
    * Else → dismiss stale-signature backlog items (``complianceRefreshed``) +
      append the current one (idempotent).
    * One-shot: any open legacy per-check ``compliance`` item (dedupKey not in
      the backlog shape) is dismissed (``supersededByBacklog``) — AC-4.

    Best-effort: returns ``{"appended","dismissed","open_fails"}``.
    """
    append_idempotent, mark_status_fn, read_all_items = _triage_api()
    if append_idempotent is None:
        return {"appended": 0, "dismissed": 0, "open_fails": 0}

    fails = _normalize_fails(report)

    try:
        open_compliance = [
            it for it in read_all_items(project_root)
            if it.get("source") == "compliance" and it.get("status") == "triage"
        ]
    except Exception:  # noqa: BLE001
        open_compliance = []
    open_backlog = [
        it for it in open_compliance
        if str(it.get("dedupKey") or "").startswith(BACKLOG_PREFIX)
    ]
    legacy = [
        it for it in open_compliance
        if not str(it.get("dedupKey") or "").startswith(BACKLOG_PREFIX)
    ]

    def _dismiss(item_id: str, reason: str) -> int:
        try:
            mark_status_fn(
                project_root, item_id, new_status="dismissed",
                by="complianceBacklog", reason=reason,
            )
            return 1
        except Exception:  # noqa: BLE001
            return 0

    # AC-4 — one-shot retirement of the legacy per-check shape.
    dismissed = sum(_dismiss(it["id"], "supersededByBacklog") for it in legacy)

    if not fails:
        dismissed += sum(_dismiss(it["id"], "complianceResolved") for it in open_backlog)
        return {"appended": 0, "dismissed": dismissed, "open_fails": 0}

    cur_key = BACKLOG_PREFIX + _signature(fails)
    dismissed += sum(
        _dismiss(it["id"], "complianceRefreshed")
        for it in open_backlog if it.get("dedupKey") != cur_key
    )

    new_id: str | None = None
    try:
        new_id = append_idempotent(
            project_root,
            source="compliance",
            severity=_max_severity(fails),
            kind="compliance",
            title=f"Compliance: {len(fails)} open finding(s)"[:160],
            detail=_build_detail(fails),
            dedup_key=cur_key,
            run_id=run_id,
            commit=commit,
            match_commit=False,
            window_seconds=None,
            launch_payload=_build_launch_payload(fails),
        )
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(
            f"[audit_detector] backlog emit failed: {type(exc).__name__}: {exc}\n"
        )

    return {
        "appended": 1 if new_id else 0,
        "dismissed": dismissed,
        "open_fails": len(fails),
    }
