#!/usr/bin/env python3
"""Run compliance detection with explicit branch, merge, or release authority."""

from __future__ import annotations

import argparse
import inspect
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

_SHA_RE = re.compile(r"[0-9a-f]{40}")

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "shared" / "scripts"))
from lib.compliance_lifecycle import ALL_GROUPS, MERGE_GROUPS, coverage_for, may_mirror  # noqa: E402
from lib.repo_root import resolve_main_repo_root  # noqa: E402


def _git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=root, text=True, capture_output=True,
                          encoding="utf-8", errors="replace", timeout=60)


def _head(root: Path) -> str:
    p = _git(root, "rev-parse", "HEAD")
    return p.stdout.strip() if p.returncode == 0 else ""


def _audit_api():
    plugin = _ROOT / "plugins" / "shipwright-compliance"
    if str(plugin) not in sys.path:
        sys.path.insert(0, str(plugin))
    from scripts.audit._registry import register_all
    from scripts.audit.audit_detector import mirror_findings_to_triage, run_all
    # Plugin-cache skew guard (same class as the Stop hook's, and more load-bearing
    # here: this IS the backlog-mutating authority path). A stale `run_all` still
    # defaulting `emit_to_triage=True` would mirror per-check items itself, before
    # `may_mirror(coverage)` is ever consulted below.
    if "emit_to_triage" in inspect.signature(run_all).parameters:
        raise RuntimeError("stale compliance-plugin cache: run_all still carries "
                           "the pre-P2.59 emit_to_triage parameter — run "
                           "check_plugin_cache_sync.py --strict")
    return register_all, run_all, mirror_findings_to_triage


def run(scope: str, audit_root: Path, backlog_root: Path, *, commit: str,
        run_id: str | None = None) -> dict:
    """Run once. Branch feedback prints findings but cannot mirror them."""
    register, run_all, mirror = _audit_api()
    register()
    only = sorted(MERGE_GROUPS if scope == "merge" else ALL_GROUPS)
    report = run_all(audit_root, only=only, run_gate=True)
    coverage = coverage_for(report, scope)
    result = {"coverage": coverage.to_dict(), "findings": report.to_dict()}
    if may_mirror(coverage):
        result["mirror"] = mirror(backlog_root, report, run_id=run_id, commit=commit,
                                  preserve_groups=frozenset({"E"}) if scope == "merge" else frozenset())
    else:
        result["mirror"] = {"appended": 0, "dismissed": 0, "reason": "local_or_incomplete"}
    return result


_WORKTREE_PREFIX = "shipwright-compliance-"
# `lib.compliance_audit_spawn.spawn_compliance_audit`'s default `timeout`
# (180s) is what actually bounds a merge audit's caller. A worktree younger
# than that could still belong to a LIVE run — a second delivery landing in
# the same window must not delete it out from under that run. 1800s gives
# generous headroom above that bound.
_RECLAIM_MIN_AGE_SECONDS = 1800


def _is_own_detached_worktree(path: Path, block_lines: list[str]) -> bool:
    """Name-prefix alone is not a safe delete guard: `.worktrees/<slug>` is this
    repo's own convention for a checked-out iterate branch, and a slug starting
    with `_WORKTREE_PREFIX` is entirely plausible there — `--force` overrides
    git's dirty-worktree refusal, so a false match destroys another session's
    uncommitted work (code review MEDIUM). This tool only ever creates its own
    worktrees via `tempfile.mkdtemp(prefix=_WORKTREE_PREFIX)` with `--detach`, so
    require BOTH a temp-dir location and a `detached` porcelain line — never name
    alone."""
    if not path.name.startswith(_WORKTREE_PREFIX):
        return False
    if "detached" not in block_lines:
        return False
    try:
        # `resolve()` defaults to non-strict — it does NOT raise for a path
        # that no longer exists on disk (a vanished worktree directory still
        # resolves fine; git's own admin registration, not the directory,
        # is porcelain's source of truth). This except is for a genuinely
        # unresolvable path (e.g. a permission error walking the ancestry);
        # returning False there is conservative, not a vanished-directory gap.
        return path.resolve().is_relative_to(Path(tempfile.gettempdir()).resolve())
    except OSError:
        return False


def _reclaim_orphaned_merge_worktrees(main_root: Path) -> None:
    """Best-effort: a caller-side timeout hard-kills this process before its own
    `finally` can clean up, orphaning a detached worktree. Scoped to worktrees
    this tool itself could have created — a blanket `git worktree prune` is
    repo-wide and could race a DIFFERENT session's parallel iterate mid-`worktree
    add`. Age-gated on top of that: two merge audits landing within the same
    short window both match, and only a stale (orphaned) one is safe to delete —
    deleting a live one would make its audit see missing files and converge
    fabricated findings into the global backlog, the exact harm this authority
    model exists to prevent."""
    listed = _git(main_root, "worktree", "list", "--porcelain")
    if listed.returncode:
        return
    now = time.time()
    for block in listed.stdout.split("\n\n"):
        lines = block.splitlines()
        if not lines or not lines[0].startswith("worktree "):
            continue
        path = Path(lines[0][len("worktree "):])
        if not _is_own_detached_worktree(path, lines):
            continue
        try:
            age = now - path.stat().st_mtime
        except OSError:
            # Directory already gone (a prior `worktree remove` that
            # failed, or external cleanup) but the admin registration
            # survives — it can never be "too young"; reclaim it now
            # rather than skip, or it leaks forever (doubt review round 4).
            _git(main_root, "worktree", "remove", "--force", str(path))
            continue
        if age < _RECLAIM_MIN_AGE_SECONDS:
            continue
        # `rmtree` only after `remove` actually reports success — the exact
        # pattern `main()`'s own `finally` block was hardened against
        # (unconditional rmtree after a FAILED remove deletes the directory
        # while the git admin registration survives, which no later sweep can
        # then find via `git worktree list` to finish reclaiming; doubt review
        # round 5, LOW).
        if _git(main_root, "worktree", "remove", "--force", str(path)).returncode == 0:
            shutil.rmtree(path, ignore_errors=True)


