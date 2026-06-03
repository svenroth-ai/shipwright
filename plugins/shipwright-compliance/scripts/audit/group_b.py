"""Group B — Config ↔ Config ↔ Event-log coherence (plan v7 Step 5).

Mix of detective-only checks and preventive re-runs. The detector calls
``run()`` once per audit invocation; each B* check is independent and
crashes are isolated so one broken check doesn't drop the rest of the
group.

Detective-only:
- B1: project_config splits with status="complete" must have ≥1 section
  recorded in plan_config.
- B2: every section recorded in plan_config has a section file under
  ``.shipwright/planning/<split>/sections/``.
- B4: every project split with status="complete" has a ``split_completed``
  event in shipwright_events.jsonl.
- B5: every ``phase_completed`` event has a matching task in
  ``run_config.completed_phase_task_ids``.
- B7: reverse git-log scan since the latest release tag — every commit
  must have at least one matching event after Rules A/B/C exclusions.

Preventive re-runs (consistent with Group C/F pattern, source =
``preventive-rerun``):
- B3: section test files exist on disk
  (reuses ``check_build_test_files_exist`` from iterate-12 build_checks).
- B6: section commit SHAs reachable in git
  (reuses ``check_commit_sha_in_git``).
"""

from __future__ import annotations

import glob as _glob
import json
from pathlib import Path
from typing import Any, Callable

from scripts.audit.audit_adapters import (
    SOURCE_DETECTIVE_ONLY,
    SOURCE_PREVENTIVE_RERUN,
    Finding,
    check_result_to_finding,
    import_iterate12_checks,
)
from scripts.audit import git_log_scan


# ---------------------------------------------------------------------------
# Suggested-iterate hint
# ---------------------------------------------------------------------------

def _suggest(check_id: str, label: str) -> str:
    return (
        f"/shipwright-iterate --type change "
        f"\"reconcile {check_id} ({label}) "
        f"— see .shipwright/compliance/audit-report.md\""
    )


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------


def _load_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _load_events(project_root: Path) -> list[dict] | None:
    path = project_root / "shipwright_events.jsonl"
    if not path.exists():
        return None
    out: list[dict] = []
    try:
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    except OSError:
        return None
    return out


# ---------------------------------------------------------------------------
# B1 — splits with status=complete must have sections recorded
# ---------------------------------------------------------------------------


def _check_b1(project_root: Path) -> tuple[str, str, list[str]]:
    project_cfg = _load_json(project_root / "shipwright_project_config.json")
    if project_cfg is None:
        return "skip", "no shipwright_project_config.json", []
    plan_cfg = _load_json(project_root / "shipwright_plan_config.json") or {}

    splits = project_cfg.get("splits", []) or []
    complete_splits = [
        s.get("name") for s in splits
        if isinstance(s, dict) and s.get("status") == "complete" and s.get("name")
    ]
    if not complete_splits:
        return "skip", "no splits with status=complete in project_config", []

    plan_splits = plan_cfg.get("splits", {})
    if not isinstance(plan_splits, dict):
        plan_splits = {}

    issues: list[str] = []
    for split_name in complete_splits:
        entry = plan_splits.get(split_name)
        if entry is None:
            issues.append(f"{split_name}: missing in plan_config.splits")
            continue
        if not isinstance(entry, dict):
            issues.append(f"{split_name}: plan_config entry is not an object")
            continue
        sections = entry.get("sections")
        section_count = _section_count(sections)
        if section_count == 0:
            issues.append(f"{split_name}: zero sections recorded")

    if not issues:
        return "pass", f"{len(complete_splits)} complete split(s) all have sections", []
    detail = "; ".join(issues[:3])
    if len(issues) > 3:
        detail += f"; (+{len(issues) - 3} more)"
    return "fail", detail, issues


def _section_count(sections: Any) -> int:
    """Return a non-negative section count.

    Negative integers (defensive) are treated as 0 — the spec
    requires ``≥1 section recorded``, so a hypothetical malformed
    ``sections: -1`` should not silently pass B1.
    """
    if isinstance(sections, int):
        return max(sections, 0)
    if isinstance(sections, list):
        return len(sections)
    return 0


# ---------------------------------------------------------------------------
# B2 — plan_config sections → section files on disk
# ---------------------------------------------------------------------------


