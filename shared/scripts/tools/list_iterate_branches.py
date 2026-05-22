"""Classify `iterate/*` branches as active / stale / locked / current.

Replaces the SKILL.md B1a prose "filter stale branches via
``git merge-base --is-ancestor``" — which had no automation — with a
deterministic read-only helper that any caller (skill invocation,
hook, manual CLI) can invoke.

See `~/.claude/plans/iterate-c-stale-iterate-branch-filter.md` for the
design rationale; this file is the 1:1 implementation of that plan.

Output: JSON (schema v1) with per-branch metadata objects plus
backward-compat flat arrays. Stdout only; stderr carries human-readable
logs and `errors[]` strings are surfaced in the JSON payload.

Known limitations (documented in guide.md §8.5 Pitfall #7):
- Squash-merged branches stay `active` until operator
  `git branch -D iterate/<slug>` — no reliable local detection.
- Custom default-branch names beyond `main`/`master` require
  `--main <name>`.
- `main` + `master` ambiguity returns `main: null` + error.
- Submodules: classifies whatever repo `--project-root` resolves to.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


# -----------------------------------------------------------------------------
# Constants
# -----------------------------------------------------------------------------

SCHEMA_VERSION = 1
GLOBAL_TIMEOUT_MULTIPLIER = 6
DEFAULT_PER_CALL_TIMEOUT = 10.0


# -----------------------------------------------------------------------------
# Exceptions
# -----------------------------------------------------------------------------


class GitError(RuntimeError):
    """Non-zero exit from a git call invoked with check=True (R3-M6)."""


# -----------------------------------------------------------------------------
# Subprocess helper (R3-M6 contract)
# -----------------------------------------------------------------------------


def run_git(
    args: list[str],
    *,
    cwd: Path,
    timeout: float = DEFAULT_PER_CALL_TIMEOUT,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    """Run a git command with consistent hygiene.

    - ``--no-pager`` prevents pager hangs (R1-H2).
    - ``-C <cwd>`` scopes the call to the requested repo (R1-M9).
    - ``shell=False`` + list-form argv — no injection surface.
    - ``encoding="utf-8", errors="replace"`` — safe on Windows locales (R1-M10).
    - ``TimeoutExpired`` kills + reaps so no zombie git.exe on Windows.
    - ``check=True`` (default) raises ``GitError`` on non-zero.
    - ``check=False`` returns ``CompletedProcess`` regardless of return code
      for calls where non-zero is semantic (e.g., ``merge-base
      --is-ancestor`` returns 0/1 as truth values).
    """
    # `encoding` and `errors` kwargs are available since Python 3.6 — the project requires 3.11+ (see pyproject.toml).
    # nosemgrep: python.lang.compatibility.python36.python36-compatibility-Popen1,python.lang.compatibility.python36.python36-compatibility-Popen2
    proc = subprocess.Popen(
        ["git", "--no-pager", "-C", str(cwd), *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        shell=False,
    )
    try:
        out, err = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.communicate()  # reap the zombie
        raise
    if check and proc.returncode != 0:
        raise GitError(
            f"git {args[0] if args else '?'} failed "
            f"(exit {proc.returncode}): {err.strip()!r}"
        )
    return subprocess.CompletedProcess(
        ["git", *args], proc.returncode, out, err
    )


# -----------------------------------------------------------------------------
# Worktree porcelain parser (R2-H1 + R3-M7 + R4-M4)
# -----------------------------------------------------------------------------


@dataclass
class WorktreeRecord:
    """One parsed record from `git worktree list --porcelain` (R5-L3)."""

    path: str
    head: str | None
    branch: str | None
    detached: bool
    locked: bool
    locked_reason: str | None
    prunable: bool
    prunable_reason: str | None


def _finalize(record: dict[str, Any]) -> WorktreeRecord | None:
    """Return None for malformed records (missing path)."""
    path = record.get("path")
    if not path:
        return None
    return WorktreeRecord(
        path=path,
        head=record.get("head"),
        branch=record.get("branch"),
        detached=record.get("detached", False),
        locked=record.get("locked", False),
        locked_reason=record.get("locked_reason"),
        prunable=record.get("prunable", False),
        prunable_reason=record.get("prunable_reason"),
    )


def parse_worktree_porcelain(
    text: str,
) -> tuple[list[WorktreeRecord], list[str]]:
    """Parse `git worktree list --porcelain` output.

    Returns (records, parse_errors). Never raises for malformed input;
    malformed records surface via parse_errors so classification can
    continue for the valid ones (R3-M7 + R4-M4).
    """
    records: list[WorktreeRecord] = []
    parse_errors: list[str] = []
    current: dict[str, Any] = {}

    def _flush_current(boundary_type: str) -> None:
        if not current:
            return
        rec = _finalize(current)
        if rec is None:
            parse_errors.append(
                f"malformed worktree record at {boundary_type}: "
                f"{dict(current)!r}"
            )
        else:
            records.append(rec)

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if not line:
            _flush_current("blank separator")
            current = {}
            continue

        parts = line.split(None, 1)
        key = parts[0]
        value = parts[1] if len(parts) == 2 else None

        # R3-M7 implicit record boundary: a second `worktree` key without
        # a blank separator flushes the current record. MUST run BEFORE
        # the `key == "worktree"` dispatch so the old path isn't
        # overwritten.
        if key == "worktree" and current.get("path"):
            rec = _finalize(current)
            if rec is None:
                parse_errors.append(
                    f"malformed worktree record at implicit boundary: "
                    f"{dict(current)!r}"
                )
            else:
                records.append(rec)
                parse_errors.append(
                    "worktree porcelain: missing blank-line separator "
                    "between records (implicit boundary assumed)"
                )
            current = {}

        if key == "worktree":
            current["path"] = value
        elif key == "HEAD":
            current["head"] = value
        elif key == "branch":
            if value and value.startswith("refs/heads/"):
                current["branch"] = value[len("refs/heads/"):]
            else:
                current["branch"] = value
        elif key == "detached":
            current["detached"] = True
        elif key == "locked":
            current["locked"] = True
            current["locked_reason"] = value
        elif key == "prunable":
            current["prunable"] = True
            current["prunable_reason"] = value
        # Unknown keys ignored (forward-compat for future git versions).

    # Final record at EOF (no trailing blank line).
    _flush_current("EOF")

    return records, parse_errors


# -----------------------------------------------------------------------------
# Main-branch detection (R2-M3 + R1-H5 + R1-H3)
# -----------------------------------------------------------------------------


def _branch_exists(project_root: Path, full_ref: str) -> bool:
    """Check if a ref exists (local or remote). check=False — non-zero is semantic."""
    result = run_git(
        ["show-ref", "--verify", "--quiet", full_ref],
        cwd=project_root,
        check=False,
    )
    return result.returncode == 0


def _find_branch_ref(project_root: Path, name: str) -> str | None:
    """Prefer remote over local for freshness (R1-H5)."""
    if _branch_exists(project_root, f"refs/remotes/origin/{name}"):
        return f"refs/remotes/origin/{name}"
    if _branch_exists(project_root, f"refs/heads/{name}"):
        return f"refs/heads/{name}"
    return None


def detect_main(
    project_root: Path, override: str | None
) -> tuple[str | None, str | None, list[str]]:
    """Detect the default branch and its preferred ref.

    Returns (name, ref, errors). `name` / `ref` are None when no default
    can be determined without guessing (ambiguity or nothing found).
    """
    if override:
        ref = _find_branch_ref(project_root, override)
        if ref is not None:
            return override, ref, []
        return None, None, [
            f"--main={override!r} not found locally or on origin"
        ]

    # origin/HEAD — non-zero means no origin or origin/HEAD unset.
    result = run_git(
        ["symbolic-ref", "refs/remotes/origin/HEAD"],
        cwd=project_root,
        check=False,
    )
    if result.returncode == 0:
        target = result.stdout.strip()
        name = target.rsplit("/", 1)[-1]
        return name, target, []

    # Local heuristic — ambiguity-safe.
    main_exists = _branch_exists(
        project_root, "refs/heads/main"
    ) or _branch_exists(project_root, "refs/remotes/origin/main")
    master_exists = _branch_exists(
        project_root, "refs/heads/master"
    ) or _branch_exists(project_root, "refs/remotes/origin/master")

    if main_exists and master_exists:
        return None, None, [
            "ambiguous default branch: both 'main' and 'master' present; "
            "pass --main <name> explicitly"
        ]
    if main_exists:
        return "main", _find_branch_ref(project_root, "main"), []
    if master_exists:
        return "master", _find_branch_ref(project_root, "master"), []
    return None, None, [
        "no default branch detected (no main, no master, no origin/HEAD)"
    ]


# -----------------------------------------------------------------------------
# Current-branch + current-worktree detection (R3-H2 + R1-H4 + R4-M3)
# -----------------------------------------------------------------------------


def detect_current_branch(project_root: Path) -> str | None:
    """Return current branch name, or None on detached HEAD / unborn branch.

    Uses `symbolic-ref --quiet --short HEAD` (R3-H2). `rev-parse
    --abbrev-ref HEAD` returns literal "HEAD" on detached and is
    therefore unsafe here.
    """
    result = run_git(
        ["symbolic-ref", "--quiet", "--short", "HEAD"],
        cwd=project_root,
        check=False,
    )
    if result.returncode != 0:
        return None
    name = result.stdout.strip()
    # Defensive — reject literal "HEAD" if somehow returned.
    if not name or name == "HEAD":
        return None
    return name


def _normalize_path(p: str) -> str:
    """Cross-platform path normalization for comparison.

    Uses `normcase(abspath(...))`. Does NOT use `.resolve()` because
    prunable worktree paths may point at deleted directories, which
    makes `.resolve()` throw or normalize inconsistently on Windows
    (R4-M3 + R5-H1).
    """
    return os.path.normcase(os.path.abspath(p))


# -----------------------------------------------------------------------------
# Classification (R3-H3 + R3-M4 + R3-M5 + R4-H2)
# -----------------------------------------------------------------------------


# reason_code enum (R2-M4)
REASON_CURRENT = "current"
REASON_LOCKED = "locked"
REASON_ANCESTOR = "ancestor"
REASON_NOT_ANCESTOR = "not_ancestor"
REASON_UNRELATED_HISTORY = "unrelated_history"
REASON_TIMEOUT = "timeout"
REASON_MAIN_UNKNOWN = "main_unknown"

STATUS_ACTIVE = "active"
STATUS_STALE = "stale"
STATUS_LOCKED = "locked"

CONF_HIGH = "high"
CONF_LOW = "low"


def _make_entry(
    name: str,
    *,
    status: str,
    reason_code: str,
    confidence: str,
    detail: str | None = None,
    locked_in_worktree: str | None = None,
    would_be_status: str | None = None,
) -> dict[str, Any]:
    """Build a schema-complete per-branch dict (all required fields)."""
    return {
        "name": name,
        "status": status,
        "reason_code": reason_code,
        "detail": detail,
        "confidence": confidence,
        "locked_in_worktree": locked_in_worktree,
        "would_be_status": would_be_status,
    }


def _map_ancestor_to_would_be_status(
    result: subprocess.CompletedProcess[str],
) -> str:
    """R3-M4 matrix row for ancestor check in the locked-branch probe."""
    rc = result.returncode
    if rc == 0:
        return STATUS_STALE
    # rc == 1 or other non-zero → active
    return STATUS_ACTIVE


def _classify_non_locked_from_ancestor(
    name: str, result: subprocess.CompletedProcess[str]
) -> dict[str, Any]:
    """R3-H3 ancestor-check-to-classification table."""
    rc = result.returncode
    if rc == 0:
        return _make_entry(
            name,
            status=STATUS_STALE,
            reason_code=REASON_ANCESTOR,
            confidence=CONF_HIGH,
        )
    if rc == 1:
        return _make_entry(
            name,
            status=STATUS_ACTIVE,
            reason_code=REASON_NOT_ANCESTOR,
            confidence=CONF_HIGH,
        )
    return _make_entry(
        name,
        status=STATUS_ACTIVE,
        reason_code=REASON_UNRELATED_HISTORY,
        confidence=CONF_LOW,
        detail=f"merge-base --is-ancestor returned exit code {rc}",
    )


def classify_branches(
    project_root: Path,
    iterate_branches: list[str],
    *,
    current_branch: str | None,
    branch_to_worktree_path: dict[str, str],
    main_ref: str | None,
    per_call_timeout: float,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Classify every iterate branch per R3-H3 + R3-M4 + R3-M5."""
    entries: list[dict[str, Any]] = []
    runtime_errors: list[str] = []

    # main_ref is None → main_unknown short-circuit (R3-H3).
    if main_ref is None:
        for b in iterate_branches:
            if b == current_branch:
                entries.append(
                    _make_entry(
                        b,
                        status=STATUS_ACTIVE,
                        reason_code=REASON_CURRENT,
                        confidence=CONF_HIGH,
                    )
                )
            elif b in branch_to_worktree_path:
                entries.append(
                    _make_entry(
                        b,
                        status=STATUS_LOCKED,
                        reason_code=REASON_LOCKED,
                        confidence=CONF_HIGH,
                        locked_in_worktree=branch_to_worktree_path[b],
                        would_be_status=None,
                    )
                )
            else:
                entries.append(
                    _make_entry(
                        b,
                        status=STATUS_ACTIVE,
                        reason_code=REASON_MAIN_UNKNOWN,
                        confidence=CONF_LOW,
                        detail="no default branch detected; cannot classify",
                    )
                )
        return entries, runtime_errors

    # main_ref known → per-branch ancestor checks with global deadline.
    deadline = time.monotonic() + (
        per_call_timeout * GLOBAL_TIMEOUT_MULTIPLIER
    )
    deadline_hit_branch: str | None = None

    for b in iterate_branches:
        is_locked = b in branch_to_worktree_path

        if b == current_branch:
            entries.append(
                _make_entry(
                    b,
                    status=STATUS_ACTIVE,
                    reason_code=REASON_CURRENT,
                    confidence=CONF_HIGH,
                )
            )
            continue

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            # R5-M2: preserve status=locked even on deadline hit;
            # would_be_status becomes null.
            if deadline_hit_branch is None:
                deadline_hit_branch = b
            if is_locked:
                entries.append(
                    _make_entry(
                        b,
                        status=STATUS_LOCKED,
                        reason_code=REASON_LOCKED,
                        confidence=CONF_HIGH,
                        locked_in_worktree=branch_to_worktree_path[b],
                        would_be_status=None,
                        detail="global deadline exceeded before probe",
                    )
                )
            else:
                entries.append(
                    _make_entry(
                        b,
                        status=STATUS_ACTIVE,
                        reason_code=REASON_TIMEOUT,
                        confidence=CONF_LOW,
                        detail="global deadline exceeded",
                    )
                )
            continue

        effective_timeout = min(per_call_timeout, remaining)
        try:
            result = run_git(
                ["merge-base", "--is-ancestor", b, main_ref],
                cwd=project_root,
                check=False,
                timeout=effective_timeout,
            )
        except subprocess.TimeoutExpired:
            if is_locked:
                entries.append(
                    _make_entry(
                        b,
                        status=STATUS_LOCKED,
                        reason_code=REASON_LOCKED,
                        confidence=CONF_HIGH,
                        locked_in_worktree=branch_to_worktree_path[b],
                        would_be_status=None,
                        detail="ancestor probe timed out",
                    )
                )
            else:
                entries.append(
                    _make_entry(
                        b,
                        status=STATUS_ACTIVE,
                        reason_code=REASON_TIMEOUT,
                        confidence=CONF_LOW,
                        detail="ancestor probe timed out",
                    )
                )
            continue

        if is_locked:
            entries.append(
                _make_entry(
                    b,
                    status=STATUS_LOCKED,
                    reason_code=REASON_LOCKED,
                    confidence=CONF_HIGH,
                    locked_in_worktree=branch_to_worktree_path[b],
                    would_be_status=_map_ancestor_to_would_be_status(result),
                )
            )
        else:
            entries.append(_classify_non_locked_from_ancestor(b, result))

    if deadline_hit_branch is not None:
        # Count branches processed BEFORE the first remaining<=0 check.
        # `iterate_branches.index(deadline_hit_branch)` is the canonical
        # position — string-matching on `detail` would be fragile
        # (per-call timeouts and global-deadline timeouts both set a
        # `detail` field but have different downstream semantics).
        processed = iterate_branches.index(deadline_hit_branch)
        runtime_errors.append(
            f"global deadline exceeded after {processed} "
            f"branches classified"
        )

    return entries, runtime_errors