def _release_commit_verified(root: Path, sha: str) -> bool:
    """Release authority is proven from the committed evidence, not a CLI claim.

    Must run before `_audit_api()` (ADR-044/045): that call inserts the
    compliance plugin at `sys.path[0]`, which can shadow this `tools.*` import.
    `main()`'s release branch already calls this ahead of `run()` — keep it so.
    """
    from tools.refresh_compliance_docs import verify_commit
    return verify_commit(root, sha).get("status") == "verified"

def _merge_sha(pr: str, repo: str) -> str:
    p = subprocess.run(["gh", "pr", "view", pr, "--repo", repo, "--json", "state,mergeCommit"],
                       text=True, capture_output=True, encoding="utf-8", errors="replace", timeout=60)
    if p.returncode:
        raise RuntimeError("delivered PR could not be read")
    data = json.loads(p.stdout)
    sha = ((data.get("mergeCommit") or {}).get("oid") or "").strip()
    # A full-match hex check, not just length: this value is the one field that
    # selects which tree merge authority converges the backlog from, and it
    # flows unquoted into `git fetch`/`worktree add` argv next — a value git
    # would parse as an option (e.g. a leading `-`) must never reach that call
    # (code review LOW).
    if data.get("state") != "MERGED" or not _SHA_RE.fullmatch(sha):
        raise RuntimeError("PR is not delivered with an exact merge commit")
    return sha


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--scope", choices=("branch_feedback", "merge", "release"), required=True)
    p.add_argument("--project-root", required=True)
    p.add_argument("--run-id", default=None)
    p.add_argument("--commit", default="")
    p.add_argument("--pr", default="")
    p.add_argument("--repo", default="")
    a = p.parse_args(argv)
    root = Path(a.project_root).resolve()
    main_root = resolve_main_repo_root(root) or root
    try:
        if a.scope == "merge":
            # A caller-side timeout (deliver_pr.py) kills this process before a
            # normal exit, so the `finally` below never runs on that path — reclaim
            # first, by name, whatever a prior killed run orphaned. Ahead of
            # `_merge_sha` so a `gh` failure or a not-yet-MERGED PR still lets
            # cleanup happen (doubt review round 3, LOW).
            _reclaim_orphaned_merge_worktrees(main_root)
            sha = _merge_sha(a.pr, a.repo)
            tmp = Path(tempfile.mkdtemp(prefix=_WORKTREE_PREFIX))
            created = False
            try:
                if _git(main_root, "fetch", "origin", sha).returncode:
                    raise RuntimeError("could not fetch delivered merge commit")
                if _git(main_root, "worktree", "add", "--detach", str(tmp), sha).returncode:
                    raise RuntimeError("could not create exact merge worktree")
                created = True
                result = run("merge", tmp, main_root, commit=sha, run_id=a.run_id)
            finally:
                if created:
                    # `worktree add` succeeded — `remove` unregisters it AND
                    # deletes the directory. On a nonzero rc, do NOT force-delete
                    # `tmp` ourselves: the registration AND directory must both
                    # survive together for the sweep to find and retry it later
                    # (an rmtree here would delete the directory while the admin
                    # registration survives, which the sweep can never see —
                    # doubt review round 4).
                    try:
                        removed = _git(main_root, "worktree", "remove", "--force", str(tmp))
                        if removed.returncode:
                            sys.stderr.write(
                                f"[compliance] worktree remove failed (rc={removed.returncode}); "
                                f"next run's reclaim sweep will retry it\n")
                        else:
                            shutil.rmtree(tmp, ignore_errors=True)
                    except Exception as exc:  # noqa: BLE001 — must not mask the real failure above
                        sys.stderr.write(f"[compliance] worktree cleanup failed: {type(exc).__name__}\n")
                else:
                    # `mkdtemp` already created `tmp` before the failed fetch/add —
                    # it was never registered as a worktree, so the reclaim sweep
                    # (which iterates `git worktree list`) can never find it. Must
                    # be removed directly here or it leaks permanently (doubt
                    # review round 3, LOW).
                    shutil.rmtree(tmp, ignore_errors=True)
        else:
            sha = a.commit or _head(root)
            if not sha or _head(root) != sha:
                raise RuntimeError("audit target is not the verified commit")
            if a.scope == "release":
                if not _release_commit_verified(root, sha):
                    raise RuntimeError("release audit requires a verified compliance-evidence commit")
                # Release has the WIDEST authority (full A-I, may dismiss
                # Group E) — merge scope goes to the trouble of a detached
                # exact-SHA worktree specifically so it never audits anything
                # but the committed tree; a dirty release tree at the right
                # HEAD sha would otherwise let uncommitted content feed that
                # same convergence (doubt review round 5, MEDIUM).
                dirty = _git(root, "status", "--porcelain")
                if dirty.returncode or dirty.stdout.strip():
                    raise RuntimeError("release audit refuses a dirty working tree")
            result = run(a.scope, root, main_root, commit=sha, run_id=a.run_id)
        print(json.dumps(result, indent=2))
        if a.scope in {"merge", "release"} and not result["coverage"]["complete"]:
            return 1
        return 0
    except Exception as exc:
        print(json.dumps({"status": "not_mirrored", "reason": str(exc)[:300]}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
