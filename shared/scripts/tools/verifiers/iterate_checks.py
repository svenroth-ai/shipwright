"""Iterate-phase verifier checks.

Migrated 1:1 from ``shared/scripts/tools/verify_iterate_finalization.py``
during iterate 12.0 (ADR-027). Behaviour and severity levels are
unchanged — the 18 pre-existing tests in
``shared/tests/test_verify_iterate_finalization.py`` must stay green
without modification. The pre-12.0 script survives as a thin wrapper
that re-exports these symbols so any downstream caller importing
``tools.verify_iterate_finalization`` keeps working.

Dual-mode reads
---------------
Since the iterate_history file-per-iterate refactor, every read of the
iterate entry store goes through ``lib.iterate_entry.read_iterate_entries``
(merged legacy-array + per-file directory). Partial migrations no longer
hide entries; a brand-new project with only ``.shipwright/agent_docs/iterates/``
files and no legacy array is fully supported.
"""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

_SCRIPTS_ROOT = Path(__file__).resolve().parents[2]
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from lib.events_log import resolve_events_path  # noqa: E402
from lib.iterate_entry import (  # noqa: E402
    MIGRATION_QUARANTINED_COUNT_KEY,
    find_entry_by_run_id,
    read_iterate_entries,
    sanitize_run_id_for_filename,
)

from .common import CheckResult, Severity  # noqa: E402


# ---------------------------------------------------------------------------
# Individual checks (iterate-specific — do NOT use the generic C1-C5 helpers)
# ---------------------------------------------------------------------------

def check_iterate_history_has_run_id(project_root: Path, run_id: str) -> CheckResult:
    """F5c check — the iterate run appended itself to the entry store.

    Reads from the merged legacy array + ``.shipwright/agent_docs/iterates/`` directory.
    Passes if either source contains the run_id.
    """
    name = "iterate_history has run_id"
    entries = read_iterate_entries(project_root)
    if any(entry.get("run_id") == run_id for entry in entries):
        return CheckResult(name, True, f"run_id={run_id} present")
    return CheckResult(
        name,
        False,
        f"run_id={run_id} not in iterate history ({len(entries)} entries)",
    )


def check_events_has_commit(project_root: Path, commit_hash: str) -> CheckResult:
    """F7 check — record_event wrote the commit to events.jsonl.

    Worktree-aware: resolves the canonical (main-repo) event log via
    ``resolve_events_path`` so the F11 verifier, run from inside a
    ``/shipwright-iterate`` worktree, reads the log F7 actually appended
    to — not an empty worktree-local copy.
    """
    name = "events.jsonl has commit"
    events = resolve_events_path(project_root)
    if not events.exists():
        return CheckResult(name, False, f"missing {events.name}")
    content = events.read_text(encoding="utf-8", errors="ignore")
    if commit_hash and commit_hash in content:
        return CheckResult(name, True, f"commit={commit_hash[:8]} found")
    return CheckResult(name, False, f"commit={commit_hash[:8]} not found")


def check_adr_in_iterate_history(project_root: Path, run_id: str) -> CheckResult:
    """F3 + F5c consistency — the entry for ``run_id`` carries an ``adr`` field
    that resolves to a real ADR.

    Two ADR-identity shapes are accepted:

    - ``ADR-NNN`` — a numbered ADR; must be a heading in ``decision_log.md``
      (the direct-append path used by non-iterate phases).
    - a run-id — the iterate decision-drop pattern (H). Pre-aggregation the
      ADR lives as a JSON drop under ``decision-drops/``; post-aggregation it
      has been folded into ``decision_log.md`` with a ``Run-ID:`` line.

    Entry lookup goes through the merged reader so new-format projects
    without any legacy array still resolve cleanly.
    """
    name = "ADR recorded + present"
    entry = find_entry_by_run_id(project_root, run_id)
    if not entry:
        return CheckResult(name, False, f"run_id={run_id} not in iterate history")
    adr_id = entry.get("adr")
    if not adr_id:
        return CheckResult(name, False, f"iterate_history[{run_id}].adr missing")

    log = project_root / ".shipwright" / "agent_docs" / "decision_log.md"
    log_content = (
        log.read_text(encoding="utf-8", errors="ignore") if log.exists() else ""
    )

    # Run-id ADR identity — the H decision-drop pattern. fullmatch (not
    # match) so a run-id that merely starts with "adr-" is not misread as a
    # numbered ADR.
    if not re.fullmatch(r"(?i)ADR-\d+", adr_id.strip()):
        drop_dir = project_root / ".shipwright" / "agent_docs" / "decision-drops"
        if drop_dir.is_dir():
            safe = sanitize_run_id_for_filename(adr_id)
            if any(p.name.startswith(f"{safe}_") for p in drop_dir.glob("*.json")):
                return CheckResult(
                    name, True, f"{adr_id}: decision-drop pending aggregation"
                )
        if log_content and re.search(
            rf"\*\*Run-ID:\*\*\s*{re.escape(adr_id)}\b", log_content
        ):
            return CheckResult(
                name, True, f"{adr_id}: ADR aggregated into decision_log.md"
            )
        return CheckResult(
            name, False, f"{adr_id}: no decision-drop and not in decision_log.md"
        )

    # Numbered ADR — heading must be present in decision_log.md.
    if not log.exists():
        return CheckResult(name, False, f"missing {log.name}")
    if re.search(rf"### {re.escape(adr_id)}[: ]", log_content):
        return CheckResult(name, True, f"{adr_id} present in decision_log.md")
    return CheckResult(name, False, f"{adr_id} NOT found in decision_log.md")


