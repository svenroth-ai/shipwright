"""MAIN-repo-root resolvers for advisory / fail-soft callers.

Thematic home for "resolve the MAIN repo's working-tree root, git-worktree-aware,
without bricking the caller" helpers. It hosts two. They share an intent but have
**deliberately different failure contracts**, so a caller picks the one whose
contract matches (the strict, raising variant is ``lib.git_base.main_repo_root``,
also re-exported as ``worktree_isolation.main_repo_root`` for back-compat):

- :func:`main_repo_root_or` — returns a ``Path`` ALWAYS; on any git failure it
  degrades to ``fallback`` (default ``start``). A thin adapter over
  ``lib.git_base.main_repo_root`` for the hot-path bloat hooks
  (``check_file_size`` PostToolUse recorder + ``bloat_gate_on_stop``), which MUST
  key the marker / baseline / re-measure off the SAME canonical MAIN root — never
  ``Path.cwd()`` (a hook firing with cwd != repo-root would write the marker into a
  nested ``.shipwright/locks/`` that the root-anchored gitignore misses; the leak
  class ADR-089 hard-gated for finalize — see ``conventions.md``,
  iterate-2026-06-09 / trg-7640bd14).

- :func:`resolve_main_repo_root` — returns ``Path | None``; ``None`` is the
  documented fail-soft signal a caller turns into ``project_root`` via
  ``resolve_main_repo_root(...) or project_root``. It distinguishes a definitive
  *"not a git repository"* (silent ``None``) from *broken git* (binary missing /
  timeout / empty / unexpected / mojibaked output), which warns first — the latter
  risks silent data loss in a worktree run. Shared primitive behind the
  worktree-aware **decision-drop** directory resolvers
  (``tools/write_decision_drop.py``, ``tools/aggregate_decisions.py``), the iterate
  F11 verifier (``tools/verifiers/iterate_checks.py``), the plugin-sync Stop hook
  (``hooks/plugin_sync_reminder_on_stop.py``), and the compliance Group-F detective.

History (iterate-2026-06-12-repo-root-resolver-relocate)
--------------------------------------------------------
``resolve_main_repo_root`` lived in ``lib/events_log.py`` until this iterate, where
it was a repo-root primitive squatting in the event-log module — its own docstring
conceded it was "no longer used to locate the event log". It is relocated here to
sit beside its sibling; ``events_log`` re-exports it via a thin lazy shim for
back-compat. This reverses the 2026-05-29
(``iterate-2026-05-29-events-jsonl-worktree-commit``) "resolve_main_repo_root
stays [in events_log]" decision, which kept it in place only because the
events-path redirect removal happened to live in the same file.

Both resolvers live in this OWN module — not appended to ``worktree_isolation.py``
— to avoid ratcheting that already-grandfathered (>300 LOC) module past its bloat
ceiling.
"""

from __future__ import annotations

import os
import subprocess
import warnings
from pathlib import Path

from lib.git_base import GitError, main_repo_root

# git path-resolution is a single fast call; cap it so a hung git cannot wedge a
# caller (e.g. an iterate finalize append or a Stop-hook resolution).
_GIT_TIMEOUT_SECONDS = 15.0

# Environment variables that override git's repo discovery. If any of these leak
# in from the caller's environment, `git rev-parse` would resolve a DIFFERENT
# repo than ``cwd=project_root`` — silently targeting the wrong repo. Strip them
# so resolution is pinned to project_root.
_GIT_DISCOVERY_OVERRIDES = ("GIT_DIR", "GIT_COMMON_DIR", "GIT_WORK_TREE")


def _git_env() -> dict[str, str]:
    """Process environment with git repo-discovery overrides removed."""
    env = dict(os.environ)
    for var in _GIT_DISCOVERY_OVERRIDES:
        env.pop(var, None)
    return env


def main_repo_root_or(start: Path, fallback: Path | None = None) -> Path:
    """Return the MAIN working tree for ``start`` (resolving from any subdir AND
    from a linked worktree), or ``fallback`` (default ``start``) when git
    resolution fails — ``start`` not in a repo, git missing, timeout, or
    unexpected output. Every failure mode degrades to ``fallback`` so advisory
    hooks never break the tool flow."""
    try:
        return main_repo_root(start)
    except (GitError, OSError, subprocess.SubprocessError, ValueError):
        return fallback if fallback is not None else start


