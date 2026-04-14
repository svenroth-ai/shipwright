"""Iterate-phase verifier checks.

Migrated 1:1 from ``shared/scripts/tools/verify_iterate_finalization.py``
during iterate 12.0 (ADR-027). Behaviour and severity levels are
unchanged — the 18 pre-existing tests in
``shared/tests/test_verify_iterate_finalization.py`` must stay green
without modification. The pre-12.0 script survives as a thin wrapper
that re-exports these symbols so any downstream caller importing
``tools.verify_iterate_finalization`` keeps working.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

from .common import CheckResult, Severity


# ---------------------------------------------------------------------------
# Individual checks (iterate-specific — do NOT use the generic C1-C5 helpers)
# ---------------------------------------------------------------------------

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
    """F3 + F5c consistency — ``iterate_history[run_id].adr`` points at an
    ADR that actually exists in ``decision_log.md``."""
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
    """F4 check — ``CHANGELOG.md [Unreleased]`` has at least one bullet.

    CHANGELOG.md lives at the monorepo root (one level above
    ``project_root`` for ``webui``, same level for standalone projects).
    Try both locations.
    """
    name = "CHANGELOG.md [Unreleased] has entries"
    candidates = [project_root / "CHANGELOG.md", project_root.parent / "CHANGELOG.md"]
    changelog = next((c for c in candidates if c.exists()), None)
    if not changelog:
        return CheckResult(
            name,
            False,
            f"CHANGELOG.md not found in {project_root} or its parent",
            severity=Severity.WARNING.value,
        )
    content = changelog.read_text(encoding="utf-8", errors="ignore")

    # Match the [Unreleased] section up to the next `## [version]` heading
    # (Keep-a-Changelog convention). The previous regex used `\s*\n`, which
    # could cross an empty section boundary and leak bullets from the
    # following version section — this form is stricter.
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
    """F11 check — ``session_handoff.md`` was regenerated recently.

    Warning-level because handoff is advisory, not load-bearing.
    """
    name = "session_handoff.md fresh"
    handoff = project_root / "agent_docs" / "session_handoff.md"
    if not handoff.exists():
        return CheckResult(
            name,
            False,
            "session_handoff.md missing",
            severity=Severity.WARNING.value,
        )
    age = time.time() - handoff.stat().st_mtime
    if age <= max_age_seconds:
        return CheckResult(name, True, f"mtime age {int(age)}s")
    return CheckResult(
        name,
        False,
        f"stale: mtime age {int(age)}s > {max_age_seconds}s",
        severity=Severity.WARNING.value,
    )


# ---------------------------------------------------------------------------
# Orchestrator (kept for backwards compat with verify_iterate_finalization.py)
# ---------------------------------------------------------------------------

def run_all_checks(
    project_root: Path,
    run_id: str,
    commit_hash: str = "",
) -> list[CheckResult]:
    """Run the full iterate check list and return results in stable order."""
    return [
        check_iterate_history_has_run_id(project_root, run_id),
        check_events_has_commit(project_root, commit_hash) if commit_hash else CheckResult(
            "events.jsonl has commit", True, "skipped (no --commit supplied)"
        ),
        check_adr_in_iterate_history(project_root, run_id),
        check_changelog_unreleased(project_root),
        check_session_handoff_fresh(project_root),
    ]