def _find_changelog_drop_files(
    base_dir: Path,
    run_id: str | None,
) -> list[Path]:
    """Return drop files in ``CHANGELOG-unreleased.d/<category>/`` matching
    ``run_id`` (if given), else all non-``.gitkeep`` ``.md`` files. The
    drop-directory layout is owned by ``write_changelog_drop.py`` and
    aggregated into ``CHANGELOG.md`` at release time.
    """
    drop_root = base_dir / "CHANGELOG-unreleased.d"
    if not drop_root.is_dir():
        return []
    pattern = f"{run_id}_*.md" if run_id else "*.md"
    found: list[Path] = []
    for category_dir in sorted(p for p in drop_root.iterdir() if p.is_dir()):
        for f in category_dir.glob(pattern):
            if f.name == ".gitkeep":
                continue
            found.append(f)
    return found


def check_changelog_unreleased(
    project_root: Path,
    run_id: str | None = None,
) -> CheckResult:
    """F4 check — the iterate's changelog entry exists.

    Recognizes both the legacy ``CHANGELOG.md [Unreleased]`` model and
    the drop-directory model introduced by ``aggregate_changelog.py``:
    entries land in ``CHANGELOG-unreleased.d/<category>/<run_id>_NNN.md``
    between releases and are merged into the dated section at release time.

    Pass conditions (any of):
      1. A drop file matching ``run_id`` exists (when ``run_id`` is given).
      2. Any non-``.gitkeep`` drop file exists (when ``run_id`` omitted —
         legacy callers).
      3. ``CHANGELOG.md [Unreleased]`` has at least one bullet
         (pre-drop-dir behaviour, kept for backward compat).
    """
    name = "CHANGELOG.md [Unreleased] has entries"

    # Drop-dir layout sits next to CHANGELOG.md, which lives at project_root
    # for standalone projects and at project_root.parent for monorepo-nested
    # ones (e.g. webui). Probe both bases.
    drop_bases = [project_root, project_root.parent]
    for base in drop_bases:
        drop_files = _find_changelog_drop_files(base, run_id)
        if drop_files:
            label = f"run_id={run_id}" if run_id else "any iterate"
            return CheckResult(
                name, True,
                f"{len(drop_files)} drop file(s) in CHANGELOG-unreleased.d for {label}",
            )

    # Fallback: legacy CHANGELOG.md [Unreleased] check
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
    handoff = project_root / ".shipwright" / "agent_docs" / "session_handoff.md"
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
# C2 check — build_dashboard.md reflects the iterate run (Canon spec gap)
# ---------------------------------------------------------------------------

def check_build_dashboard_has_run_id(
    project_root: Path,
    run_id: str,
    commit_hash: str | None = None,
) -> CheckResult:
    """C2 check — ``build_dashboard.md`` reflects the current iterate run.

    The dashboard is rendered by ``finalize_iterate.py`` (F5b) via
    ``update_build_dashboard.py``. F5b runs BEFORE the F6 commit and the
    F7 event, so the dashboard at F11-verify time structurally cannot
    contain the new commit SHA. F5b therefore embeds the iterate
    ``run_id`` in the dashboard header (``| Run: {run_id}``) as the
    deterministic, timing-independent marker. The check accepts either:

      1. the ``run_id`` literal in the dashboard — the canonical signal,
         embedded by F5b (see ``update_build_dashboard.generate_dashboard``).
      2. the short SHA prefix of ``commit_hash`` — for build-phase
         dashboards and post-F7 re-renders where the commit predates the
         render.

    Either match is sufficient — both signal that the iterate row landed.
    """
    name = "build_dashboard has run_id"
    dashboard = project_root / ".shipwright" / "agent_docs" / "build_dashboard.md"
    if not dashboard.exists():
        return CheckResult(
            name, False, "build_dashboard.md missing",
            severity=Severity.WARNING.value,
        )
    content = dashboard.read_text(encoding="utf-8", errors="ignore")
    if run_id and run_id in content:
        return CheckResult(name, True, f"run_id={run_id} present")
    if commit_hash:
        short_sha = commit_hash[:7]
        if short_sha and short_sha in content:
            return CheckResult(
                name, True,
                f"commit={short_sha} present (run_id={run_id} not embedded)",
            )
    return CheckResult(
        name, False,
        f"run_id={run_id} not found in build_dashboard.md",
        severity=Severity.WARNING.value,
    )


