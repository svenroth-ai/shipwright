#!/usr/bin/env python3
"""Stop hook: consolidated phase-quality audit entry point.

Runs all 6 Phase-Quality categories (canon, workflow, infrastructure,
traceability, quality, spec) across every Shipwright plugin's Stop
event. PR 1 of 4 — canon (C1-C5) is implemented; the other categories
are stubbed in :mod:`shared.scripts.lib.phase_quality` and filled in by
PR 2-4.

Contract (plan § 5):

- **Never blocks.** Always exits 0, even on internal errors. The hook
  is observability, not a gate. Orchestrator gating is a separate,
  opt-in Code path (see ``SHIPWRIGHT_ENFORCE_CRITICAL_GATES``).
- **Idempotent.** Repeated invocations with the same
  ``(phase, run_id, session_id)`` triple are no-ops.
- **Greenfield-safe.** Silent no-op when ``project_root`` isn't a
  Shipwright-managed project.
- **Disabled when** ``SHIPWRIGHT_PHASE_QUALITY=0``.

Usage (from a plugin's ``hooks.json``):

    uv run "${CLAUDE_PLUGIN_ROOT}/../../shared/scripts/hooks/audit_phase_quality_on_stop.py"
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

_SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from lib import phase_quality as pq  # noqa: E402
from lib.project_root import resolve_project_root  # noqa: E402


def _resolve_project_root() -> Path:
    try:
        return resolve_project_root()
    except (ValueError, Exception):
        return Path.cwd()


def _emit_hook_output(payload: dict[str, object]) -> None:
    # Stop hookSpecificOutput accepts only `hookEventName`; `additionalContext`
    # is not permitted (validates rejected by Claude Code with
    # "Hook JSON output validation failed — (root): Invalid input").
    # Route the diagnostic message to stderr — Claude Code surfaces hook
    # stderr to the user, so visibility is preserved without violating the
    # Stop schema. See iterate-2026-05-10-stop-hook-schema-fix + ADR-042.
    message = payload.get("additionalContext")
    if message:
        try:
            sys.stderr.write(f"{message}\n")
        except Exception:  # noqa: BLE001
            pass


def _consume_stdin() -> None:
    """Hook protocol sends a JSON payload on stdin; consume + ignore."""
    try:
        json.load(sys.stdin)
    except Exception:  # noqa: BLE001
        pass


def main() -> int:
    _consume_stdin()

    if not pq.phase_quality_enabled():
        return 0

    plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT", "")
    phase = pq.phase_from_plugin_root(plugin_root)
    if not phase:
        # Hook wired into a non-Shipwright plugin — silent no-op.
        return 0

    project_root = _resolve_project_root()

    # Greenfield guard — matches the contract used by the other Stop hooks.
    if not pq.is_shipwright_project(project_root):
        return 0

    # Monorepo auto-descent guard: if the resolver auto-descended into a
    # managed subfolder while the user was actually working at a parent
    # level (monorepo root, unrelated subdir), skip the audit to avoid
    # off-scope pollution. Opt-in for cross-dir audit via
    # SHIPWRIGHT_PROJECT_ROOT env var pointing exactly at project_root.
    cwd = Path.cwd()
    if pq.cwd_is_strict_ancestor_of(cwd, project_root) \
            and not pq.project_root_was_explicitly_selected(project_root):
        return 0

    session_id = os.environ.get("SHIPWRIGHT_SESSION_ID", "").strip() or "unknown"
    run_id = pq.resolve_run_id(project_root, session_id)
    source = pq.resolve_source(project_root, phase)

    if pq.already_audited(project_root, phase, run_id, session_id):
        _emit_hook_output({
            "hookEventName": "Stop",
            "additionalContext": (
                f"[phase-quality] already audited phase={phase} "
                f"run_id={run_id} session={session_id} — skipped"
            ),
        })
        return 0

    started = time.monotonic()
    try:
        findings = {
            "canon": pq.run_canon_checks(phase, project_root),
            "workflow": pq.run_workflow_checks(phase, project_root, run_id),
            "infrastructure": pq.run_infrastructure_checks(phase, project_root),
            "traceability": pq.run_traceability_checks(phase, project_root),
            "quality": pq.run_quality_checks(phase, project_root),
            "spec": pq.run_spec_checks(phase, project_root, run_id),
        }
        finding_path = pq.write_finding_json(
            project_root, phase, run_id, session_id, findings,
            source=source,
        )
        pq.regenerate_all_aggregates(project_root)
        _gc_best_effort(project_root)

        # AC-4 of iterate-2026-05-11-triage-inbox-1a: mirror Tier-1 FAILs
        # into .shipwright/triage.jsonl with (phase, code, commit) dedup
        # so the same finding doesn't flood the inbox across sessions.
        # Best-effort — never blocks the Stop chain.
        _emit_tier1_fails_to_triage(
            project_root, phase, run_id, findings, finding_path,
        )

        totals = _roll_up(findings)
        elapsed_ms = int((time.monotonic() - started) * 1000)

        rel = (
            finding_path.relative_to(project_root)
            if finding_path.is_relative_to(project_root)
            else finding_path
        )
        _emit_hook_output({
            "hookEventName": "Stop",
            "additionalContext": (
                f"[phase-quality] phase={phase} run={run_id} "
                f"pass={totals['PASS']} fail={totals['FAIL']} "
                f"warn={totals['WARN']} skip={totals['SKIP']} "
                f"({elapsed_ms}ms) → {rel}"
            ),
        })
    except Exception as exc:  # noqa: BLE001 — never block Stop chain
        sys.stderr.write(
            f"[audit_phase_quality] Error: {type(exc).__name__}: {exc}\n"
        )
        pq.write_error_finding(project_root, phase, run_id, session_id, exc)
        _emit_hook_output({
            "hookEventName": "Stop",
            "additionalContext": (
                f"[phase-quality] audit failed for phase={phase}: "
                f"{type(exc).__name__}: {exc}"
            ),
        })

    return 0


def _roll_up(findings: dict[str, list[dict[str, object]]]) -> dict[str, int]:
    totals = {
        pq.STATUS_PASS: 0,
        pq.STATUS_FAIL: 0,
        pq.STATUS_WARN: 0,
        pq.STATUS_SKIP: 0,
    }
    for items in findings.values():
        for k, v in pq.count_by_status(items).items():
            totals[k] += v
    return totals


def _gc_best_effort(project_root: Path) -> None:
    try:
        pq.gc_old_findings(project_root)
    except Exception:  # noqa: BLE001
        pass


_GIT_WARN_EMITTED = False  # process-local one-shot guard


def _git_head_sha(project_root: Path) -> str:
    """Return the current HEAD sha. Works on dirty trees.

    Returns ``""`` (empty string, never ``None``) on any failure
    (no-git binary, not a repo, timeout) and emits a one-shot stderr
    warning per process so downstream dedup keys stay shaped
    consistently. The empty-string fallback is the documented spec
    contract (see locked decision "Commit on dirty tree" in
    iterate-2026-05-11-triage-inbox-1a.md).
    """
    import subprocess

    global _GIT_WARN_EMITTED
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(project_root),
            capture_output=True,
            text=True,
            timeout=5,
        )
        if out.returncode == 0:
            return out.stdout.strip()
    except Exception:  # noqa: BLE001
        pass

    if not _GIT_WARN_EMITTED:
        _GIT_WARN_EMITTED = True
        try:
            sys.stderr.write(
                "[phase-quality] git rev-parse HEAD failed; using empty "
                "commit fallback for triage dedup keys\n"
            )
        except Exception:  # noqa: BLE001
            pass
    return ""


def _emit_tier1_fails_to_triage(
    project_root: Path,
    phase: str,
    run_id: str,
    findings: dict[str, list[dict]],
    finding_path: Path | None,
) -> int:
    """Append Tier-1 FAIL findings to .shipwright/triage.jsonl with dedup.

    Best-effort: errors are logged to stderr and swallowed. Returns the
    number of NEW triage items appended (dedup-skipped items not counted).

    Tier-1 FAIL is defined as ``status == "FAIL" AND tier != 2``. Tier-2
    findings are heuristic and intentionally excluded from triage.

    Dedup key = ``f"{phase}:{code}"``. Window: 24h. ``match_commit=True``
    means the same finding on a new commit re-fires (different commit
    is a different "occurrence" — operator can decide whether to
    promote, dismiss, or batch-snooze).
    """
    try:
        from triage import append_triage_item_idempotent  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(
            f"[phase-quality] triage import failed: "
            f"{type(exc).__name__}: {exc}\n"
        )
        return 0

    commit = _git_head_sha(project_root)  # "" on failure (spec contract)
    evidence_rel: str | None = None
    if finding_path is not None:
        try:
            evidence_rel = str(finding_path.relative_to(project_root))
        except ValueError:
            evidence_rel = str(finding_path)

    appended = 0
    for category, items in findings.items():
        for f in items or []:
            if f.get("status") != pq.STATUS_FAIL:
                continue
            if f.get("tier") == 2:
                continue  # Tier-2 = heuristic, not actionable
            code = str(f.get("id") or f.get("name") or category)
            name = str(f.get("name") or code)
            title = f"{phase} {code}: {name}"[:160]
            detail_parts: list[str] = []
            if f.get("evidence"):
                detail_parts.append(str(f["evidence"]))
            if f.get("remediation"):
                detail_parts.append(f"remediation: {f['remediation']}")
            detail = " ".join(detail_parts) or f"{phase} {code} failed"
            try:
                new_id = append_triage_item_idempotent(
                    project_root,
                    source="phaseQuality",
                    severity="high",  # Tier-1 FAIL maps to high → P1
                    kind="bug",
                    title=title,
                    detail=detail,
                    dedup_key=f"{phase}:{code}",
                    evidence_path=evidence_rel,
                    run_id=run_id,
                    commit=commit,
                )
                if new_id is not None:
                    appended += 1
            except Exception as exc:  # noqa: BLE001
                sys.stderr.write(
                    f"[phase-quality] triage emit failed for {code}: "
                    f"{type(exc).__name__}: {exc}\n"
                )
    return appended


if __name__ == "__main__":
    sys.exit(main())
