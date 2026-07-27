"""Git-derived evidence for the requirement-impact touch check.

**Why this exists as its own module rather than a helper on the CLI.** The touch
check asks "was a requirements file actually changed?", and the answer must not
come from the caller. An earlier draft let the caller pass a path list; external
review pointed out that a declaration able to name its own evidence checks
nothing — a prompt or an operator could satisfy the rule by handing in a
plausible ``spec.md`` path nobody touched. Git is therefore the only authority,
and both consumers (the recorder and the section-attribution checker) share this
one derivation so they cannot disagree about what "changed" means.

**Outcomes are classified, never lumped.** A missing git binary is not the same
failure as a bad ref, and treating them alike would let a typo in ``--base-ref``
quietly degrade into "check skipped":

===================  ==========================================================
``source``           meaning
===================  ==========================================================
``git``              git answered; ``changed`` is authoritative
``skipped``          no git binary / not a repository — caller may proceed,
                     but must record that the check did not run
``error``            bad ref, unreadable range, unexpected git failure — the
                     caller must REJECT rather than proceed
===================  ==========================================================

Origin: trg-e9e5188e (FR-01.04, FR-01.05).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from lib.git_name_status import NameStatusError, parse as parse_name_status, rebase
from lib.requirement_impact import to_repo_relative_posix

#: git answered and the result is authoritative.
SOURCE_GIT = "git"
#: Evidence was unobtainable (no binary, not a repo). Fail-open — but recorded.
SOURCE_SKIPPED = "skipped"
#: git was available but the request was bad. Fail-closed.
SOURCE_ERROR = "error"

_TIMEOUT_SECONDS = 30


class _GitUnavailable(Exception):
    """The git binary or the working directory is absent — evidence unobtainable."""


class _GitBroke(Exception):
    """git exists but the invocation failed unexpectedly (timeout, permissions).

    Deliberately NOT the same as :class:`_GitUnavailable`: collapsing the two
    would let a 30-second timeout or a permission error silently degrade the
    touch check to "skipped", which is fail-open on *unknown* — exactly what the
    outcome table above disclaims.
    """


def _run(project_root, args: list[str]) -> subprocess.CompletedProcess:
    """Run one git command with an argument array (never a shell string).

    Raises :class:`_GitUnavailable` when git itself is missing and
    :class:`_GitBroke` for any other execution failure. A non-zero *exit code*
    is returned intact — that is a normal answer the caller interprets.
    """
    try:
        return subprocess.run(
            ["git", "-C", str(project_root), *args],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=_TIMEOUT_SECONDS,
        )
    except (FileNotFoundError, NotADirectoryError) as exc:
        raise _GitUnavailable(str(exc)) from exc
    except (OSError, subprocess.SubprocessError) as exc:
        raise _GitBroke(f"{type(exc).__name__}: {exc}") from exc


def _is_repo(project_root) -> bool:
    """True iff this really is a usable repository.

    ``rev-parse --git-dir`` also exits non-zero for conditions that are NOT
    "no repository here" — most commonly `detected dubious ownership`, the
    default in bind-mounted containers and on Windows trees owned by
    Administrators. Reporting those as "not a git repository" turned the whole
    mechanism green-and-inert in exactly those environments, so they raise.
    """
    result = _run(project_root, ["rev-parse", "--git-dir"])
    if result.returncode == 0:
        return True
    stderr = (result.stderr or "").lower()
    if "not a git repository" in stderr or not stderr.strip():
        return False
    raise _GitBroke(f"git rev-parse failed: {(result.stderr or '').strip()}")


def repo_toplevel(project_root) -> Path | None:
    """The repository root, or ``None`` if it cannot be determined.

    Needed because ``git diff`` reports paths relative to the REPOSITORY root
    while everything else here is relative to the project root. When a Shipwright
    project sits in a subdirectory of a larger repo, comparing the two directly
    matched nothing: every ``--impact modify`` was refused and every changed file
    read as unattributed.
    """
    result = _run(project_root, ["rev-parse", "--show-toplevel"])
    if result.returncode != 0:
        return None
    text = result.stdout.strip()
    return Path(text) if text else None


def _has_commits(project_root) -> bool:
    """False for an initialized repo with no commits yet (unborn HEAD).

    A greenfield project runs its design phase before anything is committed;
    without this probe ``git diff HEAD`` fails, every round's declaration is
    rejected as ``evidence_unusable``, and the phase can never be finished.
    """
    return _run(project_root, ["rev-parse", "--verify", "--quiet", "HEAD"]).returncode == 0


def _resolve(project_root, ref: str) -> str | None:
    """The commit SHA a ref names, or ``None`` if it names nothing."""
    result = _run(project_root, ["rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"])
    return result.stdout.strip() if result.returncode == 0 else None


def _result(source: str, detail: str = "", buckets=None, extra_changed=(),
            base_sha=None, head_sha=None) -> dict:
    buckets = buckets or {"added_modified": [], "deleted": [], "renamed": []}
    changed = [
        *buckets["added_modified"], *buckets["deleted"], *buckets["renamed"],
        *extra_changed,
    ]
    return {
        "source": source,
        "detail": detail,
        # ``None`` (not ``[]``) when unauthoritative: the touch predicate treats
        # "git could not tell us" and "git said nothing changed" differently, and
        # collapsing them here would silently turn a skip into a pass.
        "changed": changed if source == SOURCE_GIT else None,
        "added_modified": buckets["added_modified"],
        "deleted": buckets["deleted"],
        "renamed": buckets["renamed"],
        # The RESOLVED endpoints, so a later reader can audit which range was
        # actually inspected. A symbolic "HEAD~1..HEAD" alone is unauditable —
        # it means something different from every commit.
        "base_sha": base_sha,
        "head_sha": head_sha,
    }


def changed_paths(project_root, *, base_ref=None, head_ref=None,
                  worktree: bool = False, single_commit: bool = False) -> dict:
    """Derive the changed-path set for a declaration's scope.

    Two modes, matching the two call sites:

    * ``base_ref``/``head_ref`` — a committed range, for a **build section**.
      A range whose endpoints resolve to the SAME commit is REJECTED: an empty
      diff would otherwise let any declaration through, which hands the caller
      back exactly the power that deriving evidence from git is meant to remove.
    * ``worktree=True`` — uncommitted work against ``HEAD``, for a **design
      round**, which edits mockups and specs without committing per round.
      Untracked files are included; a newly created spec counts as a touch.
      **Scope caveat:** this is everything uncommitted, not this round's changes
      alone — see ``review-loop.md``.
    """
    root = Path(project_root)
    if not root.is_dir():
        return _result(SOURCE_SKIPPED, f"project root {root} does not exist")
    try:
        if not _is_repo(root):
            return _result(SOURCE_SKIPPED, "not a git repository")
        prefix = _project_prefix(root)
        return (_worktree_paths(root, prefix) if worktree
                else _range_paths(root, base_ref, head_ref, prefix,
                                  single_commit=single_commit))
    except _GitUnavailable as exc:
        return _result(SOURCE_SKIPPED, f"git unavailable: {exc}")
    except _GitBroke as exc:
        return _result(SOURCE_ERROR, f"git failed unexpectedly: {exc}")
    except NameStatusError as exc:
        return _result(SOURCE_ERROR, f"unreadable git diff output: {exc}")


def _project_prefix(root: Path) -> str:
    """The project root's path RELATIVE to the repository root, or ``""``.

    ``""`` when the project *is* the repo root (the common case), so the rebase
    is a no-op there.
    """
    top = repo_toplevel(root)
    if top is None:
        return ""
    try:
        rel = root.resolve().relative_to(top.resolve()).as_posix()
    except (ValueError, OSError):
        return ""
    return "" if rel == "." else rel


def _worktree_paths(root: Path, prefix: str = "") -> dict:
    if not _has_commits(root):
        # Unborn HEAD: nothing is committed yet, so everything present counts as
        # changed. Diffing against HEAD here would fail and make a greenfield
        # design phase impossible to finish.
        listed = _run(root, ["ls-files", "--cached", "--others",
                             "--exclude-standard", "-z"])
        if listed.returncode != 0:
            raise _GitBroke(f"git ls-files failed: {_stderr(listed)}")
        paths = _listed_paths(listed.stdout, prefix)
        return _result(SOURCE_GIT, "unborn HEAD — all present files",
                       {"added_modified": paths, "deleted": [], "renamed": []})

    diff = _run(root, ["diff", "--name-status", "-z", "HEAD", "--"])
    if diff.returncode != 0:
        raise _GitBroke(f"git diff against HEAD failed: {_stderr(diff)}")
    untracked = _run(root, ["ls-files", "--others", "--exclude-standard", "-z"])
    if untracked.returncode != 0:
        # Swallowing this would hide a newly CREATED spec.md from the touch
        # check while still reporting source="git" — a false verified result.
        raise _GitBroke(f"git ls-files failed: {_stderr(untracked)}")
    extra = _listed_paths(untracked.stdout, prefix)
    head = _resolve(root, "HEAD")
    return _result(SOURCE_GIT, "worktree vs HEAD",
                   parse_name_status(diff.stdout, prefix), extra,
                   base_sha=head, head_sha=None)


def _listed_paths(stdout: str, prefix: str) -> list[str]:
    """NUL-separated ``ls-files`` output, rebased onto the project root."""
    return [
        path for path in (
            rebase(to_repo_relative_posix(raw), prefix)
            for raw in stdout.split("\0") if raw
        ) if path
    ]


def _range_paths(root: Path, base_ref, head_ref, prefix: str = "",
                 single_commit: bool = False) -> dict:
    if not base_ref or not head_ref:
        return _result(SOURCE_ERROR,
                       "either --worktree or both --base-ref and --head-ref "
                       "are required — the comparison boundary must be explicit")

    base_sha, head_sha = _resolve(root, base_ref), _resolve(root, head_ref)
    for ref, sha in ((base_ref, base_sha), (head_ref, head_sha)):
        if sha is None:
            return _result(SOURCE_ERROR, f"unknown git ref: {ref!r}")
    if base_sha == head_sha:
        return _result(
            SOURCE_ERROR,
            f"--base-ref {base_ref!r} and --head-ref {head_ref!r} both resolve to "
            f"{base_sha[:8]} — an empty range would let any declaration pass",
        )
    if single_commit and not _is_parent(root, base_sha, head_sha):
        # A section is answerable for ONE commit. A wider range containing some
        # unrelated requirement edit would otherwise satisfy a behaviour-
        # affecting declaration the section's own work never earned.
        return _result(
            SOURCE_ERROR,
            f"{base_ref}..{head_ref} spans more than one commit — a build "
            "section is judged against its own commit, so --base-ref must be "
            "--head-ref's parent (normally HEAD^ and HEAD)",
        )

    diff = _run(root, ["diff", "--name-status", "-z", base_ref, head_ref, "--"])
    if diff.returncode != 0:
        raise _GitBroke(f"git diff {base_ref}..{head_ref} failed: {_stderr(diff)}")
    return _result(SOURCE_GIT, f"{base_ref}..{head_ref}",
                   parse_name_status(diff.stdout, prefix),
                   base_sha=base_sha, head_sha=head_sha)


def _is_parent(root: Path, base_sha: str, head_sha: str) -> bool:
    """True iff ``base_sha`` is a parent of ``head_sha``."""
    result = _run(root, ["rev-parse", f"{head_sha}^@"])
    if result.returncode != 0:
        return False
    return base_sha in result.stdout.split()


def _stderr(result) -> str:
    return (result.stderr or "").strip() or f"exit {result.returncode}"