# ---------------------------------------------------------------------------
# Cross-artifact warnings (non-canon — advisory only)
# ---------------------------------------------------------------------------

def check_compliance_reflects_run_id(
    project_root: Path,
    run_id: str,
) -> CheckResult:
    """Non-canon warning: compliance dashboard should reference the run."""
    name = "compliance reflects run_id"
    dashboard = project_root / ".shipwright" / "compliance" / "dashboard.md"
    if not dashboard.exists():
        return CheckResult(
            name, False, ".shipwright/compliance/dashboard.md missing",
            severity=Severity.WARNING.value,
        )
    content = dashboard.read_text(encoding="utf-8", errors="ignore")
    iterate_count = len(read_iterate_entries(project_root))
    if str(iterate_count) in content or run_id in content:
        return CheckResult(name, True, "compliance reflects iterate count/run_id")
    return CheckResult(
        name, False,
        f".shipwright/compliance/dashboard.md may be stale (run_id={run_id} not found)",
        severity=Severity.WARNING.value,
    )


def _freshness_mtime_reference(project_root: Path, run_id: str) -> float | None:
    """Pick a freshness reference mtime for a given run_id.

    Prefer the per-iterate entry file (added by the file-per-iterate
    refactor) because it's created at finalize time and doesn't churn with
    unrelated config mutations. Fall back to ``shipwright_run_config.json``
    for legacy projects that still carry the array.
    """
    from lib.iterate_entry import entry_file_for

    entry_path = entry_file_for(project_root, run_id)
    if entry_path.exists():
        return entry_path.stat().st_mtime
    cfg = project_root / "shipwright_run_config.json"
    if cfg.exists():
        return cfg.stat().st_mtime
    return None


def check_architecture_reviewed(
    project_root: Path,
    run_id: str,
) -> CheckResult:
    """Non-canon warning: architecture.md may need update after structural changes."""
    name = "architecture.md reviewed"
    entry = find_entry_by_run_id(project_root, run_id)
    if not entry:
        return CheckResult(name, None, "run_id not in history", severity=Severity.SKIPPED.value)

    intent = entry.get("intent", entry.get("type", ""))
    if intent in ("bug", "fix"):
        return CheckResult(name, True, f"intent={intent}, architecture update unlikely")

    arch = project_root / ".shipwright" / "agent_docs" / "architecture.md"
    if not arch.exists():
        return CheckResult(
            name, False, "architecture.md missing",
            severity=Severity.WARNING.value,
        )

    reference_mtime = _freshness_mtime_reference(project_root, run_id)
    if reference_mtime is None:
        return CheckResult(name, None, "no iterate entry file or run_config", severity=Severity.SKIPPED.value)
    if arch.stat().st_mtime >= reference_mtime:
        return CheckResult(name, True, "architecture.md is fresh")

    return CheckResult(
        name, False,
        f"architecture.md may need update (intent={intent}, arch older than iterate entry)",
        severity=Severity.WARNING.value,
    )


def check_conventions_reviewed(
    project_root: Path,
    run_id: str,
) -> CheckResult:
    """Non-canon warning: conventions.md may need update after feature iterates."""
    name = "conventions.md reviewed"
    entry = find_entry_by_run_id(project_root, run_id)
    if not entry:
        return CheckResult(name, None, "run_id not in history", severity=Severity.SKIPPED.value)

    intent = entry.get("intent", entry.get("type", ""))
    if intent in ("bug", "fix"):
        return CheckResult(name, True, f"intent={intent}, conventions update unlikely")

    conv = project_root / ".shipwright" / "agent_docs" / "conventions.md"
    if not conv.exists():
        return CheckResult(
            name, False, "conventions.md missing",
            severity=Severity.WARNING.value,
        )

    reference_mtime = _freshness_mtime_reference(project_root, run_id)
    if reference_mtime is None:
        return CheckResult(name, None, "no iterate entry file or run_config", severity=Severity.SKIPPED.value)
    if conv.stat().st_mtime >= reference_mtime:
        return CheckResult(name, True, "conventions.md is fresh")

    return CheckResult(
        name, False,
        f"conventions.md may need update (intent={intent}, conventions older than iterate entry)",
        severity=Severity.WARNING.value,
    )


