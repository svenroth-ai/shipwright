"""resolve_target — the input seam for the grader.

``resolve_target(raw) -> ResolvedTarget`` turns a user-supplied target into a
validated local path plus the git facts the projector needs. G1 supports a
**local path only**; a URL is recognised and explicitly deferred (G4) rather
than silently mis-handled — the seam exists so URL clone-and-grade slots in
behind it with zero projector rework.

Security (untrusted input): the input is validated, the path is fully resolved
(``Path.resolve``) so ``..`` traversal cannot escape, and we never *follow* a
symlink target that points outside the resolved repo root during traversal
(that guard lives in ``repo_context``; here we only resolve the root the user
explicitly named).
"""

from __future__ import annotations

import re
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Iterator

from git_exec import run_git
from normalize_input import strip_surrounding_quotes

# A conservative URL/scheme sniff. Anything matching is treated as a *remote*
# input handled by ``open_target`` (clone-and-grade), never a local path.
_URL_RE = re.compile(r"^(?:https?|git|ssh|git\+ssh)://|^git@[\w.-]+:", re.IGNORECASE)
# GitHub ``owner/repo`` shorthand — remote ONLY when it isn't an existing local path.
_SHORTHAND_RE = re.compile(r"^[A-Za-z0-9][\w.-]*/[A-Za-z0-9][\w.-]*?(?:\.git)?$")


class TargetError(ValueError):
    """The target could not be resolved to a gradeable local repository."""


@dataclass(frozen=True)
class ResolvedTarget:
    """A validated local target plus the git facts the projector consumes."""

    local_path: Path
    is_git: bool
    is_bare: bool
    is_shallow: bool
    has_remote: bool
    input_kind: str  # "local_path" (resolved in place) | "url" (cloned remote)
    note: str = ""


def _run_git(args: list[str], cwd: Path) -> tuple[int, str]:
    """Run a read-only, hardened git command. Returns (rc, stripped-stdout)."""
    rc, out = run_git(args, cwd, timeout=15)
    return rc, out.strip()


def _git_facts(path: Path) -> tuple[bool, bool, bool, bool]:
    """Return (is_git, is_bare, is_shallow, has_remote) for ``path``."""
    rc, inside = _run_git(["rev-parse", "--is-inside-work-tree"], path)
    rc_bare, is_bare_out = _run_git(["rev-parse", "--is-bare-repository"], path)
    is_bare = is_bare_out == "true"
    # A worktree ("true") or a bare repo both count as git; a non-repo returns rc!=0.
    is_git = (rc == 0 and inside == "true") or is_bare
    if not is_git:
        return False, False, False, False
    # Shallow: the git-dir carries a `shallow` file.
    _, gitdir = _run_git(["rev-parse", "--git-dir"], path)
    is_shallow = False
    if gitdir:
        gd = Path(gitdir)
        if not gd.is_absolute():
            gd = (path / gd)
        is_shallow = (gd / "shallow").exists()
    _, remotes = _run_git(["remote"], path)
    has_remote = bool(remotes.strip())
    return is_git, is_bare, is_shallow, has_remote


def resolve_target(raw: str) -> ResolvedTarget:
    """Resolve ``raw`` to a validated local git repository.

    Raises :class:`TargetError` for a URL (deferred to G4), a missing path, a
    non-directory, or a directory that is not a git repository.
    """
    if not isinstance(raw, str) or not raw.strip():
        raise TargetError("empty target")
    raw = raw.strip()

    if _URL_RE.match(raw):
        raise TargetError(
            "URL targets are cloned via open_target(); resolve_target() takes a "
            "local path"
        )

    path = Path(raw).expanduser()
    try:
        resolved = path.resolve()
    except (OSError, RuntimeError) as exc:  # RuntimeError: symlink loop
        raise TargetError(f"cannot resolve path: {raw}") from exc

    if not resolved.exists():
        raise TargetError(f"path does not exist: {resolved}")
    if not resolved.is_dir():
        raise TargetError(f"target is not a directory: {resolved}")

    is_git, is_bare, is_shallow, has_remote = _git_facts(resolved)
    if not is_git:
        raise TargetError(f"not a git repository: {resolved}")

    return ResolvedTarget(
        local_path=resolved,
        is_git=True,
        is_bare=is_bare,
        is_shallow=is_shallow,
        has_remote=has_remote,
        input_kind="local_path",
        note="bare repository" if is_bare else "",
    )


def is_remote_target(raw: str) -> bool:
    """True when ``raw`` should be cloned (a URL / SCP remote / GitHub shorthand).

    A bare ``owner/repo`` is remote ONLY when no local path of that name exists —
    an existing local directory always wins, so a relative path is never
    mis-cloned.
    """
    if not isinstance(raw, str):
        return False
    raw = raw.strip()
    if not raw:
        return False
    if _URL_RE.match(raw):
        return True
    if _SHORTHAND_RE.match(raw) and not Path(raw).expanduser().exists():
        return True
    return False


@contextmanager
def open_target(raw: str, *, allow_clone: bool = True) -> Iterator[ResolvedTarget]:
    """Yield a :class:`ResolvedTarget` for a local path OR a cloned remote.

    This is the input seam the grader drives. A local path resolves in place
    (no cleanup). A remote (URL / ``owner/repo``) is shallow-cloned into a
    ``tempfile.TemporaryDirectory`` that is **purged on exit — even on a crash**
    (the ``with`` block runs its cleanup during exception unwinding). Set
    ``allow_clone=False`` to forbid network cloning (a remote input then errors).

    As the boundary, this is also where a user-supplied target is *sanitised*:
    a balanced pair of surrounding quotes (a copy/paste artifact — Explorer
    "Copy as path", a quoted README URL) is stripped before classification so a
    stray quote never turns a valid target into a hard error. Downstream
    validation and escaping are unchanged.
    """
    raw = strip_surrounding_quotes(raw)
    if is_remote_target(raw):
        if not allow_clone:
            raise TargetError(
                f"remote target requires cloning, which is disabled: {raw}")
        # Lazy import: a local-path run never pays the clone module's cost.
        from clone import clone_repo
        with tempfile.TemporaryDirectory(prefix="shipwright-grade-") as tmp:
            dest = Path(tmp) / "repo"
            clone_repo(raw, dest)
            # Tag the resolved target as a REMOTE input (populate the reserved
            # input_kind="url"). The grader keys its network default on this: a
            # cloned remote's identity was already sent to GitHub to fetch it, so
            # network enrichment defaults ON for it, while a local path (below)
            # stays "local_path" → local-only by default (privacy-first).
            yield replace(resolve_target(str(dest)), input_kind="url", note="cloned remote")
        return
    yield resolve_target(raw)
