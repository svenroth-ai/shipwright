"""Design-phase workflow compliance checks (Phase-Quality PR 2).

Implements D1 (at least one design artifact exists — Tier-1) and D2
(both ``screens.md`` and ``user-flow.md`` are documented — Tier-2
heuristic, text-only flows are valid).

Plan § 3 deliberately allows text-only flows for D1, so the artifact
gate is satisfied by any of:

- ``.shipwright/designs/mockups/*.html`` (or ``.shipwright/designs/*.html``)
- ``agent_docs/screens.md``
- ``agent_docs/user-flow.md``
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

_SHARED_SCRIPTS = Path(__file__).resolve().parents[2]
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

from lib.phase_quality import (  # noqa: E402
    STATUS_FAIL,
    STATUS_PASS,
    STATUS_WARN,
    make_finding,
)


D1_NAME = "D1 at least one design artifact"
D2_NAME = "D2 screens.md + user-flow.md documented (Tier-2)"

D1_REMEDIATION = (
    "Produce mockups/*.html OR write agent_docs/screens.md OR "
    "agent_docs/user-flow.md before completing the design phase."
)
D2_REMEDIATION = (
    "Document screens in agent_docs/screens.md and flows in "
    "agent_docs/user-flow.md (text-only descriptions are OK)."
)


def _html_mockups_exist(project_root: Path) -> list[Path]:
    roots = [
        project_root / ".shipwright" / "designs" / "mockups",
        project_root / ".shipwright" / "designs",
    ]
    out: list[Path] = []
    for root in roots:
        if root.is_dir():
            out.extend(root.glob("*.html"))
    return out


def check_d1_design_artifact(project_root: Path) -> dict[str, Any]:
    mockups = _html_mockups_exist(project_root)
    screens = project_root / "agent_docs" / "screens.md"
    flow = project_root / "agent_docs" / "user-flow.md"

    evidence_parts: list[str] = []
    if mockups:
        evidence_parts.append(f"{len(mockups)} mockup(s)")
    if screens.exists() and screens.stat().st_size > 0:
        evidence_parts.append("screens.md")
    if flow.exists() and flow.stat().st_size > 0:
        evidence_parts.append("user-flow.md")

    if not evidence_parts:
        return make_finding(
            "D1", STATUS_FAIL,
            "no design artifacts (no mockups/*.html, no screens.md, no user-flow.md)",
            name=D1_NAME,
            remediation=D1_REMEDIATION,
        )
    return make_finding(
        "D1", STATUS_PASS,
        "artifacts present: " + ", ".join(evidence_parts),
        name=D1_NAME,
    )


def check_d2_docs_present(project_root: Path) -> dict[str, Any]:
    screens = project_root / "agent_docs" / "screens.md"
    flow = project_root / "agent_docs" / "user-flow.md"
    missing: list[str] = []
    if not screens.exists() or screens.stat().st_size == 0:
        missing.append("screens.md")
    if not flow.exists() or flow.stat().st_size == 0:
        missing.append("user-flow.md")
    if missing:
        return make_finding(
            "D2", STATUS_WARN,
            f"missing under agent_docs/: {missing}",
            name=D2_NAME,
            remediation=D2_REMEDIATION,
        )
    return make_finding(
        "D2", STATUS_PASS,
        "screens.md + user-flow.md present",
        name=D2_NAME,
    )


def run(project_root: Path, run_id: str) -> list[dict[str, Any]]:
    del run_id
    return [
        check_d1_design_artifact(project_root),
        check_d2_docs_present(project_root),
    ]


__all__ = [
    "check_d1_design_artifact",
    "check_d2_docs_present",
    "run",
]
