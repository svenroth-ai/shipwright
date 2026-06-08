"""Self-heal the canonical ``.shipwright/`` artifact-ignore block into managed repos.

Sibling of :func:`lib.gitattributes_union.self_heal_gitattributes` (campaign
2026-06-08-triage-outbox-delivery / D3). The canonical ``.gitignore`` block
(SSoT ``shared/templates/shipwright-gitignore.template``) ignores everything
under ``.shipwright/`` and re-includes only the tracked SDLC-doc homes — which
INCLUDES keeping the per-tree ``triage.outbox.jsonl`` background buffer ignored.
That block reaches NEW repos at adopt time (``gitignore_canon`` Step E.6), but an
already-adopted repo — or one whose plugin cache predates a template revision —
can be MISSING it ("shared/ change = deployed is false for adopted repos", Codex
Q6). This module backfills it on the repo's next iterate as one guarded ``chore``
commit on the current branch, so the fix ships in the iterate PR.

The merge itself is single-sourced in :func:`lib.gitignore_canon.plan_merge`;
this module only owns the guarded git commit-path (modeled on
``self_heal_gitattributes``: never raises for an expected condition, rolls back
on any commit failure, no-op in the monorepo where the block already exists).
"""

from __future__ import annotations

import contextlib
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

_SCRIPTS_ROOT = Path(__file__).resolve().parents[1]  # shared/scripts
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from lib.gitignore_canon import plan_merge  # noqa: E402

#: Where the canonical block lives in a managed repo (repo root).
GITIGNORE_PATH = ".gitignore"

#: The managed-repo marker: a repo that tracks at least one append-log artifact.
#: Kept congruent with ``gitattributes_union.UNION_PATHS`` so the two self-heals
#: act on exactly the same population of Shipwright-managed repos.
MANAGED_MARKER_PATHS: tuple[str, ...] = (
    "shipwright_events.jsonl",
    ".shipwright/triage.jsonl",
)

#: Truthy spellings of ``$CI`` that disable the auto-commit unless ``allow_ci``.
_CI_TRUTHY = frozenset({"1", "true", "yes", "on"})


@dataclass
class HealResult:
    """Outcome of :func:`self_heal_gitignore`.

    ``status`` ∈ {``committed``, ``no_change``, ``skipped``, ``error``}.
    ``reason`` carries the guard name for ``skipped`` / ``error``; ``added`` lists
    the canonical rules newly written in a ``committed`` run.
    """

    status: str
    reason: str = ""
    added: list[str] = field(default_factory=list)
    commit_subject: str = ""

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "reason": self.reason,
            "added": self.added,
            "commit_subject": self.commit_subject,
        }


def _ci_active() -> bool:
    return os.environ.get("CI", "").strip().lower() in _CI_TRUTHY


