"""Adopt-phase workflow compliance checks (Phase-Quality integration).

Implements A1–A8 canon checks for /shipwright-adopt (A6 retired
2026-05-05 — see ADR for iterate-20260505-plugin-hook-registration).
A1–A3, A7 are Tier-1 ERROR on FAIL (but the Stop-hook is non-blocking
by default so failures just surface as ``additionalContext`` next
session). A4, A5, A8 are Tier-2 heuristics that never block.

Retired check:
- A6 ``check_a6_hook_installed`` asserted a project-level
  ``UserPromptSubmit`` ``suggest_iterate`` entry in
  ``.claude/settings.json``. That installation channel was retired —
  the hook is now plugin-owned (registered in
  ``plugins/shipwright-iterate/hooks/hooks.json``). Claude Code itself
  enforces plugin-enablement; a duplicated repo-side check would only
  drift.
"""

from __future__ import annotations

import json
import re
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
    STATUS_SKIP,
    STATUS_WARN,
    make_finding,
)


REQUIRED_CONFIGS = [
    "shipwright_run_config.json",
    "shipwright_project_config.json",
    "shipwright_plan_config.json",
    "shipwright_build_config.json",
    "shipwright_compliance_config.json",
]


def check_a1_configs_present(project_root: Path) -> dict[str, Any]:
    """A1 (Tier-1): 5 required configs exist and parse as JSON."""
    name = "A1 All shipwright_*_config.json present + valid JSON"
    missing = [c for c in REQUIRED_CONFIGS if not (project_root / c).exists()]
    if missing:
        return make_finding(
            "A1", STATUS_FAIL,
            f"missing configs: {', '.join(missing)}",
            name=name,
            remediation="Re-run /shipwright-adopt — pre-flight should have aborted",
            provenance="adopt_config_check",
        )
    for c in REQUIRED_CONFIGS:
        try:
            json.loads((project_root / c).read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            return make_finding(
                "A1", STATUS_FAIL,
                f"invalid JSON in {c}: {e!r}",
                name=name,
                remediation="Fix the JSON or re-run /shipwright-adopt",
                provenance="adopt_config_check",
            )
    return make_finding(
        "A1", STATUS_PASS,
        f"{len(REQUIRED_CONFIGS)} required configs present and valid",
        name=name,
        provenance="adopt_config_check",
    )


def check_a2_spec_has_frs(project_root: Path) -> dict[str, Any]:
    """A2 (Tier-1): .shipwright/planning/*/spec.md contains >= 1 FR-NN.MM."""
    name = "A2 .shipwright/planning/<split>/spec.md has >= 1 FR"
    planning = project_root / PLANNING_DIRNAME
    if not planning.is_dir():
        return make_finding("A2", STATUS_FAIL, "missing .shipwright/planning/ directory",
                            name=name, provenance="adopt_spec_check")
    specs = list(planning.rglob("spec.md"))
    if not specs:
        return make_finding("A2", STATUS_FAIL, "no .shipwright/planning/<split>/spec.md found",
                            name=name, provenance="adopt_spec_check")
    for spec in specs:
        content = spec.read_text(encoding="utf-8", errors="ignore")
        if re.search(r"\bFR-\d+\.\d+\b", content):
            return make_finding(
                "A2", STATUS_PASS,
                f"FR found in {spec.relative_to(project_root).as_posix()}",
                name=name, provenance="adopt_spec_check",
            )
    return make_finding(
        "A2", STATUS_FAIL,
        ".shipwright/planning/*/spec.md: no FR-NN.MM reference in any spec",
        name=name,
        remediation="Manually add FRs or re-run /shipwright-adopt with more features",
        provenance="adopt_spec_check",
    )


def check_a3_adoption_adr(project_root: Path) -> dict[str, Any]:
    """A3 (Tier-1): decision_log.md has an adoption ADR (any id, 'Adopt' in title).

    The id is no longer hardcoded to ADR-0001: when /shipwright-adopt
    runs against a brownfield repo whose existing decision_log.md
    already declares 3-digit canonical ADRs, the adoption ADR takes
    the next-free id (e.g. ADR-059 with 58 pre-existing entries).
    Matching on the canonical title is the stable signal across both
    greenfield (ADR-001) and brownfield (ADR-NNN where N is max+1).
    """
    name = "A3 decision_log.md has adoption ADR"
    log = project_root / ".shipwright" / "agent_docs" / "decision_log.md"
    if not log.exists():
        return make_finding("A3", STATUS_FAIL, "missing .shipwright/agent_docs/decision_log.md",
                            name=name, provenance="adopt_adr_check")
    content = log.read_text(encoding="utf-8", errors="ignore")
    # Match any heading-level (H2/H3) ADR-NNN with at least 3 digits and
    # 'Adopt' in the title. Suffixes (045b) tolerated.
    if re.search(
        r"^#{2,3}\s+ADR-\d{3,}[a-z]?:[^\n]*[Aa]dopt",
        content,
        re.MULTILINE,
    ):
        return make_finding("A3", STATUS_PASS, "adoption ADR found",
                            name=name, provenance="adopt_adr_check")
    return make_finding(
        "A3", STATUS_FAIL,
        "no adoption ADR found (expected '## ADR-NNN: Adopt ...' or H3 equivalent)",
        name=name,
        remediation="Add an adoption ADR entry that documents the adoption decision",
        provenance="adopt_adr_check",
    )


def check_a4_backfill_quality(project_root: Path) -> dict[str, Any]:
    """A4 (Tier-2): if retroactive ADRs exist, they should have Context > 50 chars."""
    name = "A4 ADR backfill quality (Tier-2)"
    log = project_root / ".shipwright" / "agent_docs" / "decision_log.md"
    if not log.exists():
        return make_finding("A4", STATUS_SKIP, "no decision_log.md — nothing to assess",
                            name=name, provenance="adopt_adr_check")
    content = log.read_text(encoding="utf-8", errors="ignore")
    # Split on either H2 or H3 ADR boundaries. Adopt now writes H3
    # (matches Shipwright's compact-form canon and `parse_adr_headers`);
    # older adopt-output and user-authored logs may still use H2.
    entries = re.split(r"^#{2,3}\s+ADR-\d+", content, flags=re.MULTILINE)
    retroactive = [e for e in entries if "retroactive" in e.lower()]
    if not retroactive:
        return make_finding("A4", STATUS_SKIP, "no retroactive ADRs found",
                            name=name, provenance="adopt_adr_check")
    short = [e for e in retroactive if len(e.strip()) < 150]
    if short:
        return make_finding(
            "A4", STATUS_WARN,
            f"{len(short)} retroactive ADR(s) have thin content (<150 chars) — "
            "Layer-2 enrichment may have skipped or degraded",
            name=name, provenance="adopt_adr_check",
        )
    return make_finding(
        "A4", STATUS_PASS,
        f"{len(retroactive)} retroactive ADR(s) with substantive Context",
        name=name, provenance="adopt_adr_check",
    )


def check_a5_review_present(project_root: Path) -> dict[str, Any]:
    """A5 (Tier-2): .shipwright/adopt/review.md exists (may document skip)."""
    name = "A5 Layer-3 review artifact (Tier-2)"
    review = project_root / ".shipwright" / "adopt" / "review.md"
    if not review.exists():
        return make_finding(
            "A5", STATUS_WARN,
            "missing .shipwright/adopt/review.md — run review_runner to document review or skip-reason",
            name=name, provenance="adopt_review_check",
        )
    content = review.read_text(encoding="utf-8", errors="ignore")
    if "SKIPPED" in content:
        return make_finding(
            "A5", STATUS_PASS,
            "review skipped (documented reason present)",
            name=name, provenance="adopt_review_check",
        )
    return make_finding(
        "A5", STATUS_PASS,
        "review completed and recorded",
        name=name, provenance="adopt_review_check",
    )


def check_a7_adopted_event(project_root: Path) -> dict[str, Any]:
    """A7 (Tier-1): shipwright_events.jsonl has exactly 1 'adopted' event."""
    name = "A7 shipwright_events.jsonl has exactly 1 'adopted' event"
    events = project_root / "shipwright_events.jsonl"
    if not events.exists():
        return make_finding("A7", STATUS_FAIL, "missing shipwright_events.jsonl",
                            name=name, provenance="adopt_event_check")
    adopted = 0
    for line in events.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if ev.get("type") == "adopted":
            adopted += 1
    if adopted == 0:
        return make_finding("A7", STATUS_FAIL, "no 'adopted' event found",
                            name=name,
                            remediation="Re-seed via event_seeder.seed_adopted_event",
                            provenance="adopt_event_check")
    if adopted > 1:
        return make_finding("A7", STATUS_FAIL,
                            f"expected exactly 1 'adopted' event, found {adopted}",
                            name=name,
                            remediation="Remove duplicate events",
                            provenance="adopt_event_check")
    return make_finding("A7", STATUS_PASS, "exactly 1 'adopted' event",
                        name=name, provenance="adopt_event_check")


def check_a8_e2e_baseline(project_root: Path) -> dict[str, Any]:
    """A8 (Tier-2): e2e/flows/adopted-baseline.spec.ts exists if crawl succeeded.

    SKIP when the crawl was skipped (documented in review.md or handoff).
    WARN only if the spec is missing AND a crawl result suggests it should exist.
    """
    name = "A8 E2E adopted-baseline spec (Tier-2)"
    spec = project_root / "e2e" / "flows" / "adopted-baseline.spec.ts"
    routes = project_root / ".shipwright" / "adopt" / "routes.json"
    if spec.exists():
        return make_finding("A8", STATUS_PASS, "adopted-baseline.spec.ts present",
                            name=name, provenance="adopt_e2e_check")
    if routes.exists():
        return make_finding(
            "A8", STATUS_WARN,
            "routes.json present but e2e/flows/adopted-baseline.spec.ts missing — "
            "run e2e_baseline_generator to materialize it",
            name=name, provenance="adopt_e2e_check",
        )
    return make_finding(
        "A8", STATUS_SKIP,
        "no Playwright crawl output — baseline suite skipped by design",
        name=name, provenance="adopt_e2e_check",
    )


def run(project_root: Path, run_id: str) -> list[dict[str, Any]]:
    """Return adopt-phase canon findings.

    Note: A6 ``check_a6_hook_installed`` was retired 2026-05-05 —
    the suggest_iterate hook is now plugin-owned (registered in
    plugins/shipwright-iterate/hooks/hooks.json) and Claude Code
    enforces plugin-enablement directly.
    """
    return [
        check_a1_configs_present(project_root),
        check_a2_spec_has_frs(project_root),
        check_a3_adoption_adr(project_root),
        check_a4_backfill_quality(project_root),
        check_a5_review_present(project_root),
        check_a7_adopted_event(project_root),
        check_a8_e2e_baseline(project_root),
    ]


__all__ = [
    "check_a1_configs_present",
    "check_a2_spec_has_frs",
    "check_a3_adoption_adr",
    "check_a4_backfill_quality",
    "check_a5_review_present",
    "check_a7_adopted_event",
    "check_a8_e2e_baseline",
    "run",
]