def _check_b2(project_root: Path) -> tuple[str, str, list[str]]:
    plan_cfg = _load_json(project_root / "shipwright_plan_config.json")
    if plan_cfg is None:
        return "skip", "no shipwright_plan_config.json", []

    splits = plan_cfg.get("splits", {})
    if not isinstance(splits, dict):
        return "skip", "plan_config.splits is not an object", []

    found_listed_sections = False
    issues: list[str] = []
    for split_name, entry in splits.items():
        if not isinstance(entry, dict):
            continue
        sections = entry.get("sections")
        # Only list-shaped section arrays are checkable. Aiportal-style
        # ``sections: 8`` (count) doesn't tell us section IDs, so we
        # skip those here.
        if not isinstance(sections, list):
            continue
        for section in sections:
            if not isinstance(section, dict):
                continue
            section_id = section.get("id") or section.get("name")
            if not isinstance(section_id, str):
                continue
            found_listed_sections = True
            section_dir = project_root / ".shipwright" / "planning" / split_name / "sections"
            # ``glob.escape`` keeps any glob-metacharacters inside the
            # section id (``[``, ``*``) as literals — defensive against
            # ids that aren't strictly ``\w+``-shaped.
            safe_id = _glob.escape(section_id)
            # Match either ``<id>.md`` exactly or ``<id>-*.md`` with suffix.
            candidates = list(section_dir.glob(f"{safe_id}.md"))
            candidates.extend(section_dir.glob(f"{safe_id}-*.md"))
            if not candidates:
                issues.append(f"{split_name}/{section_id}: no section file")

    if not found_listed_sections:
        return "skip", "no listed section IDs in plan_config (counts only?)", []
    if not issues:
        return "pass", "every recorded section has a file on disk", []
    detail = "; ".join(issues[:3])
    if len(issues) > 3:
        detail += f"; (+{len(issues) - 3} more)"
    return "fail", detail, issues


# ---------------------------------------------------------------------------
# B3 + B6 — preventive re-runs
# ---------------------------------------------------------------------------


_PREVENTIVE: tuple[tuple[str, str, str], ...] = (
    # (iterate12_fn_name, audit_check_id, human_label)
    ("check_build_test_files_exist", "B3",
     "Section test files exist on disk"),
    ("check_commit_sha_in_git", "B6",
     "Section commits reachable in git"),
)


def _run_preventive(project_root: Path) -> list[Finding]:
    """Run B3 + B6 by adapting iterate-12 CheckResults into Findings."""
    try:
        checks = import_iterate12_checks()
    except Exception as exc:  # noqa: BLE001
        # Hard import failure → emit fail-findings for both, severity HIGH.
        return [
            _preventive_fail(check_id, label, exc)
            for _, check_id, label in _PREVENTIVE
        ]

    out: list[Finding] = []
    for fn_name, check_id, label in _PREVENTIVE:
        fn = checks.get(fn_name)
        if fn is None:
            out.append(_preventive_fail(
                check_id, label,
                RuntimeError(f"iterate-12 symbol missing: {fn_name}"),
            ))
            continue
        try:
            result = fn(project_root)
        except Exception as exc:  # noqa: BLE001 — crash isolation
            out.append(_preventive_fail(check_id, label, exc))
            continue
        finding = check_result_to_finding(
            result,
            group="B", check_id=check_id,
            source=SOURCE_PREVENTIVE_RERUN,
            suggested_iterate_cmd=(
                _suggest(check_id, label)
                if getattr(result, "ok", None) is False else None
            ),
        )
        finding.name = label
        out.append(finding)
    return out


def _preventive_fail(check_id: str, label: str, exc: BaseException) -> Finding:
    return Finding(
        group="B", check_id=check_id, name=label,
        severity="HIGH", source=SOURCE_PREVENTIVE_RERUN, status="fail",
        detail=f"check raised {type(exc).__name__}: {exc}",
    )


# ---------------------------------------------------------------------------
# B4 — completed splits ↔ split_completed events
# ---------------------------------------------------------------------------


def _check_b4(project_root: Path) -> tuple[str, str, list[str]]:
    project_cfg = _load_json(project_root / "shipwright_project_config.json")
    if project_cfg is None:
        return "skip", "no shipwright_project_config.json", []
    splits = project_cfg.get("splits", []) or []
    complete = [
        s.get("name") for s in splits
        if isinstance(s, dict) and s.get("status") == "complete" and s.get("name")
    ]
    if not complete:
        return "skip", "no splits with status=complete", []

    events = _load_events(project_root)
    if events is None:
        return "skip", "shipwright_events.jsonl not present", []

    seen_split_completed: set[str] = set()
    for ev in events:
        if ev.get("type") != "split_completed":
            continue
        name = ev.get("split")
        if isinstance(name, str):
            seen_split_completed.add(name)

    missing = [name for name in complete if name not in seen_split_completed]
    if not missing:
        return "pass", f"{len(complete)} complete split(s) all have events", []
    detail = "missing split_completed event for: " + ", ".join(missing[:3])
    if len(missing) > 3:
        detail += f", (+{len(missing) - 3} more)"
    return "fail", detail, missing


