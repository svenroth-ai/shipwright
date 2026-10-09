"""Which repo a commit command is judged on, and the git env its reads need (``check_rtm_coverage``).

``git_commit_target`` says where each commit in the command lands; this module turns
that into one :class:`Scope`: the project root to measure, the ``GIT_DIR`` /
``GIT_WORK_TREE`` its git reads need, the WARNs, and -- for a line committing to
several repos -- every repo below its threshold (measured once each, the chosen
one's measurement cached for the hook).

* ``--git-dir`` (with or without ``--work-tree``): that git dir, the project as the
  work tree.
* ``--work-tree`` WITHOUT ``--git-dir``: the commit lands in the repo git finds from
  the directory reached (cwd / ``-C``), so that repo's git dir comes from ``git -C
  <reached> rev-parse --absolute-git-dir`` and its index is measured.
* A plain ``-C`` that resolves to no Shipwright project while the managed default
  root holds compliance data: a visible WARN (the reached directory is measured,
  and it usually has nothing to measure), never a silent allow.
* Repos are told apart by :func:`repo_key` (resolved, ``normcase``), so ``x`` and
  ``x/../x`` (or ``X`` on Windows) are one repo; on a multi-repo line every repo
  not judged on still has its measurement WARNs carried, prefixed ``[<repo>]``.

Reads project files and runs one ``git rev-parse`` per ``--work-tree`` target.
"""

from __future__ import annotations

import os
import subprocess
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, NamedTuple

import rtm_gate_support as gate
from git_commit_target import CommitTarget, commit_targets, project_at

_GIT_TIMEOUT_S = 5


class Scope(NamedTuple):
    root: str
    env: dict[str, str]
    warnings: list[str]
    below: list[str]  # repos below their threshold (only measured for a multi-repo line)
    measured: tuple[dict[str, Any] | None, list[str]] | None  # cached ``measure(root)``


@contextmanager
def git_env(env: dict[str, str]):
    """``GIT_DIR`` / ``GIT_WORK_TREE`` for the git reads inside the block, then restored."""
    saved = {key: os.environ.get(key) for key in env}
    os.environ.update(env)
    try:
        yield
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def repo_git_dir(directory: Path) -> tuple[str | None, str | None]:
    """``(absolute git dir, None)`` of the repo git finds from *directory*, else ``(None, why)``."""
    try:
        out = subprocess.run(
            ["git", "-C", str(directory), "rev-parse", "--absolute-git-dir"],
            capture_output=True, text=True, timeout=_GIT_TIMEOUT_S, check=False,
            env={**os.environ, "LC_ALL": "C"})
    except (OSError, subprocess.SubprocessError) as exc:
        return None, f"git rev-parse failed ({type(exc).__name__})"
    if out.returncode != 0 or not out.stdout.strip():
        return None, (out.stderr.strip().splitlines() or [f"exit {out.returncode}"])[0][:160]
    return out.stdout.strip(), None


def _has_compliance_data(root: str) -> bool:
    directory = Path(root) / ".shipwright/compliance"
    try:
        return directory.is_dir() and any(directory.iterdir())
    except OSError:
        return False


def _env_for(target: CommitTarget, warnings: list[str]) -> dict[str, str]:
    if target.git_dir is not None:
        tree = target.work_tree or target.project_root
        return {"GIT_DIR": str(target.git_dir), "GIT_WORK_TREE": str(tree)}
    if target.work_tree is None:
        return {}
    git_dir, why = repo_git_dir(target.base)
    if git_dir is None:
        warnings.append(f"the commit's work tree {target.work_tree} belongs to the repo at "
                        f"{target.base}, whose git dir could not be found ({why}); "
                        "its index was not measured")
        return {}
    return {"GIT_DIR": git_dir, "GIT_WORK_TREE": str(target.work_tree)}


def repo_key(path: str | Path) -> str:
    """One spelling per directory: resolved, and case-folded where the filesystem is."""
    return os.path.normcase(str(Path(path).resolve()))


def _no_project_warning(target: CommitTarget, default_root: str) -> str | None:
    root = str(target.project_root)
    if target.found or repo_key(root) == repo_key(default_root) or _has_compliance_data(root):
        return None
    if not _has_compliance_data(default_root):
        return None
    return (f"the commit goes to {root}, where no Shipwright project was found, while "
            f"{default_root} holds compliance data; that repo is not this commit's, so "
            f"{gate.NOT_EVALUATING} for this commit")


