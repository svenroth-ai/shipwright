"""Guarded git commit-path that backfills the union ``.gitattributes`` lines into
a managed repo — split out of ``gitattributes_union`` (which stays the pure,
file-path-loadable merge-logic SSoT) so each module stays within the bloat limit.

``self_heal_gitattributes`` is the commit-path sibling of the pure
``gitattributes_union.merge_into`` (mirrors the test split:
``test_gitattributes_union.py`` vs ``test_gitattributes_union_selfheal.py``).
Modeled on ``reconcile_main_triage``: a structured no-op under every safety guard
rather than ever corrupting git state; never raises for an expected condition —
returns a :class:`HealResult`. Imported normally (``from lib.gitattributes_selfheal
import …``), so unlike ``gitattributes_union`` it is NEVER loaded by the adopt
scaffolder's file-path loader and may ``from lib.* import`` at module scope.
"""

from __future__ import annotations

import contextlib
import os
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from lib.gitattributes_union import (  # noqa: E402  (pure merge-logic SSoT)
    GITATTRIBUTES_PATH,
    UNION_PATHS,
    merge_into,
    missing_union_paths,
)

#: Truthy spellings of ``$CI`` that disable the auto-commit unless ``allow_ci``.
_CI_TRUTHY = frozenset({"1", "true", "yes", "on"})


@dataclass
class HealResult:
    """Outcome of :func:`self_heal_gitattributes`.

    ``status`` ∈ {``committed``, ``no_change``, ``skipped``, ``error``}.
    ``reason`` carries the guard name for ``skipped`` / ``error``; ``added`` lists
    the union paths newly declared in a ``committed`` run.
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
    """Write ``text`` verbatim (UTF-8, no newline translation) via tempfile +
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


def _restore_gitattributes(ga_path: Path, original: str | None, unstage) -> None:
    """Best-effort rollback after a failed/timed-out commit, so the contract
    ('guarded no-op rather than ever corrupting git state') holds on failure:
    unstage the path, then restore (or delete) the working-tree file. Never
    raises — there is already a real error to report."""
    with contextlib.suppress(OSError, subprocess.TimeoutExpired):
        unstage("reset", "-q", "--", GITATTRIBUTES_PATH)
    with contextlib.suppress(OSError):
        if original is None:
            ga_path.unlink(missing_ok=True)
        else:
            _atomic_write(ga_path, original)


def self_heal_gitattributes(
    project_root: Path | str,
    *,
    allow_ci: bool = False,
) -> HealResult:
    """Backfill the union ``.gitattributes`` lines into ``project_root`` as one
    ``chore`` commit on the current branch.

    Acts ONLY on a Shipwright-managed repo (tracks at least one append-log
    artifact) that is missing union lines. A batch of guards make it a structured
    no-op rather than ever corrupting git state. Never raises for an expected
    condition — returns a structured :class:`HealResult`.
    """
    from lib.worktree_isolation import GitError, run_git  # noqa: E402

    root = Path(project_root)

    def _git(*args: str):
        # Swallow a hung-git timeout into a non-zero result so no guard probe can
        # propagate TimeoutExpired (honors "never raises"); the commit itself uses
        # run_git directly with a generous timeout + explicit catch.
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
    # op-in-progress before detached-HEAD (a rebase detaches HEAD, so the
    # in-progress reason is the more actionable one).
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
    tracked = _git("ls-files", "--", *UNION_PATHS).stdout.strip()
    if not tracked:
        return HealResult("skipped", "no_tracked_append_log")

    # --- compute the merge --------------------------------------------------
    ga_path = repo_root / GITATTRIBUTES_PATH
    # errors="replace": a non-UTF-8 file must not raise UnicodeDecodeError (uncaught by setup.main) — fail-soft, congruent with gitignore_selfheal.
    existing = ga_path.read_text("utf-8", errors="replace") if ga_path.exists() else None
    merged, changed = merge_into(existing)
    if not changed:
        return HealResult("no_change")

    # Skip rather than risk a partial ``git commit -- <path>`` interacting with a
    # user's staged WIP. The backfill is always an unstaged absence → non-empty index = no-op.
    if _git("diff", "--cached", "--quiet").returncode != 0:
        return HealResult("skipped", "staged_changes")

    added = missing_union_paths(existing)
    _atomic_write(ga_path, merged)
    subject = "chore: scaffold append-log union merge driver into .gitattributes"

    # Stage then commit ONLY .gitattributes (handles both the new-file and
    # modified-file cases; an untracked new file needs the explicit add). On ANY
    # failure, roll back so a rejected/timed-out commit leaves git state clean.
    # The commit fires the bloat pre-commit hook, whose cold `uv run` routinely
    # exceeds run_git's 15s default — and this runs on a brand-new worktree, the
    # most likely place for a cold env — so give it a generous timeout and treat
    # a timeout as a structured error rather than letting it crash the caller.
    try:
        add = _git("add", "--", GITATTRIBUTES_PATH)
        if add.returncode != 0:
            _restore_gitattributes(ga_path, existing, _git)
            return HealResult("error", f"add_failed: {add.stderr.strip()[:300]}")
        commit = run_git(
            ["commit", "-m", subject, "--", GITATTRIBUTES_PATH],
            cwd=repo_root, check=False, timeout=120.0,
        )
    except subprocess.TimeoutExpired:
        _restore_gitattributes(ga_path, existing, _git)
        return HealResult("error", "commit_timeout")
    if commit.returncode != 0:
        _restore_gitattributes(ga_path, existing, _git)
        return HealResult("error", f"commit_failed: {commit.stderr.strip()[:300]}")
    return HealResult("committed", added=added, commit_subject=subject)
