"""Pure rendering/matching helpers for the compliance rolling backlog card.

Split out of `triage_bundle.py` (P2.59, branch-feedback authority) to keep
that module's orchestration logic under the file-size guideline — no
behavior change, no new caller. `triage_bundle.py` is still the only caller.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

BACKLOG_PREFIX = "compliance:backlog:"
DASHBOARD_REL = ".shipwright/compliance/dashboard.md"

SEVERITY_RANK = {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}
# Self-contained (no back-import of audit_detector) so this module loads
# whether audit_detector is imported as a package or via spec_from_file_location.
_SEVERITY_MAP = {
    "CRITICAL": "critical", "HIGH": "high", "MEDIUM": "medium",
    "LOW": "low", "INFO": "info",
}


def normalize_fails(report: Any) -> list[dict[str, str]]:
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


def signature(fails: list[dict[str, str]]) -> str:
    return hashlib.sha256(
        "\n".join(d["key"] for d in fails).encode("utf-8")
    ).hexdigest()[:12]


def max_severity(fails: list[dict[str, str]]) -> str:
    best = "low"
    for d in fails:
        if SEVERITY_RANK.get(d["sev"], 1) > SEVERITY_RANK.get(best, 1):
            best = d["sev"]
    return best


# Matches security_card.py's cap so a large compliance finding set can't blow
# past append_triage_item's shared DETAIL_MAX_LEN (6000) and get silently
# dropped.
_DETAIL_MAX_LEN = 1024


def build_detail(fails: list[dict[str, str]]) -> str:
    lines = [
        f"{len(fails)} open compliance finding(s): "
        + ", ".join(d["key"] for d in fails),
        "",
    ]
    for d in fails:
        extra = f" — {d['detail']}" if d["detail"] else ""
        lines.append(f"- {d['key']}: {d['name']}{extra}")
    lines += ["", f"Live view: {DASHBOARD_REL}"]
    detail = "\n".join(lines)
    if len(detail) > _DETAIL_MAX_LEN:
        detail = detail[: _DETAIL_MAX_LEN - 1] + "…"
    return detail


def protected_by(item: dict[str, Any], groups: frozenset[str]) -> bool:
    """True if a bullet line in the rendered detail names a group in `groups`."""
    return bool(groups) and any(
        line.startswith(f"- {group}/")
        for line in str(item.get("detail") or "").splitlines()
        for group in groups
    )


def mentions_group(item: dict[str, Any], groups: frozenset[str]) -> bool:
    """Word-boundary group match (unlike a substring, won't false-fire in 'SOURCE/...')."""
    if not groups:
        return False
    text = " ".join(str(item.get(f) or "") for f in ("title", "detail", "dedupKey"))
    return any(re.search(rf"\b{re.escape(g)}/", text) for g in groups)


def build_launch_payload(fails: list[dict[str, str]]) -> str:
    keys = ", ".join(d["key"] for d in fails)
    return (
        "/shipwright-compliance\n\n"  # artifact-path-canon: legacy (slash command, not a path)
        f"Context: {len(fails)} open compliance finding(s): {keys}.\n"
        f"Dashboard: {DASHBOARD_REL}\n"
        "Each finding + hint is listed in this item's detail."
    )