def _below(cache: dict[str, Any], root: str, env: dict[str, str]) -> bool:
    if root not in cache:
        with git_env(env):
            cache[root] = gate.measure(root)
    measured = cache[root][0]
    return measured is not None and not gate.meets(measured, gate.read_threshold(root)[0])


def _shell_project(shell_dir: str | None, warnings: list[str],
                   default: Callable[[], str]) -> str | None:
    """The Shipwright project the persisted shell directory belongs to, else ``None``.

    ``None`` falls back to the managed default root; whenever that drops a project the
    shell directory does resolve to, a WARN says so (never a silent switch).
    """
    if shell_dir is None:
        return None
    if not Path(shell_dir).is_dir():
        warnings.append(f"the shell directory {shell_dir} does not exist; the commit is "
                        f"measured on the managed project root {default()}")
        return None
    root, found, note = project_at(Path(shell_dir))
    if note:
        warnings.append(note)
    if found and not Path(shell_dir).resolve().is_relative_to(Path(root).resolve()):
        warnings.append(f"the shell directory {shell_dir} lies outside the project {root} it "
                        f"resolves to (a project below it); the commit lands in the repo "
                        f"around the shell directory, measured on the managed project root "
                        f"{default()}")
        return None
    if found and not _has_compliance_data(str(root)):
        warnings.append(f"the shell directory belongs to the project {root}, which holds no "
                        f"compliance data; measured on the managed project root {default()}")
        return None
    if not found:
        return None  # a fixture, child or non-project directory: the default decides
    env_root = os.environ.get("SHIPWRIGHT_PROJECT_ROOT")  # the documented disambiguator wins
    if env_root and repo_key(env_root) != repo_key(root):
        warnings.append(f"the shell directory belongs to the project {root}, but "
                        f"SHIPWRIGHT_PROJECT_ROOT names {env_root}; measured on the managed "
                        f"project root {default()}")
        return None
    return str(root)


def commit_scope(command: str, cwd: Any, default: Callable[[], str]) -> Scope:
    """The :class:`Scope` for the repo(s) *command* commits to.

    A commit naming no location is judged on the project the payload's shell directory
    belongs to (the hook process may run elsewhere); *default* (the managed project
    root) when that directory is no project, or for a directory that does not exist (WARN). A command committing to several repos is
    judged on the first one below its threshold (else the first), with a WARN
    naming them all; :attr:`Scope.below` lists every repo below its threshold.
    """
    shell_dir = cwd if isinstance(cwd, str) and cwd else None
    cwd = shell_dir or os.getcwd()
    memo: list[str] = []

    def default_root() -> str:
        if not memo:
            memo.append(default())
        return memo[0]

    warnings: list[str] = []
    plain: str | None = None
    roots: dict[str, tuple[str, dict[str, str]]] = {}  # repo_key -> (root, env), in order
    for target in commit_targets(command, cwd):
        if target is not None and not target.project_root.is_dir():
            warnings.append(f"the commit names {target.project_root}, which is not a "
                            f"directory; measured {default_root()} instead")
            target = None
        if target is None:  # a plain commit lands where the SHELL is, not where the hook runs
            if plain is None:  # judged once: its WARNs are not repeated per commit
                plain = _shell_project(shell_dir, warnings, default_root) or default_root()
            roots.setdefault(repo_key(plain), (plain, {}))
            continue
        warnings.extend(filter(None, [target.note, _no_project_warning(target, default_root())]))
        root = str(target.project_root)
        if repo_key(root) not in roots:
            roots[repo_key(root)] = (root, _env_for(target, warnings))
    if not roots:
        return Scope(default_root(), {}, warnings, [], None)
    chosen, env = next(iter(roots.values()))
    if len(roots) == 1:
        return Scope(chosen, env, warnings, [], None)
    cache: dict[str, Any] = {}
    below = [root for root, env in roots.values() if _below(cache, root, env)]
    chosen = below[0] if below else chosen
    names = [root for root, _env in roots.values()]
    warnings.append(f"this command commits to {len(roots)} repos (" + ", ".join(names)
                    + f"); judged on {chosen}, the first below threshold or else the "
                    "first -- commit to each repo separately")
    for root in names:  # the chosen repo's own WARNs travel with its cached measurement
        if root != chosen:
            warnings.extend(f"[{root}] {note}" for note in cache[root][1])
    return Scope(chosen, roots[repo_key(chosen)][1], warnings, below, cache.get(chosen))