# -----------------------------------------------------------------------------
# Enumeration + orchestration
# -----------------------------------------------------------------------------


def enumerate_iterate_branches(project_root: Path) -> list[str]:
    """Enumerate `iterate/*` branches via `for-each-ref` (R3-L8).

    Uses the exact command `git for-each-ref --format='%(refname:short)'
    refs/heads/iterate` (no trailing slash on the ref pattern).
    Every returned entry must start with "iterate/" — assertion catches
    misconfiguration.
    """
    result = run_git(
        [
            "for-each-ref",
            "--format=%(refname:short)",
            "refs/heads/iterate",
        ],
        cwd=project_root,
        check=True,  # hard-fail on refdb corruption
    )
    branches = [
        line.strip()
        for line in result.stdout.splitlines()
        if line.strip()
    ]
    for b in branches:
        if not b.startswith("iterate/"):
            raise GitError(
                f"for-each-ref returned non-iterate ref: {b!r}"
            )
    return branches


def build_branch_to_worktree_map(
    records: list[WorktreeRecord],
    current_worktree_path: str,
) -> dict[str, str]:
    """Map `record.branch → record.path` for every record EXCEPT current (R4-H2).

    Paths are stored normalized via ``_normalize_path`` (normcase+abspath,
    no ``.resolve()``) so downstream serialization into
    ``locked_in_worktree`` is already Windows-stable and cross-platform
    comparable without further munging. R3-L9 + R5-H1.
    """
    normalized_current = _normalize_path(current_worktree_path)
    mapping: dict[str, str] = {}
    for rec in records:
        if rec.branch is None:
            continue  # detached linked worktree — no branch to occupy
        normalized_rec_path = _normalize_path(rec.path)
        if normalized_rec_path == normalized_current:
            continue  # current worktree — excluded by classification
        mapping[rec.branch] = normalized_rec_path
    return mapping