# ---------------------------------------------------------------------------
# B5 — phase_completed events ↔ completed_phase_task_ids
# ---------------------------------------------------------------------------


def _check_b5(project_root: Path) -> tuple[str, str, list[str]]:
    run_cfg = _load_json(project_root / "shipwright_run_config.json")
    if run_cfg is None:
        return "skip", "no shipwright_run_config.json", []

    if run_cfg.get("schemaVersion") != 2:
        return "skip", "run_config schemaVersion != 2 (no phase_tasks shape)", []

    phase_tasks = run_cfg.get("phase_tasks", [])
    completed_ids = set(run_cfg.get("completed_phase_task_ids", []) or [])

    events = _load_events(project_root)
    if events is None:
        return "skip", "shipwright_events.jsonl not present", []

    completed_events = [ev for ev in events if ev.get("type") == "phase_completed"]
    if not completed_events:
        return "skip", "no phase_completed events recorded", []

    # Build a phase → ids index from phase_tasks.
    phase_to_task_ids: dict[str, list[str]] = {}
    for task in phase_tasks:
        if not isinstance(task, dict):
            continue
        phase = task.get("phase")
        task_id = task.get("id")
        if isinstance(phase, str) and isinstance(task_id, str):
            phase_to_task_ids.setdefault(phase, []).append(task_id)

    # For every phase referenced by a phase_completed event, at least
    # one task with that phase must be in completed_phase_task_ids.
    issues: list[str] = []
    for ev in completed_events:
        phase = ev.get("phase") or ev.get("source")
        if not isinstance(phase, str):
            continue
        candidate_ids = phase_to_task_ids.get(phase, [])
        if not candidate_ids:
            issues.append(
                f"phase={phase}: no phase_tasks entry in run_config",
            )
            continue
        if not any(tid in completed_ids for tid in candidate_ids):
            issues.append(
                f"phase={phase}: event says complete, "
                f"completed_phase_task_ids has none of {candidate_ids}",
            )

    if not issues:
        return "pass", "every phase_completed event has a matching task", []
    detail = "; ".join(issues[:2])
    if len(issues) > 2:
        detail += f"; (+{len(issues) - 2} more)"
    return "fail", detail, issues


def _sha_match(commit_sha: str, tracked: set[str]) -> bool:
    """Return True when ``commit_sha`` is in ``tracked`` (full or prefix).

    Full-SHA equality first (cheap set lookup); falls back to prefix
    matching to tolerate abbreviated SHAs in hand-edited event logs.
    Prefixes shorter than 7 hex chars are rejected to prevent
    false-positive matches.
    """
    if commit_sha in tracked:
        return True
    for tracked_sha in tracked:
        if len(tracked_sha) < 7:
            continue
        if commit_sha.startswith(tracked_sha):
            return True
    return False


# ---------------------------------------------------------------------------
# B7 — Reverse git-log scan with retention rules
# ---------------------------------------------------------------------------