def resolve_main_repo_root(project_root: Path | str) -> Path | None:
    """Return the MAIN repo's working-tree root, git-worktree-aware.

    From inside a linked git worktree this resolves to the **main** repo
    root (the worktree's ``--git-common-dir`` parent); in a plain checkout
    it is the repo's own top level. Returns ``None`` when ``project_root``
    is not a git repository, or when git is unavailable / returns an
    unexpected layout — callers then fall back to ``project_root`` itself.

    A ``warnings.warn`` diagnostic is emitted only when git is *broken*
    (binary missing, timeout, empty / unexpected output). A plain "not a
    git repository" answer returns ``None`` *silently*: that is a
    definitive, no-data-loss result — a non-git project's artifacts
    genuinely live next to ``project_root``.

    Shared primitive behind the worktree-aware decision-drop directory
    resolvers (``tools/write_decision_drop.py`` / ``tools/aggregate_decisions.py``),
    the iterate F11 verifier, the plugin-sync Stop hook, and the compliance
    Group-F detective. Re-exported from ``lib.events_log`` for back-compat.
    """
    project_root = Path(project_root)

    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--git-common-dir"],
            cwd=str(project_root),
            capture_output=True,
            text=True,
            # WP7/F27: git emits the common-dir path as UTF-8 bytes. Without
            # an explicit encoding the platform default (cp1252 on Windows)
            # mojibakes a non-ASCII project path, so the resolved main root
            # points at a directory that does not exist — and worktree
            # decision-drops are silently written there and lost. Pin UTF-8;
            # the exists() guard below fail-softs if anything still slips.
            encoding="utf-8",
            errors="replace",
            check=False,
            shell=False,
            timeout=_GIT_TIMEOUT_SECONDS,
            env=_git_env(),
        )
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        # git binary missing / un-spawnable / hung — we cannot tell whether
        # this is a worktree, so a fallback here MAY be silent data loss.
        warnings.warn(
            f"resolve_main_repo_root: git unavailable for {project_root} "
            f"({exc!r}) — the caller falls back to {project_root} itself. "
            "An iterate worktree run may write a throwaway, soon-discarded "
            "artifact.",
            stacklevel=2,
        )
        return None

    if proc.returncode != 0:
        # Definitive "not a git repository" — the fallback is correct, not
        # a failure. Silent by design (non-git projects + test tmp dirs).
        return None

    common_dir = proc.stdout.strip()
    if not common_dir:
        warnings.warn(
            f"resolve_main_repo_root: `git rev-parse --git-common-dir` "
            f"returned empty output in {project_root} — the caller falls "
            f"back to {project_root} itself.",
            stacklevel=2,
        )
        return None

    common_path = Path(common_dir)
    if not common_path.is_absolute():
        # Without --path-format=absolute, `--git-common-dir` yields a path
        # relative to the git command's cwd, which we pinned to project_root.
        common_path = (project_root / common_path).resolve()

    # `--git-common-dir` returns the MAIN repo's .git directory; its parent
    # is the canonical project root. A linked worktree's *git-dir* is
    # `.git/worktrees/<name>`, but its *common* dir is the top-level `.git`
    # — so this is worktree-correct. Defensive: only trust a path that
    # actually ends in ".git".
    if common_path.name == ".git":
        resolved_root = common_path.parent
        # WP7/F27: a mojibaked (or otherwise corrupt) path can name a
        # directory that does not exist on disk. Returning it would send
        # worktree decision-drops into a phantom dir where they are lost.
        # Fail-soft to None so the caller falls back to project_root, which
        # is guaranteed real.
        if not resolved_root.exists():
            warnings.warn(
                f"resolve_main_repo_root: resolved main root "
                f"{str(resolved_root)!r} does not exist (corrupt/mojibaked "
                f"git output?) for {project_root} — the caller falls back to "
                f"{project_root} itself.",
                stacklevel=2,
            )
            return None
        return resolved_root

    warnings.warn(
        f"resolve_main_repo_root: unexpected git-common-dir "
        f"{str(common_path)!r} (not a `.git` directory) for {project_root} "
        f"— the caller falls back to {project_root} itself.",
        stacklevel=2,
    )
    return None
