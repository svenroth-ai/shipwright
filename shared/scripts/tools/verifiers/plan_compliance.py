"""Plan-phase workflow compliance checks (Phase-Quality PR 2).

Implements W5 — ``planning/external_review_state.json`` exists with a
``status=completed`` OR a ``skipped_*`` status carrying a non-empty
``reason`` (no-keys-marker variant). Matches the marker written by
``shared/scripts/checks/mark-review-state.py``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

_SHARED_SCRIPTS = Path(__file__).resolve().parents[2]
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

from lib.phase_quality import (  # noqa: E402
    STATUS_FAIL,
    STATUS_PASS,
    make_finding,
)


W5_NAME = "W5 plan external review marker"
W5_REMEDIATION = (
    "Run external review via /shipwright-plan Step 5, or document the "
    "skip in external_review_state.json with a reason."
)


def _find_review_state(project_root: Path) -> Path | None:
    candidates = [
        project_root / "planning" / "external_review_state.json",
        project_root / "external_review_state.json",
    ]
    planning = project_root / "planning"
    if planning.is_dir():
        for sub in planning.iterdir():
            if sub.is_dir():
                candidates.append(sub / "external_review_state.json")
    for p in candidates:
        if p.exists():
            return p
    return None


def check_w5_external_review_marker(project_root: Path) -> dict[str, Any]:
    marker = _find_review_state(project_root)
    if marker is None:
        return make_finding(
            "W5", STATUS_FAIL,
            "no external_review_state.json under planning/",
            name=W5_NAME,
            remediation=W5_REMEDIATION,
        )
    try:
        data = json.loads(marker.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return make_finding(
            "W5", STATUS_FAIL,
            f"{marker.name} malformed: {exc}",
            name=W5_NAME,
            remediation=W5_REMEDIATION,
        )
    status = str(data.get("status") or "")
    if status == "completed":
        provider = data.get("provider") or "unknown"
        return make_finding(
            "W5", STATUS_PASS,
            f"status=completed, provider={provider}",
            name=W5_NAME,
            provenance="marker",
        )
    if status.startswith("skipped_"):
        reason = str(data.get("reason") or "").strip()
        if not reason:
            return make_finding(
                "W5", STATUS_FAIL,
                f"status={status} but reason is empty (justification required)",
                name=W5_NAME,
                remediation=W5_REMEDIATION,
            )
        return make_finding(
            "W5", STATUS_PASS,
            f"status={status} with justification: {reason[:80]}",
            name=W5_NAME,
            provenance="marker",
        )
    return make_finding(
        "W5", STATUS_FAIL,
        f"unknown status={status!r} in {marker.name}",
        name=W5_NAME,
        remediation=W5_REMEDIATION,
    )


def run(project_root: Path, run_id: str) -> list[dict[str, Any]]:
    del run_id
    return [check_w5_external_review_marker(project_root)]


__all__ = ["check_w5_external_review_marker", "run"]
