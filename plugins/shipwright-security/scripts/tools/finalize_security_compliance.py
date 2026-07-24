#!/usr/bin/env python3
"""Post-scan compliance snapshot for ``/shipwright-security`` Step 7.5.

After Step 7 persists ``shipwright_security_config.json``, this helper:

  1. Runs the compliance regen (``update_compliance.py --phase security``)
     so the MDs reflect the post-scan state.
  2. If any of the artifacts ``update_compliance`` writes changed, stages
     the FULL write-set and creates a snapshot-qualifying commit
     ``chore(compliance): refresh after security scan`` with the body
     trailer ``Run-ID: security-<scan_id>``. The audit's
     ``find_snapshot_commit`` picks it up the same way it picks up
     iterate F6 / adopt Step H commits.
  3. Otherwise: no-op (the regen produced no diff).

``update_compliance.py --phase security`` writes THREE artifact groups, not
one: the compliance MDs under ``.shipwright/compliance/``, an appended
``grade_snapshot`` in ``shipwright_events.jsonl`` (``emit_grade_snapshot``
records one per regen, UNCONDITIONALLY — M-Pre-3), and
``shipwright_compliance_config.json`` (``phases_covered``). The finalizer
stages ALL of them (``FINALIZE_ARTIFACTS``), mirroring iterate F6's explicit
per-path ``git add`` list. Staging only the MDs — as this helper did before
iterate-2026-07-24-finalizer-events-staging — left the appended event dirty in
the working tree, which aborts the next ``ensure_current`` pre-merge refresh
with exit 6 (merge_failed); the ad-hoc recovery, ``git checkout --
shipwright_events.jsonl``, silently discards the grade snapshot.

**Pipeline mode only.** When ``shipwright_project_config.json`` is absent
the project is standalone — Step 8 already hands off to
``/shipwright-iterate`` for the actual fix commits, so we don't double-
commit here.

**CI / non-interactive skip.** ``CI`` or ``SHIPWRIGHT_NON_INTERACTIVE``
env vars → no-op (CI scan workflows don't drive interactive commits and
shouldn't race the pipeline).

Returns structured JSON on stdout for the SKILL.md consumer:

    {"committed": bool, "reason": "...", "commit_sha": "..."}

Safe to re-run — each invocation records one post-scan compliance snapshot
(the ``grade_snapshot`` append is unconditional per regen) and NEVER leaves the
working tree dirty. A re-run is therefore not a strict no-op; only a genuinely
empty regen (no MD change AND no appended event) makes no commit.

Usage:
    uv run finalize_security_compliance.py --project-root <path> \
        --scan-id <id>
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


# Compliance dir lives at this path inside the project. Kept as a
# module-level constant so tests can override via monkeypatching if
# layout changes downstream.
COMPLIANCE_DIR = ".shipwright/compliance"

# The complete set of tracked artifacts ``update_compliance.py --phase
# security`` may write — the dirty-check and the staging BOTH key on this so
# the finalizer never leaves part of the regen behind (see module docstring).
# Explicit per-path list, mirroring iterate F6's ``git add`` block; a path that
# is absent, unchanged, or gitignored is skipped naturally (it never surfaces in
# ``git status --porcelain``), so no ``git add`` is attempted for it. Order is
# cosmetic (git stages regardless).
FINALIZE_ARTIFACTS = (
    COMPLIANCE_DIR,                       # dashboard/test-evidence/change-history/sbom + audit-report + ci-security.json
    "shipwright_events.jsonl",            # grade_snapshot append (one per regen)
    "shipwright_compliance_config.json",  # phases_covered
    ".shipwright/triage.jsonl",           # sbom_triage / test_evidence_triage — appends DIRECT to the
                                          # tracked log only when there is no `origin` remote to route to the
                                          # gitignored outbox; harmless (never dirty) in the routed case.
)

# Files that signal "this project went through the orchestrator pipeline".
# Their presence is what distinguishes pipeline-mode security from
# standalone-mode security.
PIPELINE_MARKER = "shipwright_project_config.json"


def _is_pipeline_mode(project_root: Path) -> bool:
    return (project_root / PIPELINE_MARKER).exists()


def _is_ci_or_noninteractive() -> bool:
    if os.environ.get("CI", "").strip():
        return True
    if os.environ.get("SHIPWRIGHT_NON_INTERACTIVE", "").strip():
        return True
    return False


def _run_update_compliance(project_root: Path) -> dict:
    """Invoke ``update_compliance.py --phase security`` and return its JSON.

    Test seam — monkeypatched in unit tests to simulate no-diff /
    diff-producing runs without depending on the real renderer.
    """
    # Resolve the compliance plugin script relative to this file: we live
    # at plugins/shipwright-security/scripts/tools/, the compliance plugin
    # is at plugins/shipwright-compliance/scripts/tools/.
    this_plugin = Path(__file__).resolve().parents[2]  # plugins/shipwright-security
    compliance_plugin = this_plugin.parent / "shipwright-compliance"
    script = compliance_plugin / "scripts" / "tools" / "update_compliance.py"
    if not script.exists():
        return {"updated_reports": [], "error": f"missing: {script}"}

    proc = subprocess.run(
        [sys.executable, str(script),
         "--project-root", str(project_root),
         "--phase", "security"],
        capture_output=True, text=True, encoding="utf-8", timeout=30,
        cwd=str(project_root),
    )
    if proc.returncode != 0 or not proc.stdout.strip():
        return {
            "updated_reports": [],
            "error": f"non-zero exit {proc.returncode}: {(proc.stderr or '')[:300]}",
        }
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        return {"updated_reports": [], "error": f"invalid JSON: {exc}"}


def _git(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(cwd), *args],
        capture_output=True, text=True, encoding="utf-8", timeout=15,
        check=False,
    )


def _dirty_artifacts(project_root: Path,
                     candidates: tuple[str, ...] = FINALIZE_ARTIFACTS) -> list[str]:
    """Return the subset of ``candidates`` that git reports as dirty.

    Uses ``git status --porcelain -- <candidates>`` (git-aware: modified +
    untracked-not-ignored + deleted all surface). A path that is absent,
    unchanged, or gitignored-and-untracked never appears in the porcelain
    output, so it is naturally excluded — this is how the F6 "skip a path only
    if gitignored / untracked / absent" convention is honoured without a
    separate ``check-ignore`` probe, and why a downstream project that
    ``.gitignore``s ``shipwright_events.jsonl`` can never trigger a ``git add``
    error here. A directory candidate (``.shipwright/compliance``) matches when
    any file beneath it is dirty. Returns the candidates (not the individual
    files) so the caller stages by the same paths it declared.
    """
    proc = _git(["status", "--porcelain", "--", *candidates], cwd=project_root)
    if proc.returncode != 0:
        return []
    changed: list[str] = []
    for line in proc.stdout.splitlines():
        if not line.strip():
            continue
        # porcelain v1: two status chars, a space, then the path; a rename is
        # rendered "old -> new" — the post-rename path is what is staged.
        path = line[3:]
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        changed.append(path.strip().strip('"').replace("\\", "/"))
    hits: list[str] = []
    for cand in candidates:
        norm = cand.rstrip("/")
        if any(ch == norm or ch.startswith(norm + "/") for ch in changed):
            hits.append(cand)
    return hits


def finalize(project_root: Path, *, scan_id: str) -> dict:
    """Orchestrate the Step 7.5 finalize. Returns structured result dict.

    See module docstring for skip semantics and the commit message shape.
    """
    project_root = Path(project_root).resolve()

    if not _is_pipeline_mode(project_root):
        return {
            "committed": False,
            "reason": "standalone mode (no shipwright_project_config.json) — pipeline-only step",
        }

    if _is_ci_or_noninteractive():
        return {
            "committed": False,
            "reason": "CI / non-interactive env detected — step skipped",
        }

    regen = _run_update_compliance(project_root)
    if "error" in regen:
        return {
            "committed": False,
            "reason": f"update_compliance failed: {regen['error']}",
        }

    dirty = _dirty_artifacts(project_root)
    if not dirty:
        return {
            "committed": False,
            "reason": "compliance unchanged after security scan — no diff to commit",
        }

    # Stage the full write-set (only the paths git actually reports dirty, so an
    # absent / ignored artifact is silently skipped instead of erroring).
    add = _git(["add", "--", *dirty], cwd=project_root)
    if add.returncode != 0:
        return {
            "committed": False,
            "reason": f"git add failed: {(add.stderr or '').strip()[:200]}",
        }

    message = (
        "chore(compliance): refresh after security scan\n"
        "\n"
        "Regenerated dashboard/test-evidence/change-history/sbom and recorded "
        "the post-scan grade snapshot (shipwright_events.jsonl).\n"
        "No FR coverage change (RTM unaffected).\n"
        "\n"
        f"Run-ID: security-{scan_id}\n"
        "Co-Authored-By: Claude <noreply@anthropic.com>"
    )
    commit = _git(["commit", "-m", message], cwd=project_root)
    if commit.returncode != 0:
        return {
            "committed": False,
            "reason": f"git commit failed: {(commit.stderr or '').strip()[:200]}",
        }

    sha_proc = _git(["rev-parse", "HEAD"], cwd=project_root)
    return {
        "committed": True,
        "reason": "compliance refreshed and committed",
        "commit_sha": sha_proc.stdout.strip(),
        "regenerated": regen.get("updated_reports", []),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Step 7.5 security compliance finalize")
    parser.add_argument("--project-root", required=True)
    parser.add_argument(
        "--scan-id", required=True,
        help="Identifier for the security scan run; appears in the "
             "commit's `Run-ID: security-<scan_id>` trailer.",
    )
    args = parser.parse_args(argv)

    result = finalize(Path(args.project_root), scan_id=args.scan_id)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("committed") or "skipped" in result.get("reason", "") or "standalone" in result.get("reason", "") or "unchanged" in result.get("reason", "") else 1


if __name__ == "__main__":
    sys.exit(main())