def derive_arrays(branches: list[dict[str, Any]]) -> dict[str, list[str]]:
    """Derive backward-compat top-level arrays from branches[]."""
    buckets = {STATUS_ACTIVE: [], STATUS_STALE: [], STATUS_LOCKED: []}
    for b in branches:
        buckets[b["status"]].append(b["name"])
    return {
        "active": buckets[STATUS_ACTIVE],
        "stale": buckets[STATUS_STALE],
        "locked": buckets[STATUS_LOCKED],
    }


def collect(
    project_root: Path,
    *,
    main_override: str | None = None,
    per_call_timeout: float = DEFAULT_PER_CALL_TIMEOUT,
) -> dict[str, Any]:
    """End-to-end: returns the JSON payload dict (schema v1)."""
    errors: list[str] = []

    # Resolve repo_root — check=True, propagates GitError on non-git dir.
    root_result = run_git(
        ["rev-parse", "--show-toplevel"],
        cwd=project_root,
        check=True,
    )
    repo_root = str(Path(root_result.stdout.strip()).resolve())

    # Enumerate worktrees — check=True, corrupted state is fatal.
    worktree_result = run_git(
        ["worktree", "list", "--porcelain"],
        cwd=project_root,
        check=True,
    )
    records, parse_errors = parse_worktree_porcelain(worktree_result.stdout)
    errors.extend(parse_errors)

    current_branch = detect_current_branch(project_root)
    branch_to_worktree_path = build_branch_to_worktree_map(
        records, repo_root
    )

    main_name, main_ref, main_errors = detect_main(
        project_root, main_override
    )
    errors.extend(main_errors)

    iterate_branches = enumerate_iterate_branches(project_root)

    branches, classify_errors = classify_branches(
        project_root,
        iterate_branches,
        current_branch=current_branch,
        branch_to_worktree_path=branch_to_worktree_path,
        main_ref=main_ref,
        per_call_timeout=per_call_timeout,
    )
    errors.extend(classify_errors)

    arrays = derive_arrays(branches)

    payload: dict[str, Any] = {
        "version": SCHEMA_VERSION,
        "repo_root": repo_root,
        "main": main_name,
        "main_ref": main_ref,
        "current": current_branch,
        "branches": branches,
        "active": arrays["active"],
        "stale": arrays["stale"],
        "locked": arrays["locked"],
        "errors": errors,
    }
    return payload


# -----------------------------------------------------------------------------
# CLI
# -----------------------------------------------------------------------------


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=__doc__.splitlines()[0] if __doc__ else None
    )
    p.add_argument("--project-root", default=".")
    p.add_argument(
        "--main",
        default=None,
        help="Override default-branch detection (e.g. `trunk`)",
    )
    p.add_argument(
        "--timeout-seconds",
        type=float,
        default=DEFAULT_PER_CALL_TIMEOUT,
        help="Per-call git timeout; global deadline = 6× this value",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    try:
        args = _parse_args(argv)
        project_root = Path(args.project_root)
        payload = collect(
            project_root,
            main_override=args.main,
            per_call_timeout=args.timeout_seconds,
        )
    except FileNotFoundError:
        # subprocess.Popen raises FileNotFoundError when git.exe is not
        # in PATH. On Windows the message is "[WinError 2] The system
        # cannot find the file specified" — no "git" substring — so
        # string-matching is unreliable. Every FileNotFoundError in this
        # flow comes from the `git` spawn; catch it unconditionally.
        print("git binary not found in PATH", file=sys.stderr)
        return 1
    except GitError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    # R3-L9 + R5-H1: field-specific path serialization already handled
    # upstream. All payload values here are JSON primitives.
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