def check_surface_verification(project_root: Path, run_id: str) -> CheckResult:
    """F0.5 audit — ``shipwright_test_results.json.iterate_latest`` carries a
    well-formed ``surface_verification`` block.

    The post-commit second layer behind the production-time gate in
    ``shared/scripts/surface_verification.py``. Skipped at trivial/small
    complexity (the gate's safety floor enforces those at the prose level).
    Severity ERROR — fails ``--strict`` and default both.

    Fail-closed conditions (mirror of SKILL.md F0.5):

    1. medium+ iterate but no ``surface_verification`` block (silent regression).
    2. ``surface != "none"`` and ``tests_run == 0`` (greedy-filter trap).
    3. ``surface != "none"`` and ``exit_code != 0`` (runner failed after retries).
    4. ``surface == "none"`` with empty / missing ``justification``.

    A missing or malformed ``shipwright_test_results.json`` at medium+ is
    itself a failure — the F5 step is mandatory and produces the file.
    """
    name = "F0.5 surface_verification block valid"

    entry = find_entry_by_run_id(project_root, run_id)
    complexity = (entry or {}).get("complexity", "")
    if complexity not in ("medium", "large"):
        return CheckResult(
            name, True,
            f"skipped (complexity={complexity or 'unknown'})",
            severity=Severity.SKIPPED.value,
        )

    results_path = project_root / "shipwright_test_results.json"
    if not results_path.exists():
        return CheckResult(
            name, False,
            "shipwright_test_results.json missing — F5 did not run",
        )
    try:
        results = json.loads(results_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return CheckResult(
            name, False,
            f"shipwright_test_results.json malformed: {exc}",
        )

    iterate_latest = (results or {}).get("iterate_latest", {})
    block = iterate_latest.get("surface_verification") if isinstance(iterate_latest, dict) else None
    if not isinstance(block, dict):
        return CheckResult(
            name, False,
            "iterate_latest.surface_verification missing for medium+ iterate",
        )

    surface = block.get("surface")
    if surface not in ("web", "cli", "api", "none"):
        return CheckResult(
            name, False,
            f"surface={surface!r} not one of web/cli/api/none",
        )

    if surface == "none":
        justification = (block.get("justification") or "").strip()
        if not justification:
            return CheckResult(
                name, False,
                "surface=none requires non-empty justification",
            )
        return CheckResult(
            name, True,
            f"surface=none, justification recorded ({len(justification)} chars)",
        )

    exit_code = block.get("exit_code")
    tests_run = block.get("tests_run")
    if not isinstance(tests_run, int) or tests_run <= 0:
        return CheckResult(
            name, False,
            f"surface={surface}, tests_run={tests_run!r} (must be > 0)",
        )
    if exit_code != 0:
        return CheckResult(
            name, False,
            f"surface={surface}, exit_code={exit_code!r} (runner failed after retries)",
        )
    return CheckResult(
        name, True,
        f"surface={surface}, tests_run={tests_run}, exit_code=0",
    )


def check_migration_quarantine_empty(project_root: Path) -> CheckResult:
    """Advisory warn — flag if iterate_history migration quarantined any entries.

    Loud signal on the operator's console so quarantined losses don't go
    unnoticed. Does not fail the check so follow-on work can proceed.
    """
    name = "iterate migration quarantine empty"
    cfg = project_root / "shipwright_run_config.json"
    if not cfg.exists():
        return CheckResult(name, None, "no run_config", severity=Severity.SKIPPED.value)
    try:
        data = json.loads(cfg.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return CheckResult(name, None, "malformed run_config", severity=Severity.SKIPPED.value)

    count = data.get(MIGRATION_QUARANTINED_COUNT_KEY, 0)
    if not isinstance(count, int) or count == 0:
        return CheckResult(name, True, "no quarantined legacy entries")

    report = data.get("_iterate_migration_quarantine_report", "<no report path>")
    return CheckResult(
        name, False,
        f"{count} legacy iterate entries quarantined during migration — see {report}",
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
        check_changelog_unreleased(project_root, run_id=run_id),
        check_session_handoff_fresh(project_root),
        check_build_dashboard_has_run_id(project_root, run_id, commit_hash=commit_hash or None),
        check_surface_verification(project_root, run_id),
    ]


def run_cross_artifact_checks(
    project_root: Path,
    run_id: str,
) -> list[CheckResult]:
    """Non-canon advisory checks — called by Stop hook for drift detection."""
    return [
        check_compliance_reflects_run_id(project_root, run_id),
        check_architecture_reviewed(project_root, run_id),
        check_conventions_reviewed(project_root, run_id),
        check_migration_quarantine_empty(project_root),
    ]