def _check_b7(
    project_root: Path,
    config: dict,
) -> tuple[str, str, list[str]]:
    if not git_log_scan.is_git_repo(project_root):
        return "skip", "not a git repository", []

    exclusions = config.get("b7_exclusions", {}) or {}
    retention = config.get("retention", {}) or {}
    pattern = exclusions.get("last_release_tag_pattern", "v*")

    tag = git_log_scan.latest_release_tag(project_root, pattern)
    if tag is None:
        return "skip", f"no release tag matching '{pattern}' (no baseline)", []

    commits = git_log_scan.commits_since_tag(project_root, tag)
    if isinstance(commits, git_log_scan.ScanError):
        # Operational git failure (broken repo, permission denied) — fail
        # loud rather than silently skip. Suppressing the audit on a
        # broken `git log` would mask whatever drift the operator wanted
        # to detect.
        return "fail", f"git log failed: {commits.detail}", [commits.detail]
    if not commits:
        return "pass", f"no commits since {tag}", []

    # Build a set of event-tracked commit identifiers. We accept either
    # full or abbreviated SHAs in the event log: callers normally use
    # `git rev-parse HEAD` (full 40 chars), but a hand-edited event log
    # could carry an abbreviated form. ``_sha_match`` below resolves
    # via prefix when needed.
    events = _load_events(project_root) or []
    tracked: set[str] = set()
    tracked_run_ids: set[str] = set()
    for ev in events:
        sha = ev.get("commit")
        if isinstance(sha, str) and sha:
            tracked.add(sha)
        # Since iterate-2026-05-29-events-jsonl-worktree-commit a work_completed
        # event ships commit:"" and links to its commit via the F6 commit's
        # Run-ID: footer ↔ the event's adr_id. Collect adr_ids so a commit whose
        # Run-ID trailer matches a recorded event still counts as covered even
        # when the event carries no SHA (C1, 2026-06-02-compliance-detective-realign).
        adr_id = ev.get("adr_id")
        if isinstance(adr_id, str) and adr_id:
            tracked_run_ids.add(adr_id)

    uncovered: list[tuple[str, str]] = []  # (sha, reason-or-empty)
    excluded_count = 0
    for sha in commits:
        info = git_log_scan.commit_info(project_root, sha)
        if isinstance(info, git_log_scan.ScanError):
            # Soft-skip individual unreadable commits — don't fail the
            # whole audit on one corrupt entry.
            continue
        result = git_log_scan.apply_retention_rules(
            info, exclusions=exclusions, retention=retention,
        )
        if result.excluded:
            excluded_count += 1
            continue
        if _sha_match(sha, tracked):
            continue
        # Fallback for the worktree-commit flow: the event carries no SHA but
        # links via Run-ID footer ↔ adr_id. Only pay the extra git call when the
        # cheap SHA-set lookup missed.
        run_id = git_log_scan.commit_run_id(project_root, sha)
        if run_id and run_id in tracked_run_ids:
            continue
        uncovered.append((sha, ""))

    if not uncovered:
        if excluded_count:
            return "pass", (
                f"{len(commits)} commit(s) since {tag} "
                f"({excluded_count} excluded by Rules A/B/C, "
                f"{len(commits) - excluded_count} matched events)"
            ), []
        return "pass", f"every commit since {tag} has a matching event", []

    detail = (
        f"{len(uncovered)} commit(s) since {tag} have no matching event: "
        + ", ".join(sha[:8] for sha, _ in uncovered[:5])
    )
    if len(uncovered) > 5:
        detail += f", (+{len(uncovered) - 5} more)"
    evidence = [f"{sha} (no event with this commit)" for sha, _ in uncovered]
    return "fail", detail, evidence


# ---------------------------------------------------------------------------
# Top-level run()
# ---------------------------------------------------------------------------


_DETECTIVE_NAME_BY_ID = {
    "B1": "Splits-complete have plan_config sections",
    "B2": "plan_config sections have files on disk",
    "B4": "Completed splits have split_completed events",
    "B5": "phase_completed events match completed_phase_task_ids",
    "B7": "Every commit since release tag has a matching event",
}

_DETECTIVE_SEVERITY_BY_ID = {
    "B1": "HIGH", "B2": "HIGH", "B4": "HIGH", "B5": "HIGH", "B7": "MEDIUM",
}


def run(
    project_root: Path,
    config: dict[str, Any] | None,
    _data: Any,
) -> list[Finding]:
    """Run B1-B7 and return Findings (B-ordered: B1 B2 B3 B4 B5 B6 B7)."""
    cfg = config or {}
    out: list[Finding] = []

    detective_runners: list[tuple[str, Callable[[], tuple[str, str, list[str]]]]] = [
        ("B1", lambda: _check_b1(project_root)),
        ("B2", lambda: _check_b2(project_root)),
        ("B4", lambda: _check_b4(project_root)),
        ("B5", lambda: _check_b5(project_root)),
        ("B7", lambda: _check_b7(project_root, cfg)),
    ]

    detective_findings: dict[str, Finding] = {}
    for check_id, fn in detective_runners:
        try:
            status, detail, evidence = fn()
        except Exception as exc:  # noqa: BLE001 — crash isolation
            detective_findings[check_id] = Finding(
                group="B", check_id=check_id,
                name=_DETECTIVE_NAME_BY_ID[check_id],
                severity=_DETECTIVE_SEVERITY_BY_ID[check_id],
                source=SOURCE_DETECTIVE_ONLY,
                status="fail",
                detail=f"check raised {type(exc).__name__}: {exc}",
            )
            continue
        detective_findings[check_id] = Finding(
            group="B", check_id=check_id,
            name=_DETECTIVE_NAME_BY_ID[check_id],
            severity=_DETECTIVE_SEVERITY_BY_ID[check_id],
            source=SOURCE_DETECTIVE_ONLY,
            status=status, detail=detail,
            evidence=list(evidence),
            suggested_iterate_cmd=(
                _suggest(check_id, _DETECTIVE_NAME_BY_ID[check_id])
                if status == "fail" else None
            ),
        )

    preventive = {f.check_id: f for f in _run_preventive(project_root)}

    # Emit in canonical B1..B7 order.
    for check_id in ("B1", "B2", "B3", "B4", "B5", "B6", "B7"):
        if check_id in detective_findings:
            out.append(detective_findings[check_id])
        elif check_id in preventive:
            out.append(preventive[check_id])
    return out
