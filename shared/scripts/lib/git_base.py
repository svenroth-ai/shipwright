"""Low-level git subprocess primitives (dependency-free leaf module).

Extracted from :mod:`worktree_isolation` so :mod:`repo_root` can use
``GitError`` / ``main_repo_root`` WITHOUT importing ``worktree_isolation`` —
that closed the ``worktree_isolation -> events_log -> repo_root ->
worktree_isolation`` import cycle (CodeQL ``py/cyclic-import``). This module
imports only the stdlib, so both ``worktree_isolation`` (which re-exports these
names for its existing callers) and ``repo_root`` depend on it without forming a
cycle.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

DEFAULT_GIT_TIMEOUT = 15.0

#: Generous budget for a git call that fires this repo's pre-commit hooks, whose
#: cold ``uv run`` routinely exceeds :data:`DEFAULT_GIT_TIMEOUT` on a fresh worktree.
HOOK_GIT_TIMEOUT = 120.0

#: Conventional shell exit code for "killed by a timeout". :func:`run_git_soft`
#: reports it so a timeout reaches a caller's existing ``returncode != 0`` branch
#: instead of raising past it.
TIMEOUT_RETURNCODE = 124


class GitError(RuntimeError):
    """Non-zero exit from a git call invoked with ``check=True``."""


# -----------------------------------------------------------------------------
# Git subprocess helper (hygiene mirrors tools/list_iterate_branches.run_git)
# -----------------------------------------------------------------------------


def _timeout_message(args: list[str], timeout: float) -> str:
    """The one wording for a killed-on-timeout git call, shared by both ``_soft``
    wrappers so the operator-facing index.lock hint cannot drift out of one of them."""
    return (
        f"git {args[0] if args else '?'} timed out after {timeout}s "
        f"(process killed; a stale .git/index.lock may need clearing)"
    )


def _popen_git(
    args: list[str],
    *,
    cwd: Path,
    timeout: float,
    binary: bool,
) -> tuple[int, Any, Any]:
    """Shared execution core: argv, capture, and timeout kill-and-reap.

    Returns ``(returncode, stdout, stderr)``, typed ``Any`` on the streams so the
    two wrappers' narrow public types (``CompletedProcess[str]`` /
    ``CompletedProcess[bytes]``) are the only claims made — a union here would make
    both unverifiable rather than either checkable.

    ``binary`` changes TWO things, not one:

    1. the captured streams come back undecoded, and
    2. **no universal-newline translation happens.** Text mode wraps the pipes in
       ``io.TextIOWrapper`` with ``newline=None``, so a blob's ``\\r\\n`` — and a lone
       ``\\r`` — arrive as ``\\n``; binary mode hands back what git actually wrote.

    Point 2 is easy to miss and matters to anyone migrating another caller: a
    comparison that was implicitly newline-normalised on one side stops being so.
    The store readers are unaffected because they run the bytes through
    :func:`lib.sweep_text.normalize_lines` (or ``.strip()``), which absorbs the
    ``\\r`` explicitly — and for a LONE ``\\r`` the byte path is the more faithful of
    the two, since text mode would have split the line where git stored none.

    Text mode passes exactly the kwargs :func:`run_git` has always passed.
    """
    stream_kwargs: dict[str, object] = (
        {"text": False}
        if binary
        else {"text": True, "encoding": "utf-8", "errors": "replace"}
    )
    # `encoding` and `errors` (now reaching Popen via **stream_kwargs, text branch only)
    # are available since Python 3.6 — the project requires 3.11+ (see pyproject.toml).
    # KEPT rather than removed: the rules may no longer match through the ** spread, but
    # `--config auto` needs network so that could not be settled locally, and a wrong
    # removal reddens a Required Check. Re-check when the scanner next runs (trg filed).
    # nosemgrep: python.lang.compatibility.python36.python36-compatibility-Popen1,python.lang.compatibility.python36.python36-compatibility-Popen2
    proc = subprocess.Popen(
        ["git", "--no-pager", "-C", str(cwd), *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        shell=False,
        **stream_kwargs,
    )
    try:
        out, err = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.communicate()
        raise
    return proc.returncode, out, err


def run_git(
    args: list[str],
    *,
    cwd: Path,
    timeout: float = DEFAULT_GIT_TIMEOUT,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    """Run a git command with consistent hygiene.

    - ``--no-pager`` prevents pager hangs.
    - ``-C <cwd>`` scopes the call to the requested repo.
    - ``shell=False`` + list argv — no injection surface.
    - ``encoding="utf-8", errors="replace"`` — safe on Windows locales.
    - ``TimeoutExpired`` kills + reaps so no zombie git.exe lingers.
    - ``check=True`` raises :class:`GitError` on non-zero exit.
    """
    returncode, out, err = _popen_git(args, cwd=cwd, timeout=timeout, binary=False)
    if check and returncode != 0:
        raise GitError(
            f"git {args[0] if args else '?'} failed "
            f"(exit {returncode}): {err.strip()!r}"
        )
    return subprocess.CompletedProcess(["git", *args], returncode, out, err)


def run_git_soft(
    args: list[str],
    *,
    cwd: Path,
    timeout: float = DEFAULT_GIT_TIMEOUT,
) -> subprocess.CompletedProcess[str]:
    """:func:`run_git` that REPORTS a timeout instead of raising it.

    For callers inside a critical section whose contract is "never raises for an
    expected condition" — the triage sweep, the GC membership read, the main-tree
    reconcile. Those held the canonical triage lock and wrapped only their
    ``commit``, so ``add`` / ``diff --cached`` / ``show`` ran bare on the 15 s
    default. Two things made that worse than slow: :func:`run_git` KILLS the
    process on timeout, which strands ``.git/index.lock``; and an escaping
    ``TimeoutExpired`` aborts ``setup_iterate_worktree`` step 5 *after*
    ``git worktree add`` has already succeeded, orphaning the new worktree.

    A timeout comes back as a failed :class:`subprocess.CompletedProcess` carrying
    :data:`TIMEOUT_RETURNCODE`, so every existing ``returncode != 0`` branch
    reports it as the structured error it always was, with no new control flow.
    Always ``check=False``: raising ``GitError`` would defeat the purpose.
    """
    try:
        return run_git(args, cwd=cwd, check=False, timeout=timeout)
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(
            ["git", *args],
            TIMEOUT_RETURNCODE,
            "",
            _timeout_message(args, timeout),
        )


def run_git_bytes_soft(
    args: list[str],
    *,
    cwd: Path,
    timeout: float = DEFAULT_GIT_TIMEOUT,
) -> subprocess.CompletedProcess[bytes]:
    """:func:`run_git_soft` that hands back the RAW BYTES, decoding nothing.

    For the callers that compare a git blob against a file they read themselves.
    :func:`run_git`'s ``errors="replace"`` is lossy AND non-injective — every byte
    that is not valid UTF-8 collapses to the same ``U+FFFD`` — while the triage
    store reads its files with ``errors="surrogateescape"``. The two sides then
    produce different strings for identical bytes, and no comparison built on
    them can ever match again: the delivered-line GC never fires, the drift plan
    reports an unchanged log as diverged, and the reconcile fold count inflates
    (iterate-2026-08-06-gc-decode-parity).

    Handing back bytes lets each store apply its OWN decode rule (for triage:
    :func:`lib.sweep_text.decode_store_text`), so both sides of the seam agree.
    Fixing it here rather than in any one comparison means every rule layered on
    top — id membership, raw text, a canonical form — inherits the parity.

    Deliberately NOT a change to :func:`run_git`'s own decode: ~133 call sites
    depend on it, and lone surrogates would escape into code that re-encodes
    (JSON writes, subprocess argv) far from this boundary.

    Soft like :func:`run_git_soft`, and for the same reason — a raise here would
    abort ``setup_iterate_worktree`` step 5 *after* ``git worktree add`` already
    succeeded. A timeout comes back as :data:`TIMEOUT_RETURNCODE` with EMPTY
    stdout: ``TimeoutExpired`` may carry partial output, and half a blob compared
    against a whole file is a wrong answer, where ``b""`` routes every caller to
    its existing fail-safe branch. Both streams are bytes, so a caller that
    formats ``stderr`` cannot silently mix types.
    """
    try:
        returncode, out, err = _popen_git(args, cwd=cwd, timeout=timeout, binary=True)
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(
            ["git", *args],
            TIMEOUT_RETURNCODE,
            b"",
            _timeout_message(args, timeout).encode("utf-8"),
        )
    return subprocess.CompletedProcess(["git", *args], returncode, out, err)


# -----------------------------------------------------------------------------
# Worktree / main-repo detection
# -----------------------------------------------------------------------------


def resolve_git_dirs(root: Path) -> tuple[Path, Path]:
    """Return ``(git_dir, git_common_dir)`` as absolute resolved paths."""
    out = run_git(
        ["rev-parse", "--path-format=absolute", "--git-dir", "--git-common-dir"],
        cwd=root,
    ).stdout
    lines = [ln.strip() for ln in out.splitlines() if ln.strip()]
    if len(lines) != 2:
        raise GitError(f"unexpected rev-parse output for git dirs: {out!r}")
    return Path(lines[0]).resolve(), Path(lines[1]).resolve()


def is_worktree(root: Path) -> bool:
    """True when ``root`` is a *linked* worktree, not the main working tree.

    In the main repo ``--git-dir`` and ``--git-common-dir`` are the same path;
    in a linked worktree ``--git-dir`` points at ``.git/worktrees/<name>``.
    """
    git_dir, common = resolve_git_dirs(root)
    return git_dir != common


def main_repo_root(root: Path) -> Path:
    """Absolute path to the MAIN repo working tree (never a linked worktree)."""
    _, common = resolve_git_dirs(root)
    if common.name == ".git":
        return common.parent
    # Bare repo / unusual layout — fall back to this checkout's toplevel.
    return Path(run_git(["rev-parse", "--show-toplevel"], cwd=root).stdout.strip())
