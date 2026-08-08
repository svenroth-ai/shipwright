"""Run-ID-scoped commit trailer reader and run_id -> commit map builder.

Backs the git-history backfill in ``event_context_index.py``: most recorded
events carry an empty ``changed_files``/``commit`` (the worktree flow ships
``commit=""`` by design and links via the F6 commit's ``Run-ID:`` footer
instead), so this module recovers both from git history for any event whose
``run_id`` matches a commit's trailer.

Trimmed to ``Run-ID:`` only after architecture review (both external
reviewers plus an internal Opus arbitration) — an earlier draft also read
``ADR:``/``Area:``/``FR:`` trailers, but nothing in this change consumes
them. See
``.shipwright/planning/iterate/2026-08-07-events-context-backfill-keys.md``,
``## Architecture Review``.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any

_RUN_ID_TRAILER_RE = re.compile(r"(?im)^[ \t]*Run-ID:[ \t]*(\S+)[ \t]*$")
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_TIMEOUT = 60
MAX_CHANGED_FILES = 50


def _run_git(repo_root: Path, args: list[str], timeout: int) -> tuple[str, str]:
    """Run ``git -C repo_root <args>``. Returns (status, stdout).

    ``status`` is one of ``"ok"`` / ``"timeout"`` / ``"error"`` — never
    raises. ``-c core.quotepath=false`` so non-ASCII paths arrive
    addressable rather than octal-escaped.
    """
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), "-c", "core.quotepath=false", *args],
            capture_output=True, text=True, timeout=timeout,
            encoding="utf-8", errors="replace",
        )
    except subprocess.TimeoutExpired:
        return "timeout", ""
    except OSError:
        return "error", ""
    if result.returncode != 0:
        return "error", ""
    return "ok", result.stdout


def resolve_base_ref(repo_root: Path | str) -> tuple[str, str] | None:
    """The ``(ref_name, resolved_sha)`` to scan, or ``None`` if none resolve.

    A worktree in this repo checks out ONLY its own ``iterate/<slug>``
    branch, so there is normally no local ``main`` to fall back to — unlike
    ``shared/scripts/lib/branch_base.py``'s ``resolve_default_branch()``,
    which is safe to fall back to a bare ``"main"`` only because its caller
    (the campaign loop) always runs from a checkout that has one. Walking
    the remote-tracking refs explicitly, with local ``HEAD`` as the last
    resort, is correct in both contexts (worktree and a bare test fixture
    repo with no remote at all).

    Returns the resolved sha alongside the ref name (one ``rev-parse`` per
    call, not two — a caller that previously re-resolved the same ref
    inside ``build_run_id_commit_map`` no longer needs to) so a cheap,
    cache-validity re-check (compare this sha against a previously cached
    ``resolved_sha``) can detect that new commits landed without re-walking
    history.
    """
    root = Path(repo_root)
    for ref in ("origin/HEAD", "origin/main", "origin/master", "HEAD"):
        status, out = _run_git(
            root, ["rev-parse", "--verify", "--quiet", "--end-of-options", ref], timeout=10,
        )
        sha = out.strip()
        if status == "ok" and _SHA_RE.match(sha):
            return ref, sha
    return None


def _parse_bodies(raw: str) -> dict[str, str]:
    """sha -> commit body, from ``%H%x00%B%x00`` formatted ``git log`` output.

    Every candidate sha token is validated against the 40-hex-char shape
    before its "body" is trusted — a resync point, not a crash, if a
    hostile commit body happened to contain a literal NUL byte.
    """
    bodies: dict[str, str] = {}
    tokens = raw.split("\x00")
    i = 0
    while i + 1 < len(tokens):
        candidate = tokens[i].strip()
        if _SHA_RE.match(candidate):
            bodies[candidate] = tokens[i + 1]
            i += 2
        else:
            i += 1
    return bodies


def _parse_files(raw: str) -> dict[str, list[str]]:
    """sha -> changed file paths, from ``%x00%H`` + ``--name-only`` output.

    No commit-body text is present in this call's format at all — only the
    sha and git's own newline-listed filenames (which cannot contain NUL) —
    so there is no delimiter-safety question for this half of the scan.
    """
    files: dict[str, list[str]] = {}
    for chunk in raw.split("\x00")[1:]:
        lines = chunk.split("\n")
        candidate = lines[0].strip()
        if not _SHA_RE.match(candidate):
            continue
        files[candidate] = [ln.strip() for ln in lines[1:] if ln.strip()]
    return files


def build_run_id_commit_map(repo_root: Path | str, base_ref_pin: tuple[str, str] | None) -> dict[str, Any]:
    """Build ``{run_id: {"sha", "changed_files", "changed_files_truncated"}}``.

    ``base_ref_pin`` is ``resolve_base_ref()``'s ``(ref_name, resolved_sha)``
    — already pinned to an immutable sha by the caller (external review
    openai finding #4: two separate ``git log <ref>`` calls against a branch
    name that a concurrent fetch/push could advance between them would let
    Call A and Call B see different history). Accepting the pin instead of
    re-resolving it here means one ``rev-parse`` per build, not two.

    Two ``git log`` calls total (not one per event) — see module docstring.
    Both carry ``--grep=Run-ID: -i`` so git itself skips commits that cannot
    possibly match before computing the (expensive, per-commit) ``--name-only``
    diff for Call B; the predicate is a plain, case-insensitive substring
    (matching `_RUN_ID_TRAILER_RE`'s own ``(?i)``) and a strict superset of
    the anchored regex, so it can only ever admit more commits than the
    Python regex accepts, never fewer. Merge commits are excluded
    (``--no-merges``): ``--name-only`` emits no diff for a multi-parent
    commit, so a Run-ID trailer landing only on a merge would otherwise
    resolve to a confidently-wrong empty file list. Nothing else is excluded
    by shape — a `git revert` whose message legitimately carries a fresh,
    correct `Run-ID:` (e.g. an iterate whose fix genuinely is `git revert
    <bad-sha>`) recovers normally; an EARLIER draft additionally excluded
    every `Revert `-subject commit to guard against a hand-edited revert
    pasting back another run's trailer, but external review (openai,
    iterate-2026-08-07-events-context-backfill-keys) correctly flagged that
    as broader than the spec's stated merge-only exclusion and costing a
    real case to guard a contrived one — removed. Duplicate Run-ID across
    commits (the normal case here —
    repair commits, triage folds): the union of changed files across every
    match, sha = the newest match (git log lists newest-first, and the map
    keeps the FIRST-seen sha per run_id since iteration follows that order).

    Returns ``status`` ``"ok"`` / ``"timeout"`` / ``"no-repo"`` so a caller
    can surface a degraded scan rather than silently reflect it only as
    more ``unavailable`` per-entry rows.
    """
    root = Path(repo_root)
    if not base_ref_pin:
        return {"status": "no-repo", "commits_scanned": 0, "base_ref_used": None,
                "resolved_sha": None, "map": {}}
    base_ref, pinned_sha = base_ref_pin

    status_a, raw_bodies = _run_git(
        root, ["log", pinned_sha, "--no-merges", "--grep=Run-ID:", "-i",
               "--pretty=format:%H%x00%B%x00", "--"], timeout=_TIMEOUT,
    )
    if status_a != "ok":
        return {"status": "timeout" if status_a == "timeout" else "no-repo",
                "commits_scanned": 0, "base_ref_used": base_ref,
                "resolved_sha": pinned_sha, "map": {}}

    status_b, raw_files = _run_git(
        root, ["log", pinned_sha, "--no-merges", "--no-renames", "--name-only",
               "--grep=Run-ID:", "-i", "--pretty=format:%x00%H", "--"], timeout=_TIMEOUT,
    )
    if status_b != "ok":
        return {"status": "timeout" if status_b == "timeout" else "no-repo",
                "commits_scanned": 0, "base_ref_used": base_ref,
                "resolved_sha": pinned_sha, "map": {}}

    bodies_by_sha = _parse_bodies(raw_bodies)
    files_by_sha = _parse_files(raw_files)

    grouped: dict[str, dict[str, Any]] = {}
    for sha, body in bodies_by_sha.items():
        match = _RUN_ID_TRAILER_RE.search(body)
        if not match:
            continue
        run_id = match.group(1)
        entry = grouped.setdefault(run_id, {"sha": sha, "files": set()})
        entry["files"].update(files_by_sha.get(sha, []))

    resolved: dict[str, dict[str, Any]] = {}
    for run_id, entry in grouped.items():
        # Non-dot-prefixed (source) paths sort before dot-prefixed
        # (framework-bookkeeping: `.shipwright/`, `.github/`, …) ones, so a
        # commit with >MAX_CHANGED_FILES changed files keeps the paths that
        # actually carry ranking signal instead of losing them to plain
        # ASCII order, which puts every dot-path first.
        files = sorted(entry["files"], key=lambda p: (p.startswith("."), p))
        resolved[run_id] = {
            "sha": entry["sha"],
            "changed_files": files[:MAX_CHANGED_FILES],
            "changed_files_truncated": len(files) > MAX_CHANGED_FILES,
        }

    return {
        "status": "ok",
        "commits_scanned": len(bodies_by_sha),
        "base_ref_used": base_ref,
        "resolved_sha": pinned_sha,
        "map": resolved,
    }