def _atomic_write(path: Path, text: str) -> None:
    """Write *text* verbatim (UTF-8, no newline translation) via tempfile +
    os.replace so a concurrent reader never sees a torn file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)
        os.replace(tmp, path)
    except Exception:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def _restore(gi_path: Path, original: str | None, reset) -> None:
    """Best-effort rollback after a failed/timed-out commit: unstage then restore
    (or delete) the working-tree file. Never raises — there is already a real
    error to report."""
    # If the suppressed `reset` itself fails, .gitignore may stay STAGED — but that
    # is fail-safe: the step-5 outbox sweep's staged_changes guard then SKIPS (now
    # surfaced, LOW-1) and re-sweeps next setup; no silent data loss.
    with contextlib.suppress(OSError, subprocess.TimeoutExpired):
        reset("reset", "-q", "--", GITIGNORE_PATH)
    with contextlib.suppress(OSError):
        if original is None:
            gi_path.unlink(missing_ok=True)
        else:
            _atomic_write(gi_path, original)


def self_heal_gitignore(
    project_root: Path | str,
    *,
    allow_ci: bool = False,
) -> HealResult:
    """Backfill the canonical ``.shipwright/`` ignore block into ``project_root``
    as one ``chore`` commit on the current branch.

    Acts ONLY on a Shipwright-managed repo (tracks at least one append-log
    artifact) that is MISSING canonical rules. A batch of guards make it a
    structured no-op rather than ever corrupting git state. Never raises for an
    expected condition — returns a structured :class:`HealResult`.
    """
    from lib.worktree_isolation import GitError, run_git  # noqa: E402

    root = Path(project_root)

    def _git(*args: str):
        # Swallow a hung-git timeout into a non-zero result so no guard probe can
        # propagate TimeoutExpired (honors "never raises").
        try:
            return run_git(list(args), cwd=repo_root, check=False)
        except subprocess.TimeoutExpired:
            return subprocess.CompletedProcess(args, 124, "", "git timed out")

    # --- resolve repo root (also the not-a-git-repo probe) -----------------
    try:
        top = run_git(
            ["rev-parse", "--show-toplevel"], cwd=root, check=True
        ).stdout.strip()
    except GitError:
        return HealResult("skipped", "not_a_git_repo")
    except (OSError, subprocess.TimeoutExpired) as exc:
        return HealResult("error", f"git_probe_failed: {exc}")
    repo_root = Path(top)

    # --- cheap guards -------------------------------------------------------
    if _ci_active() and not allow_ci:
        return HealResult("skipped", "ci_without_optin")
    for ref in ("MERGE_HEAD", "CHERRY_PICK_HEAD", "REVERT_HEAD"):
        if _git("rev-parse", "--verify", "--quiet", ref).returncode == 0:
            return HealResult("skipped", "op_in_progress")
    for rel in ("rebase-merge", "rebase-apply", "BISECT_LOG"):
        probe = _git("rev-parse", "--git-path", rel)
        if probe.returncode != 0:
            continue
        p = Path(probe.stdout.strip())
        if (p if p.is_absolute() else repo_root / p).exists():
            return HealResult("skipped", "op_in_progress")
    if _git("symbolic-ref", "--quiet", "HEAD").returncode != 0:
        return HealResult("skipped", "detached_head")

    # --- only act on Shipwright-managed append-log repos -------------------
    tracked = _git("ls-files", "--", *MANAGED_MARKER_PATHS).stdout.strip()
    if not tracked:
        return HealResult("skipped", "no_tracked_append_log")

    # --- compute the merge (pure; single-sourced in gitignore_canon) -------
    gi_path = repo_root / GITIGNORE_PATH
    # ``errors="replace"`` keeps a non-UTF-8 ``.gitignore`` from raising a
    # UnicodeDecodeError — a ValueError that setup.main's (GitError, OSError)
    # handler does NOT catch, which would crash setup and break fail-soft.
    existing = (
        gi_path.read_text(encoding="utf-8", errors="replace")
        if gi_path.exists() else None
    )
    merged, changed, added = plan_merge(existing or "")
    if not changed:
        return HealResult("no_change")

    # Skip rather than risk a partial ``git commit -- <path>`` interacting with a
    # user's staged WIP. The backfill is always an unstaged absence.
    if _git("diff", "--cached", "--quiet").returncode != 0:
        return HealResult("skipped", "staged_changes")

    _atomic_write(gi_path, merged)
    subject = (
        "chore: scaffold canonical .shipwright/ artifact-ignore block into .gitignore"
    )

    # Stage then commit ONLY .gitignore. On ANY failure, roll back so a
    # rejected/timed-out commit leaves git state clean. The commit fires the bloat
    # pre-commit hook, whose cold ``uv run`` on a brand-new worktree routinely
    # exceeds run_git's 15s default — give it a generous timeout + structured error.
    try:
        add = _git("add", "--", GITIGNORE_PATH)
        if add.returncode != 0:
            _restore(gi_path, existing, _git)
            return HealResult("error", f"add_failed: {add.stderr.strip()[:300]}")
        commit = run_git(
            ["commit", "-m", subject, "--", GITIGNORE_PATH],
            cwd=repo_root, check=False, timeout=120.0,
        )
    except subprocess.TimeoutExpired:
        _restore(gi_path, existing, _git)
        return HealResult("error", "commit_timeout")
    if commit.returncode != 0:
        _restore(gi_path, existing, _git)
        return HealResult("error", f"commit_failed: {commit.stderr.strip()[:300]}")
    return HealResult("committed", added=added, commit_subject=subject)
