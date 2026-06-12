#!/usr/bin/env python3
"""Resolve git merge conflicts on Shipwright *churn* artifacts — and ONLY those.

When ``origin/main`` advances while an iterate branch is open, a ``git merge
origin/main`` conflicts exclusively on generated/"churn" artifacts (see
iterate-2026-05-31-churn-merge-resolver). This tool reconciles them
deterministically so a human never hand-resolves them again:

- **derived MDs** (the 5 compliance + 3 agent-doc snapshot markdown files) —
  regenerated from the merged tree via the *same* single-producer generators
  that ``finalize_iterate`` uses (zero drift by construction).
- **``shipwright_test_results.json``** — a PR-owned snapshot → resolved ``--ours``.
- **``shipwright_events.jsonl``** — append-only log; normally auto-unioned by
  ``.gitattributes`` (``merge=union``). Validated unconditionally (every line
  must parse as JSON, this run's event must survive) and exact-line-deduped.

**Hard safety invariant (AC-3):** a *pre-flight gate* aborts — touching nothing,
running no generator — if ANY conflicted path is outside ``CHURN_ALLOWLIST``
(i.e. real source code).

Pure rules (allowlist / classify / dedup / validate) live in
``lib/churn_merge.py``. Trusted use only: runs repo-local generators at merge
time (O12); all git calls use argv lists (no shell).
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent  # shared/scripts
sys.path.insert(0, str(_SCRIPTS_DIR))

from lib.churn_merge import (  # noqa: E402
    CHURN_ALLOWLIST,
    COMPLIANCE_MDS,
    DERIVED_MDS,
    EVENTS_LOG,
    TEST_RESULTS,
    TRIAGE_LOG,
    classify,
    dedup_event_lines,
    dedup_triage_lines,
    norm,
    validate_events_text,
    validate_triage_text,
)

__all__ = [
    "CHURN_ALLOWLIST",
    "complete_merge",
    "conflicted_paths",
    "regenerate_tracked_snapshots",
    "ResolveResult",
    "main",
]


# --- git plumbing -----------------------------------------------------------

def _git(project_root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    # encoding="utf-8" STRICT (no errors="replace"): default text=True decodes via
    # the Windows cp1252 locale, mojibaking/crashing on UTF-8 git output (WP6/F22).
    # _union_conflict re-serialises this stdout verbatim into the tracked log, so
    # the round-trip must be byte-identical (errors="replace" would corrupt it).
    return subprocess.run(
        ["git", "-C", str(project_root), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=check,
    )


def conflicted_paths(project_root: Path) -> list[str]:
    """Currently-unmerged paths (``git diff --name-only --diff-filter=U``)."""
    proc = _git(project_root, "diff", "--name-only", "--diff-filter=U", check=False)
    if proc.returncode != 0:
        return []
    return [norm(p) for p in proc.stdout.splitlines() if p.strip()]


def _take_side(project_root: Path, rel: str, side: str) -> None:
    """Resolve an unmerged path to ``--ours``/``--theirs`` and stage it."""
    _git(project_root, "checkout", side, "--", rel)
    _git(project_root, "add", "--", rel)


class _TriageNotUtf8Error(Exception):
    """A triage.jsonl stage was not valid UTF-8, so the byte-identical union cannot
    run safely. Translated by ``complete_merge`` into a ``triage_invalid`` status."""


def _union_conflict(project_root: Path, rel: str) -> None:
    """Union both sides of an append-only-log conflict (ours stage :2: + theirs
    stage :3:) and stage it. ``--ours`` would DROP theirs' items; target projects
    lack the ``merge=union`` driver so this is the sole safety net there. The
    duplicate header + shared lines collapse in the subsequent ``_reconcile_*``
    dedup; the reconcile also validates the union.

    ``_git`` decodes STRICT UTF-8 (WP6/F22) for a byte-identical round-trip. A
    non-UTF-8 byte raises ``UnicodeDecodeError`` synchronously (strict decode runs
    in the calling thread on every platform), normalised here to a typed error —
    not a bare traceback. ``stdout is None`` is a defensive guard folded into it.
    """
    def _show(stage: str) -> str:
        try:
            out = _git(project_root, "show", f"{stage}:{rel}", check=False).stdout
        except UnicodeDecodeError as exc:  # strict-decode shape (all platforms)
            raise _TriageNotUtf8Error(f"{rel} ({stage}) non-UTF-8 byte: {exc}") from exc
        if out is None:  # defensive: unexpected None stdout (output not piped)
            raise _TriageNotUtf8Error(f"{rel} ({stage}) contains a non-UTF-8 byte")
        return out

    both = _show(":2").splitlines() + _show(":3").splitlines()
    (project_root / rel).write_text("\n".join(both) + "\n" if both else "", encoding="utf-8")
    _git(project_root, "add", "--", rel)


# --- resolution outcome -----------------------------------------------------

@dataclass
class ResolveResult:
    status: str  # "resolved" | "blocked" | "clean" | "events_invalid" | "triage_invalid"
    resolved: list[str] = field(default_factory=list)
    blocking: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def exit_code(self) -> int:
        return {
            "clean": 0, "resolved": 0, "blocked": 2,
            "events_invalid": 4, "triage_invalid": 4,
        }.get(self.status, 1)


def _reconcile_events(
    project_root: Path, run_id: str | None, resolved: list[str]
) -> tuple[list[str], list[str]]:
    """Dedup + validate ``events.jsonl`` unconditionally (it is union-resolved
    silently, so may never appear as unmerged). Mutates ``resolved`` to record a
    rewrite. Returns ``(errors, warnings)``."""
    log = project_root / EVENTS_LOG
    if not log.exists():
        return [], []
    original = log.read_text(encoding="utf-8")
    deduped, warnings = dedup_event_lines(original.splitlines())
    new_text = "\n".join(deduped) + "\n" if deduped else ""
    if new_text != original:
        log.write_text(new_text, encoding="utf-8")
        _git(project_root, "add", "--", EVENTS_LOG)
        if EVENTS_LOG not in resolved:
            resolved.append(EVENTS_LOG)
    return validate_events_text(new_text, require_run_id=run_id), warnings


def _reconcile_triage(
    project_root: Path, resolved: list[str]
) -> tuple[list[str], list[str]]:
    """Dedup + validate ``triage.jsonl`` unconditionally (mirrors
    ``_reconcile_events``; triage dedup never warns — shared append/status ids
    are by design). Mutates ``resolved``; returns ``(errors, warnings)``.
    """
    log = project_root / TRIAGE_LOG
    if not log.exists():
        return [], []
    original = log.read_text(encoding="utf-8")
    deduped, warnings = dedup_triage_lines(original.splitlines())
    new_text = "\n".join(deduped) + "\n" if deduped else ""
    if new_text != original:
        log.write_text(new_text, encoding="utf-8")
        _git(project_root, "add", "--", TRIAGE_LOG)
        if TRIAGE_LOG not in resolved:
            resolved.append(TRIAGE_LOG)
    return validate_triage_text(new_text), warnings


def _reconcile_logs(
    project_root: Path, run_id: str | None, resolved: list[str]
) -> tuple[str | None, list[str], list[str]]:
    """Reconcile BOTH append-only logs. Returns ``(invalid_status_or_None,
    errors, warnings)`` — the status is ``events_invalid`` / ``triage_invalid``.
    """
    e_errors, e_warnings = _reconcile_events(project_root, run_id, resolved)
    t_errors, t_warnings = _reconcile_triage(project_root, resolved)
    warnings = e_warnings + t_warnings
    if e_errors:
        return "events_invalid", e_errors, warnings
    if t_errors:
        return "triage_invalid", t_errors, warnings
    return None, [], warnings


def complete_merge(project_root: Path, *, run_id: str | None = None) -> ResolveResult:
    """Make a conflicted merge committable by resolving ONLY churn conflicts.

    Pre-flight gate first (AC-3): any conflicted path outside the allowlist
    aborts touching nothing. Then ``test_results.json`` → ``--ours``; derived
    MDs → ``--theirs`` (cleared now, regenerated in the follow-up commit, AC-6);
    ``events.jsonl`` validated + deduped unconditionally.
    """
    conflicted = conflicted_paths(project_root)
    resolvable, blocking = classify(conflicted)
    if blocking:
        return ResolveResult(status="blocked", blocking=blocking)
    if not conflicted:
        # Still reconcile the append-only logs: union may have resolved them silently.
        resolved: list[str] = []
        invalid, errors, warnings = _reconcile_logs(project_root, run_id, resolved)
        if invalid:
            return ResolveResult(status=invalid, resolved=resolved, errors=errors, warnings=warnings)
        return ResolveResult(status="clean" if not resolved else "resolved", resolved=resolved, warnings=warnings)

    resolved = []
    for rel in resolvable:
        if rel == TRIAGE_LOG:
            # A non-UTF-8 byte in a legacy triage.jsonl would crash the strict
            # decode (WP6/F22); translate to a structured triage_invalid instead.
            try:
                _union_conflict(project_root, rel)  # append-only backlog — keep BOTH sides
            except (_TriageNotUtf8Error, UnicodeDecodeError) as exc:
                _git(project_root, "merge", "--abort", check=False)
                return ResolveResult(
                    status="triage_invalid",
                    errors=[f"{TRIAGE_LOG} is not valid UTF-8 ({exc}); "
                            "cannot union safely — resolve by hand"],
                )
            resolved.append(rel)
        elif rel in (EVENTS_LOG, TEST_RESULTS):
            _take_side(project_root, rel, "--ours")
            resolved.append(rel)
        else:  # DERIVED_MDS or campaign status.json (S3): placeholder, regenerated later
            # resolvable ⊆ allowlist ∪ campaign-status, so this catch-all never drops a path
            _take_side(project_root, rel, "--theirs")
            resolved.append(rel)

    invalid, errors, warnings = _reconcile_logs(project_root, run_id, resolved)
    if invalid:
        return ResolveResult(status=invalid, resolved=sorted(set(resolved)), errors=errors, warnings=warnings)
    return ResolveResult(status="resolved", resolved=sorted(set(resolved)), warnings=warnings)


def regenerate_tracked_snapshots(
    project_root: Path,
    run_id: str,
    *,
    session_id: str | None = None,
    reason: str = "merge origin/main reconciliation",
    only: set[str] | None = None,
    campaign_status_rels: list[str] | None = None,
) -> dict[str, str]:
    """Regenerate derived MDs from the merged tree via the canonical
    single-producer generators (the SAME ones ``finalize_iterate`` uses) and
    stage them. Returns ``{relpath: outcome}``. ``only`` restricts the derived-MD
    set (defaults to the full set). ``campaign_status_rels`` (campaign S3) names
    the campaign ``status.json`` files this merge TOUCHED — re-projected scoped
    (NEVER glob-all: re-deriving an untouched campaign would be destructive)."""
    from tools import finalize_iterate  # canonical producers; zero-drift reuse

    session_id = session_id or os.environ.get("SHIPWRIGHT_SESSION_ID", "")
    targets = only or set(DERIVED_MDS)
    stems = {Path(t).stem for t in targets}
    out: dict[str, str] = {}

    if "build_dashboard" in stems:
        out[".shipwright/agent_docs/build_dashboard.md"] = (
            finalize_iterate._update_dashboard(project_root, session_id, run_id) or "error"
        )
    if "session_handoff" in stems:
        out[".shipwright/agent_docs/session_handoff.md"] = (
            finalize_iterate._generate_handoff(project_root, session_id, run_id, reason) or "error"
        )
    if "triage_inbox" in stems:
        out[".shipwright/agent_docs/triage_inbox.md"] = finalize_iterate._snapshot_triage_runtime(
            project_root
        )
    if any(t in COMPLIANCE_MDS for t in targets):
        # One call regenerates all five compliance MDs (consistent set, O9).
        paths = finalize_iterate._update_compliance(project_root)
        for rel in sorted(COMPLIANCE_MDS):
            out[rel] = "regenerated" if paths else "error"

    if campaign_status_rels:  # re-project ONLY the campaigns this merge touched (S3)
        from lib.campaign_status_io import regenerate_campaign_statuses
        out.update(regenerate_campaign_statuses(project_root, project_root / EVENTS_LOG, campaign_status_rels))

    staged = [
        rel for rel, outcome in out.items()
        if outcome != "error" and (project_root / rel).exists()
    ]
    if staged:
        _git(project_root, "add", "--", *staged)
    return out


# --- CLI --------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Resolve Shipwright churn-artifact merge conflicts")
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--run-id", default=None, help="iterate run id (enables events presence check)")
    parser.add_argument("--session-id", default=None)
    parser.add_argument("--reason", default="merge origin/main reconciliation")
    parser.add_argument(
        "--mode",
        choices=["resolve", "regenerate"],
        default="resolve",
        help="'resolve' completes a conflicted merge (allowlist-gated); "
        "'regenerate' re-derives the tracked MD snapshots from the merged tree",
    )
    args = parser.parse_args(argv)
    project_root = Path(args.project_root).resolve()

    if args.mode == "regenerate":
        outcomes = regenerate_tracked_snapshots(
            project_root, args.run_id or "unknown",
            session_id=args.session_id, reason=args.reason,
        )
        failed = [k for k, v in outcomes.items() if v == "error"]
        print(json.dumps({"mode": "regenerate", "outcomes": outcomes, "failed": failed}, indent=2))
        return 3 if failed else 0

    result = complete_merge(project_root, run_id=args.run_id)
    print(
        json.dumps(
            {
                "mode": "resolve",
                "status": result.status,
                "resolved": result.resolved,
                "blocking": result.blocking,
                "errors": result.errors,
                "warnings": result.warnings,
            },
            indent=2,
        )
    )
    if result.status == "blocked":
        print(
            "ABORT: non-churn conflicts present — resolve these by hand "
            f"(nothing was touched): {result.blocking}",
            file=sys.stderr,
        )
    elif result.status == "events_invalid":
        print(f"ABORT: {EVENTS_LOG} failed validation after merge: {result.errors}", file=sys.stderr)
    elif result.status == "triage_invalid":
        print(f"ABORT: {TRIAGE_LOG} failed validation after merge: {result.errors}", file=sys.stderr)
    return result.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
