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

    # Foreign-plugin gate — the audit is only valid from a recognized Shipwright
    # plugin root. An unrecognized root no-ops here, BEFORE the claim below, so a
    # foreign first invocation can never win the claim and block a later
    # recognized one (external-review gpt#2). The plugin-root phase is used ONLY
    # as this recognition gate now; the audited phases come from session state.
    plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT", "")
    if pq.phase_from_plugin_root(plugin_root) is None:
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

    # Once-per-(Stop, session) guard: Claude Code fires this hook from every
    # enabled plugin (no filter), so one Stop invokes it ~11×. Exactly ONE wins
    # and audits; the rest skip — replacing the old per-plugin-root fan-out (11
    # phases audited, 10 never ran). Taken AFTER all no-op guards (a foreign/
    # no-op invocation must not consume the claim). Fail-open + unknown-session
    # handling live in the shared helper.
    from lib.event_once import claim_once_for_event
    if not claim_once_for_event(project_root, "stop-phasequality", session_id):
        return 0

    run_id = pq.resolve_run_id(project_root, session_id)

    # Resolve which phase(s) ran THIS session from SESSION STATE (events.jsonl +
    # run_config), not CLAUDE_PLUGIN_ROOT. Fail-open: unknown/unreadable → ALL
    # canonical phases (audit more, never fewer). One claimed invocation audits
    # each engaged, not-yet-audited phase.
    phases = pq.resolve_engaged_phases(project_root)

    started = time.monotonic()
    audited: list[tuple[str, dict[str, int]]] = []
    for phase in phases:
        # Whole body (incl. already_audited) is guarded so one bad phase can
        # neither abort the remaining phases nor crash main → block the Stop
        # chain (external-review code, gemini).
        try:
            if pq.already_audited(project_root, phase, run_id, session_id):
                continue
            findings = {
                "canon": pq.run_canon_checks(phase, project_root),
                "workflow": pq.run_workflow_checks(phase, project_root, run_id),
                "infrastructure": pq.run_infrastructure_checks(phase, project_root),
                "traceability": pq.run_traceability_checks(phase, project_root),
                "quality": pq.run_quality_checks(phase, project_root),
                "spec": pq.run_spec_checks(phase, project_root, run_id),
            }
            # Defense-in-depth: in the fail-open all-phases path a non-engaged
            # phase's FAILs are rewritten to SKIP. No-op on the normal path
            # (every audited phase IS engaged). FAIL-OPEN post-pass.
            findings = _skip_unengaged_fails(findings, phase, project_root)
            pq.write_finding_json(
                project_root, phase, run_id, session_id, findings,
                source=pq.resolve_source(project_root, phase),
            )
            audited.append((phase, _roll_up(findings)))
        except Exception as exc:  # noqa: BLE001 — one bad phase must not abort the rest
            sys.stderr.write(
                f"[audit_phase_quality] Error auditing phase={phase}: "
                f"{type(exc).__name__}: {exc}\n"
            )
            pq.write_error_finding(project_root, phase, run_id, session_id, exc)

    # Project-wide tail — runs ONCE for the whole Stop event. Best-effort; never
    # blocks. Refreshes aggregates + the single rolling phaseQuality:backlog
    # action-unit (iterate-2026-05-31-phasequality-triage-bundle).
    try:
        pq.regenerate_all_aggregates(project_root)
        _gc_best_effort(project_root)
        commit = _git_head_sha(project_root)  # "" on failure (spec contract)
        pq.emit_phase_quality_backlog(project_root, run_id=run_id, commit=commit)
    except Exception as exc:  # noqa: BLE001 — never block Stop chain
        sys.stderr.write(
            f"[audit_phase_quality] Error in aggregate tail: "
            f"{type(exc).__name__}: {exc}\n"
        )

    elapsed_ms = int((time.monotonic() - started) * 1000)
    if audited:
        # One "phase=<p>" token per audited phase keeps the [phase-quality] tag
        # and downstream routing filters working.
        parts = " ".join(
            f"phase={p}(pass={t['PASS']} fail={t['FAIL']} "
            f"warn={t['WARN']} skip={t['SKIP']})"
            for p, t in audited
        )
        _emit_hook_output({
            "hookEventName": "Stop",
            "additionalContext": (
                f"[phase-quality] run={run_id} audited {len(audited)} phase(s) "
                f"({elapsed_ms}ms): {parts}"
            ),
        })
    else:
        _emit_hook_output({
            "hookEventName": "Stop",
            "additionalContext": (
                f"[phase-quality] run={run_id} already audited "
                f"{len(phases)} engaged phase(s) — skipped"
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


def _skip_unengaged_fails(
    findings: dict[str, list[dict]],
    phase: str,
    project_root: Path,
) -> dict[str, list[dict]]:
    """Rewrite FAIL→SKIP for a phase the project never actively engaged.

    Dashboard-consistency follow-up to the triage backlog: a phase with no
    completion evidence (and not the active pipeline cursor) renders its
    Tier-1 FAILs as "not applicable" rather than red. Best-effort + FAIL-OPEN
    — any error, or an engaged/undeterminable phase, leaves findings verbatim.
    """
    try:
        cfg, events = pq.load_engagement_inputs(project_root)
        if pq.phase_is_engaged(phase, cfg, events):
            return findings
        note = f"phase '{phase}' not engaged by this project — check not applicable"
        for items in findings.values():
            for f in items or []:
                if isinstance(f, dict) and f.get("status") == pq.STATUS_FAIL:
                    f["status"] = pq.STATUS_SKIP
                    f["evidence"] = note
                    f["provenance"] = "not-engaged"
    except Exception:  # noqa: BLE001 — never block the Stop chain
        pass
    return findings


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


if __name__ == "__main__":
    sys.exit(main())
