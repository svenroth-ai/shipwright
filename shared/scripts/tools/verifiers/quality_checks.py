"""Quality-category checks (Phase-Quality PR 3).

Implements Q1 and Q2 — the "was the decision substance actually
captured" and "did build finish every planned section" gates.

- **Q1** (Tier-2, WARN): the latest ADR in ``.shipwright/agent_docs/decision_log.md``
  has a non-trivial Context (≥50 chars), Decision (≥30) and
  Consequences (≥30) section. Heuristic — thresholds are intentionally
  forgiving (plan § 7 R13). Never FAIL.
- **Q2** (Tier-1, FAIL): every section the plan phase produced (captured
  in ``shipwright_plan_snapshot.json`` or derived from the planning
  directory) also appears in ``shipwright_build_config.json.sections``
  with a completed status. SKIPs when no snapshot nor planning tree
  exists (fresh project, pre-build-start, plan § 7 R14).
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

from lib.adr_parser import latest_adr_body  # noqa: E402
from lib.phase_quality import (  # noqa: E402
    STATUS_FAIL,
    STATUS_PASS,
    STATUS_SKIP,
    STATUS_WARN,
    make_finding,
)
from tools.verifiers.common import read_decision_log  # noqa: E402


Q1_NAME = "Q1 latest ADR has substantive Context/Decision/Consequences"
Q2_NAME = "Q2 all plan sections present in build_config.sections (complete)"

Q1_REMEDIATION = (
    "Expand the latest ADR: Context ≥50 chars, Decision ≥30, "
    "Consequences ≥30. These are forgiving thresholds — write a full "
    "sentence per field, not a placeholder."
)
Q2_REMEDIATION = (
    "Complete missing sections via /shipwright-build, then update "
    "shipwright_build_config.json.sections[*].status=complete."
)

# Plan § 3 thresholds for Q1 — tuned for "single sentence per field" not
# "short story". Changing these values invalidates R13 rationale.
Q1_MIN_CONTEXT = 50
Q1_MIN_DECISION = 30
Q1_MIN_CONSEQUENCES = 30

# Statuses treated as "done" when verifying Q2.
_COMPLETED_STATUSES: frozenset[str] = frozenset({
    "complete", "completed", "done",
})


# ---------------------------------------------------------------------------
# Q1 — ADR substance
# ---------------------------------------------------------------------------

def check_q1_adr_substance(project_root: Path) -> dict[str, Any]:
    """Q1 — verify the latest ADR has a non-trivial body.

    Uses ``lib.adr_parser.latest_adr_body`` so the check doesn't care
    whether the ADR uses bullet-form (``- **Context:** ...``) or
    section-form (``**Context**`` + paragraph) — both Shipwright shapes
    are normalised in the parser. Never FAIL; heuristic only.
    """
    content = read_decision_log(project_root)
    if not content:
        return make_finding(
            "Q1", STATUS_SKIP,
            ".shipwright/agent_docs/decision_log.md missing or empty — nothing to audit",
            name=Q1_NAME,
        )

    body = latest_adr_body(content)
    if body is None:
        return make_finding(
            "Q1", STATUS_SKIP,
            "no ADR headers parsed — no substance to verify",
            name=Q1_NAME,
        )

    context = body.get("context")
    decision = body.get("decision")
    consequences = body.get("consequences")

    missing: list[str] = []
    if len(context) < Q1_MIN_CONTEXT:
        missing.append(f"Context ({len(context)} < {Q1_MIN_CONTEXT})")
    if len(decision) < Q1_MIN_DECISION:
        missing.append(f"Decision ({len(decision)} < {Q1_MIN_DECISION})")
    if len(consequences) < Q1_MIN_CONSEQUENCES:
        missing.append(f"Consequences ({len(consequences)} < {Q1_MIN_CONSEQUENCES})")

    if missing:
        return make_finding(
            "Q1", STATUS_WARN,
            f"{body.header.id}: {', '.join(missing)}",
            name=Q1_NAME,
            remediation=Q1_REMEDIATION,
            provenance="unverified_marker",
        )

    return make_finding(
        "Q1", STATUS_PASS,
        f"{body.header.id}: Context={len(context)}, Decision={len(decision)}, "
        f"Consequences={len(consequences)}",
        name=Q1_NAME,
    )


# ---------------------------------------------------------------------------
# Q2 — plan sections ⊆ build completed sections
# ---------------------------------------------------------------------------

def _read_plan_section_names(project_root: Path) -> list[str] | None:
    """Return the plan-phase section names, or None if unknowable.

    Resolution order:
    1. ``shipwright_plan_snapshot.json`` — authoritative snapshot written
       at build-start (plan § 3 + R14).
    2. ``.shipwright/planning/sections/*.md`` — monolithic plan layout.
    3. ``.shipwright/planning/<split>/sections/*.md`` — split-based plan layout.

    Returns a de-duplicated, sorted list of section file stems. A result
    of ``None`` means "no plan material found yet" and downstream logic
    should SKIP instead of FAILing.
    """
    snapshot = project_root / "shipwright_plan_snapshot.json"
    if snapshot.exists():
        try:
            data = json.loads(snapshot.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            data = None
        if isinstance(data, dict):
            raw = data.get("sections")
            if isinstance(raw, list):
                names = [str(n).strip() for n in raw if str(n).strip()]
                if names:
                    return sorted(set(names))

    planning = project_root / PLANNING_DIRNAME
    if not planning.is_dir():
        return None

    collected: set[str] = set()
    for section_md in planning.glob("sections/*.md"):
        collected.add(section_md.stem)
    for section_md in planning.glob("*/sections/*.md"):
        collected.add(section_md.stem)

    if not collected:
        return None
    return sorted(collected)


def _read_build_section_status(project_root: Path) -> dict[str, str] | None:
    cfg = project_root / "shipwright_build_config.json"
    if not cfg.exists():
        return None
    try:
        data = json.loads(cfg.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    sections = data.get("sections")
    if not isinstance(sections, list):
        return {}
    result: dict[str, str] = {}
    for entry in sections:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        status = entry.get("status")
        if isinstance(name, str) and name:
            result[name] = str(status or "").strip().lower()
    return result


def check_q2_plan_subset_of_build(project_root: Path) -> dict[str, Any]:
    """Q2 — every planned section is present and complete in build config."""
    plan_sections = _read_plan_section_names(project_root)
    if plan_sections is None:
        return make_finding(
            "Q2", STATUS_SKIP,
            "no plan snapshot and no .shipwright/planning/ tree — "
            "plan phase has not produced sections yet",
            name=Q2_NAME,
        )

    build_statuses = _read_build_section_status(project_root)
    if build_statuses is None:
        return make_finding(
            "Q2", STATUS_FAIL,
            "shipwright_build_config.json missing — build never recorded "
            f"{len(plan_sections)} planned section(s)",
            name=Q2_NAME,
            remediation=Q2_REMEDIATION,
        )

    missing: list[str] = []
    incomplete: list[str] = []
    for name in plan_sections:
        if name not in build_statuses:
            missing.append(name)
            continue
        if build_statuses[name] not in _COMPLETED_STATUSES:
            incomplete.append(f"{name}={build_statuses[name] or '<empty>'}")

    if missing or incomplete:
        parts: list[str] = []
        if missing:
            preview = ", ".join(missing[:3])
            suffix = f" (+{len(missing) - 3} more)" if len(missing) > 3 else ""
            parts.append(f"{len(missing)} missing: {preview}{suffix}")
        if incomplete:
            preview = ", ".join(incomplete[:3])
            suffix = f" (+{len(incomplete) - 3} more)" if len(incomplete) > 3 else ""
            parts.append(f"{len(incomplete)} incomplete: {preview}{suffix}")
        return make_finding(
            "Q2", STATUS_FAIL,
            "; ".join(parts),
            name=Q2_NAME,
            remediation=Q2_REMEDIATION,
        )

    return make_finding(
        "Q2", STATUS_PASS,
        f"all {len(plan_sections)} planned section(s) complete in build config",
        name=Q2_NAME,
    )


# ---------------------------------------------------------------------------
# Phase → check list dispatch (plan § 5.1)
# ---------------------------------------------------------------------------

_PHASE_TO_CHECKS: dict[str, tuple[str, ...]] = {
    "project": ("Q1",),
    "plan":    ("Q1",),
    "build":   ("Q1", "Q2"),
    "iterate": ("Q1",),
}


def run(phase: str, project_root: Path) -> list[dict[str, Any]]:
    checks = _PHASE_TO_CHECKS.get(phase)
    if not checks:
        return []
    findings: list[dict[str, Any]] = []
    for check_id in checks:
        if check_id == "Q1":
            findings.append(check_q1_adr_substance(project_root))
        elif check_id == "Q2":
            findings.append(check_q2_plan_subset_of_build(project_root))
    return findings


__all__ = [
    "Q1_MIN_CONSEQUENCES",
    "Q1_MIN_CONTEXT",
    "Q1_MIN_DECISION",
    "check_q1_adr_substance",
    "check_q2_plan_subset_of_build",
    "run",
]
