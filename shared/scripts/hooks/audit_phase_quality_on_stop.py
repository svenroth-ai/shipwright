#!/usr/bin/env python3
"""Stop hook: consolidated phase-quality audit entry point.

Runs all 6 Phase-Quality categories (canon, workflow, infrastructure,
traceability, quality, spec) across every Shipwright plugin's Stop event.

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

# _resolve_roots moved to lib.phase_quality._resolution.resolve_project_roots
# (pq.resolve_project_roots) — see its docstring for the audit_root/plain_root
# split rationale (doubt-review D1/D4).


def _emit_hook_output(payload: dict[str, object]) -> None:
    # Stop hookSpecificOutput accepts only `hookEventName`; `additionalContext`
    # is rejected by validation. Route the message to stderr instead — Claude
    # Code surfaces hook stderr to the user. See ADR-042.
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

    session_id = os.environ.get("SHIPWRIGHT_SESSION_ID", "").strip() or "unknown"
    cwd = Path.cwd()
    audit_root, via_pointer, plain_root = pq.resolve_project_roots(cwd, session_id)

    # Greenfield guard — matches the contract used by the other Stop hooks.
    # Gated on plain_root (never redirected): a verified pointer worktree is
    # inherently a valid Shipwright project too, but plain_root is what the
    # pre-redirect contract always checked and stays the stable signal.
    if not pq.is_shipwright_project(plain_root):
        return 0

    # Monorepo auto-descent guard: skip when the resolver auto-descended
    # into a managed subfolder the user wasn't actually working in. Opt-in
    # via SHIPWRIGHT_PROJECT_ROOT — or, equally, `via_pointer`: a worktree
    # redirect is a verified selection too, not an unwanted descent, and
    # without this OR the guard would SKIP exactly the audit this fix needs.
    if pq.cwd_is_strict_ancestor_of(cwd, audit_root) \
            and not (pq.project_root_was_explicitly_selected(audit_root) or via_pointer):
        return 0

    # Once-per-(Stop, session) guard: Claude Code fires this hook from every
    # enabled plugin (no filter), so one Stop invokes it ~11×. Exactly ONE wins
    # and audits; the rest skip — replacing the old per-plugin-root fan-out (11
    # phases audited, 10 never ran). Taken AFTER all no-op guards (a foreign/
    # no-op invocation must not consume the claim). Anchored at plain_root, not
    # audit_root: the pointer redirect's git lookup can transiently fail on any
    # one of the ~11 near-simultaneous invocations, which would otherwise let
    # two different roots each win their own claim (doubt-review D4). Fail-open
    # + unknown-session handling live in the shared helper.
    from lib.event_once import claim_once_for_event
    if not claim_once_for_event(plain_root, "stop-phasequality", session_id):
        return 0

    run_id = pq.resolve_run_id(audit_root, session_id)

    # Resolve which phase(s) ran THIS session from SESSION STATE (events.jsonl +
    # run_config), not CLAUDE_PLUGIN_ROOT. Fail-open: unknown/unreadable → ALL
    # canonical phases (audit more, never fewer). One claimed invocation audits
    # each engaged, not-yet-audited phase.
    phases = pq.resolve_engaged_phases(audit_root)

    started = time.monotonic()
    audited: list[tuple[str, dict[str, int]]] = []
    for phase in phases:
        # Whole body (incl. already_audited) is guarded so one bad phase can
        # neither abort the remaining phases nor crash main → block the Stop
        # chain (external-review code, gemini).
        try:
            if pq.already_audited(audit_root, phase, run_id, session_id):
                continue
            findings = {
                "canon": pq.run_canon_checks(phase, audit_root),
                "workflow": pq.run_workflow_checks(phase, audit_root, run_id),
                "infrastructure": pq.run_infrastructure_checks(phase, audit_root),
                "traceability": pq.run_traceability_checks(phase, audit_root),
                "quality": pq.run_quality_checks(phase, audit_root),
                "spec": pq.run_spec_checks(phase, audit_root, run_id),
            }
            # Defense-in-depth: in the fail-open all-phases path a non-engaged
            # phase's FAILs are rewritten to SKIP. No-op on the normal path
            # (every audited phase IS engaged). FAIL-OPEN post-pass.
            findings = _skip_unengaged_fails(findings, phase, audit_root)
            pq.write_finding_json(
                audit_root, phase, run_id, session_id, findings,
                source=pq.resolve_source(audit_root, phase),
            )
            audited.append((phase, _roll_up(findings)))
        except Exception as exc:  # noqa: BLE001 — one bad phase must not abort the rest
            sys.stderr.write(
                f"[audit_phase_quality] Error auditing phase={phase}: "
                f"{type(exc).__name__}: {exc}\n"
            )
            pq.write_error_finding(audit_root, phase, run_id, session_id, exc)

    # Project-wide tail — runs ONCE for the whole Stop event. Best-effort; never
    # blocks. Refreshes aggregates + the single rolling phaseQuality:backlog
    # action-unit (iterate-2026-05-31-phasequality-triage-bundle). Split, not
    # uniformly anchored (code-review, D1 + delta-pass follow-up):
    # `regenerate_all_aggregates` runs at `audit_root` so the worktree's own
    # findings render into ITS OWN dashboard, and ALSO at `plain_root` when a
    # pointer redirect makes the two differ — otherwise main's dashboard goes
    # dark for the whole redirected run instead of refreshing on every Stop.
    # Both are pure per-tree renders of that tree's own findings, so running
    # it twice carries no cross-tree hazard. `gc_old_findings` and
    # `emit_phase_quality_backlog` stay at `plain_root` only: GC bounds the
    # long-lived main tree's storage, and the backlog write is the one call
    # with a real cross-tree hazard (D1) — see `resolve_project_roots`'s
    # docstring.
    try:
        pq.regenerate_all_aggregates(audit_root)
        if audit_root != plain_root:
            pq.regenerate_all_aggregates(plain_root)
        _gc_best_effort(plain_root)
        commit = _git_head_sha(plain_root)  # "" on failure (spec contract)
        pq.emit_phase_quality_backlog(plain_root, run_id=run_id, commit=commit)
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
