"""Build-phase verifier checks (iterate 12.3 — canon hybrid).

Build is the only phase whose canon granularity is NOT uniform:

- **C1 (record_event), C2 (build_dashboard), C4 (ADR)** run **per
  section** (existing pre-12.3 behaviour, unchanged). The verifier
  iterates every ``build_config.sections[].status == "complete"`` and
  expects a matching ``work_completed`` event, dashboard mention, and
  ADR body reference for each section name.
- **C3 (session_handoff), C5 (CHANGELOG Unreleased), phase_history**
  run **once per split completion** (iterate 12.3 addition). The
  verifier checks that the split-level handoff is fresh, that the
  CHANGELOG has at least one bullet for each completed section in the
  current split, and that ``phase_history[build]`` has an entry for
  the current run id.

Preventive check-plan imports:

- ``check_build_test_files_exist`` — shipwright-check plan Group B3:
  every ``build_config.sections[].test_file`` (or ``test_files``) must
  exist on disk after that section completes. Catches tests that were
  referenced but never written.
- ``check_commit_sha_in_git`` — shipwright-check plan Group B6: every
  recorded ``sections[].commit`` sha must be reachable via
  ``git cat-file -e``. Catches history rewrites early.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from .common import (
    CheckResult,
    Severity,
    check_adr_ids_sequential,
    check_adr_status_valid,
    check_adr_supersession_exists,
    check_c2_dashboard_reflects_phase,
    check_c3_session_handoff_fresh_after_phase,
    check_phase_history_has_run,
    find_changelog,
    read_events_jsonl,
    read_run_config,
)


# ---------------------------------------------------------------------------
# build_config readers
# ---------------------------------------------------------------------------

def _read_build_config(project_root: Path) -> dict:
    path = project_root / "shipwright_build_config.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _completed_sections(project_root: Path) -> list[dict]:
    """Return ``build_config.sections`` entries whose status == 'complete'.

    Uses the *current* sections list, not the archived
    ``split_NN_sections`` buckets — the canon verifier runs at split
    completion and the current sections array is authoritative for that
    split. Archived buckets are a historical audit trail only.
    """
    cfg = _read_build_config(project_root)
    sections = cfg.get("sections") or []
    return [
        s for s in sections
        if isinstance(s, dict) and s.get("status") == "complete"
    ]


# ---------------------------------------------------------------------------
# Phase-own checks
# ---------------------------------------------------------------------------

def check_all_sections_complete(project_root: Path) -> CheckResult:
    """Every section in the current split's ``sections`` array must have
    ``status == 'complete'``. Mirrors the legacy ``_validate_build``
    pre-canon gate so the modular verifier can stand alone.
    """
    name = "all current-split sections complete"
    cfg = _read_build_config(project_root)
    sections = cfg.get("sections") or []
    if not sections:
        return CheckResult(
            name, False,
            "shipwright_build_config.json has no sections — was /shipwright-build run?",
        )
    incomplete = [s.get("name", "?") for s in sections if s.get("status") != "complete"]
    if incomplete:
        return CheckResult(name, False, f"incomplete sections: {incomplete}")
    return CheckResult(name, True, f"{len(sections)} section(s), all complete")


def check_build_test_files_exist(project_root: Path) -> CheckResult:
    """Every ``test_file`` / ``test_files`` entry referenced by a
    completed section must exist on disk.

    Adapted from shipwright-check plan Group B3 (preventive). The
    section state file shape varies across build versions, so this
    check is tolerant: both ``test_file: "path"`` and
    ``test_files: ["path", ...]`` work, and either key missing means
    the section didn't declare test files (not a failure — some
    refactor-only sections legitimately have none).
    """
    name = "B3 build section test files exist on disk"
    sections = _completed_sections(project_root)
    if not sections:
        return CheckResult(name, True, "no complete sections to check")

    missing: list[str] = []
    checked_count = 0
    for sec in sections:
        test_paths: list[str] = []
        if isinstance(sec.get("test_file"), str):
            test_paths.append(sec["test_file"])
        if isinstance(sec.get("test_files"), list):
            test_paths.extend(p for p in sec["test_files"] if isinstance(p, str))
        if not test_paths:
            continue
        section_name = sec.get("name", "?")
        for tp in test_paths:
            checked_count += 1
            full = project_root / tp
            if not full.exists():
                missing.append(f"{section_name}:{tp}")

    if missing:
        return CheckResult(
            name, False,
            f"{len(missing)} missing test file(s): {missing[:3]}"
            + (" ..." if len(missing) > 3 else ""),
        )
    if checked_count == 0:
        return CheckResult(
            name, True,
            "sections declared no test files — nothing to check",
        )
    return CheckResult(
        name, True,
        f"{checked_count} test file(s) across {len(sections)} section(s) all present",
    )


def check_commit_sha_in_git(project_root: Path) -> CheckResult:
    """Every recorded ``section.commit`` SHA must be reachable via
    ``git cat-file -e``.

    Adapted from shipwright-check plan Group B6 (preventive). Catches
    history rewrites early: if a user rebases, squashes, or
    force-pushes after a section completed, the section's recorded
    commit vanishes and downstream compliance reports drift.
    Sections without a ``commit`` field are skipped — they haven't
    been committed yet or are pre-iterate-11 entries.
    """
    name = "B6 section commits reachable in git"
    sections = _completed_sections(project_root)
    to_check = [
        (s.get("name", "?"), s["commit"])
        for s in sections
        if isinstance(s.get("commit"), str) and s["commit"]
    ]
    if not to_check:
        return CheckResult(name, True, "no section commits to verify")

    missing: list[str] = []
    for section_name, sha in to_check:
        try:
            result = subprocess.run(
                ["git", "cat-file", "-e", sha],
                cwd=str(project_root),
                capture_output=True,
                text=True,
                timeout=10,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return CheckResult(
                name, False,
                f"git cat-file failed: {exc}",
                severity=Severity.WARNING.value,
            )
        if result.returncode != 0:
            missing.append(f"{section_name}:{sha[:8]}")

    if missing:
        return CheckResult(
            name, False,
            f"{len(missing)} commit(s) not reachable: {missing[:3]}"
            + (" ..." if len(missing) > 3 else ""),
        )
    return CheckResult(name, True, f"{len(to_check)} section commit(s) reachable")


# ---------------------------------------------------------------------------
# Per-section canon checks (C1 event + C4 ADR)
# ---------------------------------------------------------------------------

def check_per_section_work_completed_events(project_root: Path) -> CheckResult:
    """C1 (hybrid): every completed section must have at least one
    ``work_completed`` event in ``shipwright_events.jsonl`` whose
    ``source == 'build'`` and ``section == <section name>``.

    Missing events here mean the build plugin's Step 10 ``record_event``
    call didn't fire — the run-state verifier would otherwise silently
    lose the per-section audit trail.
    """
    name = "C1 per-section work_completed events recorded"
    sections = _completed_sections(project_root)
    if not sections:
        return CheckResult(name, True, "no complete sections to check")

    events = read_events_jsonl(project_root)
    recorded: set[str] = set()
    for ev in events:
        if ev.get("type") != "work_completed":
            continue
        if ev.get("source") != "build":
            continue
        section = ev.get("section")
        if isinstance(section, str) and section:
            recorded.add(section)

    missing = [s["name"] for s in sections if s.get("name") not in recorded]
    if missing:
        return CheckResult(
            name, False,
            f"{len(missing)} section(s) without work_completed event: {missing[:3]}"
            + (" ..." if len(missing) > 3 else ""),
        )
    return CheckResult(
        name, True,
        f"{len(sections)} section(s) each have work_completed event",
    )


def check_per_section_adr_recorded(project_root: Path) -> CheckResult:
    """C4 (hybrid): every completed section must have an ADR in
    ``decision_log.md`` whose header or body references the section
    name. The build plugin's Step 9 calls ``write_decision_log.py
    --section <name>`` which writes ``**Section:** <name>`` inline;
    we grep for any occurrence of the section name as a whole word
    inside a bullet marked ``Section`` or in the header title.
    """
    name = "C4 per-section ADR recorded in decision_log"
    sections = _completed_sections(project_root)
    if not sections:
        return CheckResult(name, True, "no complete sections to check")

    log_path = project_root / ".shipwright" / "agent_docs" / "decision_log.md"
    if not log_path.exists():
        return CheckResult(name, False, ".shipwright/agent_docs/decision_log.md missing")
    try:
        log_body = log_path.read_text(encoding="utf-8", errors="ignore")
    except OSError as exc:
        return CheckResult(name, False, f"read error: {exc}")

    missing: list[str] = []
    for sec in sections:
        section_name = sec.get("name", "")
        if not section_name:
            continue
        # Match "**Section:** <name>" (write_decision_log's canonical
        # form), or the section name inside an ADR header line.
        pattern = re.compile(
            rf"\*\*Section:\*\*[^\n]*{re.escape(section_name)}|"
            rf"^###?\s+ADR-\d+[^\n]*{re.escape(section_name)}",
            re.MULTILINE,
        )
        if not pattern.search(log_body):
            missing.append(section_name)

    if missing:
        return CheckResult(
            name, False,
            f"{len(missing)} section(s) without ADR reference: {missing[:3]}"
            + (" ..." if len(missing) > 3 else ""),
        )
    return CheckResult(
        name, True,
        f"{len(sections)} section(s) each have ADR reference",
    )


# ---------------------------------------------------------------------------
# Phase-level canon checks (C5 per-section CHANGELOG matching)
# ---------------------------------------------------------------------------

_UNRELEASED_RE = re.compile(
    r"## \[Unreleased\][^\n]*\n(.*?)(?=\n## \[|\Z)",
    re.DOTALL,
)


def check_c5_changelog_has_bullet_per_section(project_root: Path) -> CheckResult:
    """C5 (hybrid): every completed section of the current split must
    have a bullet in ``CHANGELOG.md [Unreleased]`` that mentions the
    section name.

    The helper-written bullets use the format
    ``Build: <split>/<section_name> complete (...)`` (see the build
    plugin's Step 10 canon block); we substring-match the section name
    anywhere in ``[Unreleased]``. This is coarse by design — manual
    edits that rename a section bullet still pass, and the build
    plugin dedupes via ``append_changelog_entry.py``.
    """
    name = "C5 CHANGELOG [Unreleased] has bullet per section"
    sections = _completed_sections(project_root)
    if not sections:
        return CheckResult(name, True, "no complete sections to check")

    changelog = find_changelog(project_root)
    if changelog is None:
        return CheckResult(
            name, False, "CHANGELOG.md not found",
            severity=Severity.WARNING.value,
        )
    try:
        content = changelog.read_text(encoding="utf-8", errors="ignore")
    except OSError as exc:
        return CheckResult(name, False, f"read error: {exc}")

    m = _UNRELEASED_RE.search(content)
    if not m:
        return CheckResult(name, False, "no [Unreleased] section in CHANGELOG.md")
    unreleased = m.group(1)

    missing = [
        s["name"] for s in sections
        if isinstance(s.get("name"), str)
        and s["name"] not in unreleased
    ]
    if missing:
        return CheckResult(
            name, False,
            f"{len(missing)} section(s) without CHANGELOG bullet: {missing[:3]}"
            + (" ..." if len(missing) > 3 else ""),
        )
    return CheckResult(
        name, True,
        f"{len(sections)} section(s) each have CHANGELOG bullet",
    )


# ---------------------------------------------------------------------------
# phase_history with sections sub-array
# ---------------------------------------------------------------------------

def check_phase_history_build_has_sections(
    project_root: Path,
    run_id: str,
) -> CheckResult:
    """Extends ``check_phase_history_has_run`` for build: the entry for
    the current ``run_id`` must also contain a ``sections`` array
    matching ``build_config.sections[].name``.
    """
    name = "phase_history[build] entry has sections array"
    if not run_id:
        return CheckResult(name, True, "skipped (no --run-id supplied)")

    data = read_run_config(project_root)
    if not data:
        return CheckResult(name, False, "shipwright_run_config.json missing or malformed")
    history = data.get("phase_history") or {}
    bucket = history.get("build") if isinstance(history, dict) else None
    if not isinstance(bucket, list):
        return CheckResult(name, False, "phase_history[build] missing")

    entry = next((e for e in bucket if e.get("run_id") == run_id), None)
    if not entry:
        return CheckResult(name, False, f"run_id={run_id} not in phase_history[build]")

    sections = entry.get("sections")
    if not isinstance(sections, list) or not sections:
        return CheckResult(
            name, False,
            f"phase_history[build][{run_id}] has no sections array",
        )

    completed = {s.get("name") for s in _completed_sections(project_root)}
    recorded = {s.get("id") for s in sections if isinstance(s, dict)}
    missing = sorted(completed - recorded)
    if missing:
        return CheckResult(
            name, False,
            f"phase_history missing completed sections: {missing[:3]}"
            + (" ..." if len(missing) > 3 else ""),
        )
    return CheckResult(
        name, True,
        f"phase_history[build][{run_id}] has {len(sections)} section entry(ies)",
    )


# ---------------------------------------------------------------------------
# Canon dispatcher
# ---------------------------------------------------------------------------

def run_build_checks(
    project_root: Path,
    *,
    run_id: str = "",
) -> list[CheckResult]:
    """Run the full build-phase verifier suite in stable order."""
    results: list[CheckResult] = []

    # Phase-own
    results.append(check_all_sections_complete(project_root))
    results.append(check_build_test_files_exist(project_root))
    results.append(check_commit_sha_in_git(project_root))

    # Per-section canon (C1 + C4)
    results.append(check_per_section_work_completed_events(project_root))
    results.append(check_per_section_adr_recorded(project_root))

    # Phase-level canon (C2 + C3 + C5)
    results.append(check_c2_dashboard_reflects_phase(project_root, "build"))
    results.append(check_c3_session_handoff_fresh_after_phase(project_root, "build"))
    results.append(check_c5_changelog_has_bullet_per_section(project_root))

    # Phase history (standard + build-specific sub-array check)
    results.append(check_phase_history_has_run(project_root, "build", run_id))
    results.append(check_phase_history_build_has_sections(project_root, run_id))

    # ADR integrity (phase-agnostic)
    results.append(check_adr_ids_sequential(project_root))
    results.append(check_adr_status_valid(project_root))
    results.append(check_adr_supersession_exists(project_root))

    return results


def run_all_checks(project_root: Path, run_id: str = "") -> list[CheckResult]:
    return run_build_checks(project_root, run_id=run_id)


__all__ = [
    "Severity",
    "check_all_sections_complete",
    "check_build_test_files_exist",
    "check_c5_changelog_has_bullet_per_section",
    "check_commit_sha_in_git",
    "check_per_section_adr_recorded",
    "check_per_section_work_completed_events",
    "check_phase_history_build_has_sections",
    "run_all_checks",
    "run_build_checks",
]
