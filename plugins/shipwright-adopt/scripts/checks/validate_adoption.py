#!/usr/bin/env python3
"""Post-generation canon-lite validation for /shipwright-adopt.

Runs after all artifacts are written. Verifies:
  - 5 required config JSONs exist + valid JSON (sync_config optional)
  - .shipwright/agent_docs/{architecture, conventions, decision_log, build_dashboard}.md exist
  - .shipwright/planning/*/spec.md exists and has >= 1 FR-NN.MM reference
  - shipwright_events.jsonl has exactly 1 "adopted" event
  - .shipwright/adopt/review.md exists (skip-reason is acceptable)

The .claude/settings.json UserPromptSubmit hook check was retired
2026-05-05 (iterate-20260505-plugin-hook-registration) — the hook is
now plugin-owned (plugins/shipwright-iterate/hooks/hooks.json).

Exit 0 on success, non-zero with error list otherwise.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


REQUIRED_CONFIGS = [
    "shipwright_run_config.json",
    "shipwright_project_config.json",
    "shipwright_plan_config.json",
    "shipwright_build_config.json",
    "shipwright_compliance_config.json",
]

REQUIRED_AGENT_DOCS = [
    ".shipwright/agent_docs/architecture.md",
    ".shipwright/agent_docs/conventions.md",
    ".shipwright/agent_docs/decision_log.md",
    ".shipwright/agent_docs/build_dashboard.md",
]


def _validate_configs(project_root: Path) -> list[str]:
    errors: list[str] = []
    for name in REQUIRED_CONFIGS:
        p = project_root / name
        if not p.exists():
            errors.append(f"missing: {name}")
            continue
        try:
            json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            errors.append(f"invalid JSON: {name} ({e.msg})")
    return errors


def _validate_agent_docs(project_root: Path) -> list[str]:
    errors: list[str] = []
    for name in REQUIRED_AGENT_DOCS:
        if not (project_root / name).exists():
            errors.append(f"missing: {name}")
    return errors


def _validate_spec(project_root: Path) -> list[str]:
    errors: list[str] = []
    planning = project_root / ".shipwright" / "planning"
    if not planning.is_dir():
        return ["missing: .shipwright/planning/ directory"]
    specs = list(planning.rglob("spec.md"))
    if not specs:
        return ["missing: .shipwright/planning/<split>/spec.md (no spec found)"]
    spec = specs[0]
    content = spec.read_text(encoding="utf-8", errors="ignore")
    if not re.search(r"\bFR-\d+\.\d+\b", content):
        errors.append(f"spec.md has no FR-NN.MM reference: {spec.relative_to(project_root).as_posix()}")
    return errors


def _validate_events(project_root: Path) -> list[str]:
    events_path = project_root / "shipwright_events.jsonl"
    if not events_path.exists():
        return ["missing: shipwright_events.jsonl"]
    adopted_count = 0
    for line in events_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if ev.get("type") == "adopted":
            adopted_count += 1
    if adopted_count == 0:
        return ["shipwright_events.jsonl: no 'adopted' event found"]
    if adopted_count > 1:
        return [f"shipwright_events.jsonl: expected exactly 1 'adopted' event, found {adopted_count}"]
    return []


# _validate_hook retired 2026-05-05 (iterate-20260505-plugin-hook-registration):
# the suggest_iterate UserPromptSubmit hook is now plugin-owned (registered
# in plugins/shipwright-iterate/hooks/hooks.json). Claude Code surfaces
# disabled-plugin state at session start; an adopt-side validation would
# only drift.


def _validate_review(project_root: Path) -> list[str]:
    review = project_root / ".shipwright" / "adopt" / "review.md"
    if not review.exists():
        return ["missing: .shipwright/adopt/review.md (should document review OR skip-reason)"]
    return []


def _count_adrs(decision_log: Path) -> int:
    if not decision_log.is_file():
        return 0
    body = decision_log.read_text(encoding="utf-8", errors="ignore")
    # Match both H2 and H3 ADR headings. H3 is the canonical form used by
    # write_decision_log.py (and by adopt's decision_log generator since
    # commit 63352ff which fixed brownfield-ADR parser round-trip); H2 is
    # accepted for compatibility with older logs.
    return len(re.findall(r"^#{2,3}\s+ADR-\d+", body, re.MULTILINE))


def _read_snapshot_commits_total(project_root: Path) -> int | None:
    snap = project_root / ".shipwright" / "adopt" / "snapshot.json"
    if not snap.is_file():
        return None
    try:
        data = json.loads(snap.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    git = data.get("git") or {}
    val = git.get("commits_total")
    if isinstance(val, int):
        return val
    return None


def _soft_check_decision_log_density(project_root: Path) -> list[str]:
    """Warn (not error) when the decision_log feels suspiciously thin for the
    repo's git history. A 200-commit repo with 1 ADR is plausible to flag
    as "did Layer-2 enrichment skip the retroactive ADRs?" """
    warnings: list[str] = []
    commits = _read_snapshot_commits_total(project_root)
    if commits is None or commits <= 50:
        return warnings  # not enough signal to flag
    adrs = _count_adrs(project_root / ".shipwright" / "agent_docs" / "decision_log.md")
    if adrs < 3:
        warnings.append(
            f".shipwright/agent_docs/decision_log.md has {adrs} ADR(s) but the repo has "
            f"{commits} commits — historical data may be missing. Re-run "
            "Layer-2 enrichment or seed retroactive ADRs from "
            "git.major_refactor_commits[]."
        )
    return warnings


def validate(project_root: Path) -> dict:
    """Run hard + soft validation. Returns `{errors: [...], warnings: [...]}`."""
    errors: list[str] = []
    errors.extend(_validate_configs(project_root))
    errors.extend(_validate_agent_docs(project_root))
    errors.extend(_validate_spec(project_root))
    errors.extend(_validate_events(project_root))
    errors.extend(_validate_review(project_root))

    warnings: list[str] = []
    warnings.extend(_soft_check_decision_log_density(project_root))

    return {"errors": errors, "warnings": warnings}


def main() -> int:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
    from cli_paths import unquoted_path
    parser = argparse.ArgumentParser(description="Post-generation validation for /shipwright-adopt")
    parser.add_argument("--project-root", required=True, type=unquoted_path)
    args = parser.parse_args()
    project_root = args.project_root.resolve()
    result = validate(project_root)
    errors = result["errors"]
    warnings = result["warnings"]
    if errors:
        print(json.dumps({"ok": False, "errors": errors, "warnings": warnings}, indent=2))
        return 1
    print(json.dumps({"ok": True, "errors": [], "warnings": warnings}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
