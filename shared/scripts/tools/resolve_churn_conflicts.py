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
    classify,
    dedup_event_lines,
    norm,
    validate_events_text,
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
    return subprocess.run(
        ["git", "-C", str(project_root), *args],
        capture_output=True,
        text=True,
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


# --- resolution outcome -----------------------------------------------------

@dataclass
class ResolveResult:
    status: str  # "resolved" | "blocked" | "clean" | "events_invalid"
    resolved: list[str] = field(default_factory=list)
    blocking: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def exit_code(self) -> int:
        return {"clean": 0, "resolved": 0, "blocked": 2, "events_invalid": 4}.get(self.status, 1)


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
        # Still reconcile events: union may have resolved it silently.
        resolved: list[str] = []
        errors, warnings = _reconcile_events(project_root, run_id, resolved)
        if errors:
            return ResolveResult(status="events_invalid", resolved=resolved, errors=errors, warnings=warnings)
        return ResolveResult(status="clean" if not resolved else "resolved", resolved=resolved, warnings=warnings)

    resolved = []
    for rel in resolvable:
        if rel in (EVENTS_LOG, TEST_RESULTS):
            _take_side(project_root, rel, "--ours")
            resolved.append(rel)
        elif rel in DERIVED_MDS:
            _take_side(project_root, rel, "--theirs")  # placeholder — regenerated later
            resolved.append(rel)

    errors, warnings = _reconcile_events(project_root, run_id, resolved)
    if errors:
        return ResolveResult(status="events_invalid", resolved=sorted(set(resolved)), errors=errors, warnings=warnings)
    return ResolveResult(status="resolved", resolved=sorted(set(resolved)), warnings=warnings)


def regenerate_tracked_snapshots(
    project_root: Path,
    run_id: str,
    *,
    session_id: str | None = None,
    reason: str = "merge origin/main reconciliation",
    only: set[str] | None = None,
) -> dict[str, str]:
    """Regenerate derived MDs from the merged tree via the canonical
    single-producer generators (the SAME ones ``finalize_iterate`` uses) and
    stage them. Returns ``{relpath: outcome}``. ``only`` restricts the set
    (defaults to the full derived-MD set)."""
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
    return result.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
