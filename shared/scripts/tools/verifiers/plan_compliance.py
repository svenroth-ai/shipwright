"""Plan-phase workflow compliance checks (Phase-Quality PR 2).

Implements W5 — ``.shipwright/planning/external_review_state.json`` exists with a
``status=completed`` OR a ``skipped_*`` status carrying a non-empty
``reason`` (no-keys-marker variant), **and** records no reviewer disagreement
that nobody decided. Matches the marker written by
``shared/scripts/checks/mark-review-state.py``.

The verdict on the marker's contents comes from
``lib.review_marker.evaluate_review_state`` — the same function the in-session
Step 6 gate and the ``setup-planning-session`` resume gate call, so the three
readers cannot drift into three different definitions of "reviewed".
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


# Canonical home of the planning artifact set, relative to project_root.
# Mirrors PLANNING_DIR in shared/scripts/lib/artifact_migrations.py.
PLANNING_DIRNAME = ".shipwright/planning"

_SHARED_SCRIPTS = Path(__file__).resolve().parents[2]
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

from lib.phase_quality import (  # noqa: E402
    STATUS_FAIL,
    STATUS_PASS,
    STATUS_WARN,
    make_finding,
)
from lib.review_marker import (  # noqa: E402
    STATE_BLOCK,
    STATE_LEGACY,
    evaluate_review_state,
)


W5_NAME = "W5 plan external review marker"
W5_REMEDIATION = (
    "Run external review via /shipwright-plan Step 5, or document the "
    "skip in external_review_state.json with a reason."
)
W5_CONTRADICTION_REMEDIATION = (
    "Two reviewers disagreed, or a verdict could not be read. Decide it and "
    "record the decision: mark-review-state.py "
    "--contradiction-resolution '<which side you took and why>'."
)
W5_LEGACY_REMEDIATION = (
    "Re-run Step 5b with one --verdict per reviewer so a disagreement between "
    "the two would be noticed. Markers written before verdicts existed are "
    "expected to hit this."
)


def _find_review_state(project_root: Path) -> Path | None:
    candidates = [
        project_root / PLANNING_DIRNAME / "external_review_state.json",
        project_root / "external_review_state.json",
    ]
    planning = project_root / PLANNING_DIRNAME
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
            "no external_review_state.json under .shipwright/planning/",
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
    state, detail = evaluate_review_state(data)
    if state == STATE_BLOCK:
        return make_finding(
            "W5", STATUS_FAIL,
            f"{detail} ({marker.name})",
            name=W5_NAME,
            remediation=(
                W5_CONTRADICTION_REMEDIATION
                if "disagreement" in detail
                else W5_REMEDIATION
            ),
        )
    if state == STATE_LEGACY:
        # The marker may predate per-reviewer verdicts entirely. W5 audits
        # plans of any age, so it says so rather than failing one written
        # before the field existed; the in-session gate, which only ever sees
        # a marker written moments ago, blocks on the same state.
        return make_finding(
            "W5", STATUS_WARN,
            f"{detail} ({marker.name})",
            name=W5_NAME,
            remediation=W5_LEGACY_REMEDIATION,
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
    reason = str(data.get("reason") or "").strip()
    return make_finding(
        "W5", STATUS_PASS,
        f"status={status} with justification: {reason[:80]}",
        name=W5_NAME,
        provenance="marker",
    )


def run(project_root: Path, run_id: str) -> list[dict[str, Any]]:
    del run_id
    return [check_w5_external_review_marker(project_root)]


__all__ = ["check_w5_external_review_marker", "run"]
