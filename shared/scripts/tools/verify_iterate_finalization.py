"""Deterministic post-commit verifier for iterate finalization.

Shipwright keeps a lot of cross-artifact sync invariants during an iterate
run's F0-F11 finalization sequence. Miss ONE step and the next run starts
with silently drifted state: iterate_history doesn't know about the commit,
architecture.md is stuck at an older ADR, session_handoff.md points at
last week's branch, etc.

Iterate 11 introduces this script as a minimal "am I done?" checklist that
runs after F6 but before the user walks away. Each check is a pure function
returning a CheckResult — easy to unit-test and extend. Iterate 12 will
expand this into a full cross-plugin sync verifier (project, design, plan,
build, test, changelog, deploy, compliance, iterate) under Plan Mode.

CLI usage:
    uv run verify_iterate_finalization.py \\
        --run-id iterate-2026-04-13-foo \\
        --project-root webui \\
        --commit $(git rev-parse HEAD)

Exit code 0 = all green (or warnings only).
Exit code 1 = one or more hard-failures (missing required artifact).

The WARN level is used for soft drift (e.g. session_handoff.md stale by
hours) — visible to the user, not blocking. Callers that want strict
behavior can pass --strict to promote warnings to failures.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path


# ──────────────────────────────────────────────────────────────────────
# Result type
# ──────────────────────────────────────────────────────────────────────

@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str = ""
    severity: str = "error"  # "error" | "warning"


# ──────────────────────────────────────────────────────────────────────
# Individual checks
# ──────────────────────────────────────────────────────────────────────

def check_iterate_history_has_run_id(project_root: Path, run_id: str) -> CheckResult:
    """F5c check — the iterate run appended itself to iterate_history."""
    name = "iterate_history has run_id"
    cfg = project_root / "shipwright_run_config.json"
    if not cfg.exists():
        return CheckResult(name, False, f"missing {cfg.name}")
    try:
        data = json.loads(cfg.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return CheckResult(name, False, f"malformed {cfg.name}: {e}")
    history = data.get("iterate_history", [])
    if any(entry.get("run_id") == run_id for entry in history):
        return CheckResult(name, True, f"run_id={run_id} present")
    return CheckResult(
        name,
        False,
        f"run_id={run_id} not in iterate_history ({len(history)} entries)",
    )


def check_events_has_commit(project_root: Path, commit_hash: str) -> CheckResult:
    """F7 check — record_event wrote the commit to events.jsonl."""
    name = "events.jsonl has commit"
    events = project_root / "shipwright_events.jsonl"
    if not events.exists():
        return CheckResult(name, False, f"missing {events.name}")
    content = events.read_text(encoding="utf-8", errors="ignore")
    if commit_hash and commit_hash in content:
        return CheckResult(name, True, f"commit={commit_hash[:8]} found")
    return CheckResult(name, False, f"commit={commit_hash[:8]} not found")


def check_adr_in_iterate_history(project_root: Path, run_id: str) -> CheckResult:
    """F3 + F5c consistency — iterate_history[run_id].adr points at an
    ADR that actually exists in decision_log.md."""
    name = "ADR recorded + present"
    cfg = project_root / "shipwright_run_config.json"
    if not cfg.exists():
        return CheckResult(name, False, f"missing {cfg.name}")
    try:
        data = json.loads(cfg.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return CheckResult(name, False, f"malformed {cfg.name}")
    entry = next(
        (e for e in data.get("iterate_history", []) if e.get("run_id") == run_id),
        None,
    )
    if not entry:
        return CheckResult(name, False, f"run_id={run_id} not in iterate_history")
    adr_id = entry.get("adr")
    if not adr_id:
        return CheckResult(name, False, f"iterate_history[{run_id}].adr missing")

    log = project_root / "agent_docs" / "decision_log.md"
    if not log.exists():
        return CheckResult(name, False, f"missing {log.name}")
    log_content = log.read_text(encoding="utf-8", errors="ignore")
    if re.search(rf"### {re.escape(adr_id)}[: ]", log_content):
        return CheckResult(name, True, f"{adr_id} present in decision_log.md")
    return CheckResult(name, False, f"{adr_id} NOT found in decision_log.md")


def check_changelog_unreleased(project_root: Path) -> CheckResult:
    """F4 check — CHANGELOG.md [Unreleased] section has at least one bullet.

    CHANGELOG.md lives at the monorepo root (one level above project_root
    for webui, same level for standalone projects). Try both locations.
    """
    name = "CHANGELOG.md [Unreleased] has entries"
    candidates = [project_root / "CHANGELOG.md", project_root.parent / "CHANGELOG.md"]
    changelog = next((c for c in candidates if c.exists()), None)
    if not changelog:
        return CheckResult(
            name,
            False,
            f"CHANGELOG.md not found in {project_root} or its parent",
            severity="warning",
        )
    content = changelog.read_text(encoding="utf-8", errors="ignore")

    # Find the [Unreleased] section and count bullets before the next
    # `## [version]` bracketed heading (Keep-a-Changelog convention).
    # The previous regex used `\s*\n` which could cross an empty section
    # boundary and leak bullets from the following version section.
    match = re.search(
        r"## \[Unreleased\][^\n]*\n(.*?)(?=\n## \[|\Z)",
        content,
        re.DOTALL,
    )
    if not match:
        return CheckResult(name, False, "no [Unreleased] section found")
    section = match.group(1)
    bullet_count = len(re.findall(r"^\s*-\s+", section, re.MULTILINE))
    if bullet_count == 0:
        return CheckResult(name, False, "[Unreleased] has no bullets")
    return CheckResult(name, True, f"{bullet_count} bullets in [Unreleased]")


def check_session_handoff_fresh(
    project_root: Path,
    max_age_seconds: int = 600,
) -> CheckResult:
    """F11 check — session_handoff.md was regenerated recently.

    Warning-level because handoff is advisory, not load-bearing.
    """
    name = "session_handoff.md fresh"
    handoff = project_root / "agent_docs" / "session_handoff.md"
    if not handoff.exists():
        return CheckResult(
            name,
            False,
            "session_handoff.md missing",
            severity="warning",
        )
    age = time.time() - handoff.stat().st_mtime
    if age <= max_age_seconds:
        return CheckResult(name, True, f"mtime age {int(age)}s")
    return CheckResult(
        name,
        False,
        f"stale: mtime age {int(age)}s > {max_age_seconds}s",
        severity="warning",
    )


# ──────────────────────────────────────────────────────────────────────
# Orchestrator
# ──────────────────────────────────────────────────────────────────────

def run_all_checks(
    project_root: Path,
    run_id: str,
    commit_hash: str = "",
) -> list[CheckResult]:
    """Run the full check list and return results in stable order."""
    return [
        check_iterate_history_has_run_id(project_root, run_id),
        check_events_has_commit(project_root, commit_hash) if commit_hash else CheckResult(
            "events.jsonl has commit", True, "skipped (no --commit supplied)"
        ),
        check_adr_in_iterate_history(project_root, run_id),
        check_changelog_unreleased(project_root),
        check_session_handoff_fresh(project_root),
    ]


def format_report(results: list[CheckResult]) -> str:
    lines = [
        "================================================================================",
        "SHIPWRIGHT-ITERATE: Finalization Verifier",
        "================================================================================",
    ]
    errors = 0
    warnings = 0
    for r in results:
        if r.ok:
            icon = "[32m OK [0m"
        elif r.severity == "warning":
            icon = "[33mWARN[0m"
            warnings += 1
        else:
            icon = "[31mFAIL[0m"
            errors += 1
        lines.append(f"  {icon}  {r.name:<40}  {r.detail}")
    lines.append("--------------------------------------------------------------------------------")
    lines.append(f"  {errors} error(s), {warnings} warning(s)")
    lines.append("================================================================================")
    return "\n".join(lines)


# ──────────────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--run-id", required=True, help="Iterate run id to verify")
    parser.add_argument("--project-root", default=".", help="Project directory")
    parser.add_argument("--commit", default="", help="Current HEAD commit hash")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Treat warnings as errors (exit 1 if any WARN/FAIL)",
    )
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()
    results = run_all_checks(project_root, args.run_id, args.commit)
    print(format_report(results))

    errors = sum(1 for r in results if not r.ok and r.severity == "error")
    warnings = sum(1 for r in results if not r.ok and r.severity == "warning")

    if errors > 0 or (args.strict and warnings > 0):
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
