"""Everything the delivery ladder needs from outside the process
(iterate-2026-07-31-f11-delivery-truth).

Split from ``tools/deliver_pr.py`` so the ladder itself reads as the sequence of
decisions it is, and every call that touches ``gh``, ``git`` or another script lives in
one place with one rule: **an unreadable fact is never a false one.** A capability read
that fails answers ``None``, not ``False`` — the difference decides whether this run is
allowed to merge a pull request, so collapsing it would be the same class of defect as
the gate that reported "none derived" while eleven derived files landed on ``main``
(PR #503).

Two hardenings Stage 2 review required, both learned from the adjacent module that had
already learned them (``lib/pr_blockers._gh_json``):

* **Every call is timed out.** ``timeout_seconds`` bounds the *polling clock*, and that
  clock is only consulted after a fetch returns — so an untimed ``gh`` blocking on a TLS
  handshake or a misbehaving credential helper escapes every stated bound and the run
  neither delivers nor fails.
* **Nothing here raises for an ordinary failure.** ``gh`` missing from PATH is an
  ``OSError``, not a ``RuntimeError``; a zero exit with empty stdout is a
  ``JSONDecodeError``. Both used to escape the ladder's handlers and surface as a
  traceback instead of the documented exit 5.

:class:`Host` bundles the six seams as one object. They used to be six loose callables
with independent defaults, and ``read_capability``'s default closed over the
module-level ``gh_json`` rather than the injected one — so a caller who faked
``gh_json`` alone would have fired real ``gh api`` calls at the operator's live GitHub
while believing the host was faked. The bundle makes that unrepresentable.
"""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass, field
from functools import partial
from pathlib import Path

#: ``shared/scripts`` — sibling tools are invoked by absolute path so the ladder works
#: from a worktree whose cwd is not the main repo root.
SCRIPTS_ROOT = Path(__file__).resolve().parents[1]

#: A host read must not outlive the operator's patience. Matches ``lib/pr_blockers``.
GH_TIMEOUT_SECONDS = 60.0
#: The verifier and ``ensure_current`` do real work (a test suite, a merge + regenerate),
#: so they get their own, much larger, but still finite budget.
CHILD_TIMEOUT_SECONDS = 1800.0

#: Everything an ordinary host failure can raise. ``RuntimeError`` is ours;
#: ``OSError`` covers a missing binary; ``subprocess.SubprocessError`` covers
#: ``TimeoutExpired``; ``ValueError`` covers a JSON parse.
HOST_ERRORS = (RuntimeError, OSError, subprocess.SubprocessError, ValueError)


def _run(argv: list[str], *, cwd: Path | None = None,
         timeout: float = GH_TIMEOUT_SECONDS) -> subprocess.CompletedProcess:
    """One child process, always timed out. Raises nothing an ordinary failure needs:
    a timeout or a missing binary becomes a non-zero result with the reason on stderr."""
    try:
        return subprocess.run(
            argv, capture_output=True, text=True, encoding="utf-8",
            cwd=str(cwd) if cwd else None, timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(
            argv, 124, "", f"timed out after {timeout:g}s: {argv[0]}")
    except OSError as exc:
        return subprocess.CompletedProcess(
            argv, 127, "", f"could not run {argv[0]!r}: {type(exc).__name__}: {exc}")


def gh(args: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess:
    """One ``gh`` call. ``cwd`` is passed explicitly because ``gh`` has no ``-C`` analog
    and acts on the cwd's repository — the reason F11 ``cd``s into the worktree before
    calling it at all. The ladder additionally passes ``--repo`` on every call, so the
    repository is never inferred from a remote."""
    return _run(["gh", *args], cwd=cwd)


def gh_json(args: list[str], *, cwd: Path | None = None):
    """A ``gh`` call whose stdout is JSON, or ``None`` when it cannot be read.

    A zero exit with blank stdout is *not* an empty answer — it is an unreadable one,
    and the caller's whole permission model turns on telling those apart.
    """
    proc = gh(args, cwd=cwd)
    if proc.returncode != 0 or not (proc.stdout or "").strip():
        return None
    try:
        return json.loads(proc.stdout)
    except (ValueError, TypeError):
        return None


@dataclass(frozen=True)
class Host:
    """The six things the ladder needs from outside, as one substitutable object.

    ``capability`` is bound to *this* Host's ``gh_json`` by :meth:`default`, so faking
    one member can never leave another talking to the real GitHub.
    """

    gh: object = gh
    gh_json: object = gh_json
    capability: object = None
    verify: object = None
    refresh: object = None
    head_sha: object = None
    #: Extra argv appended to every gh call — ``["--repo", "owner/name"]`` in practice.
    repo_args: tuple[str, ...] = field(default=())

    @classmethod
    def default(cls, *, repo: str = "") -> Host:
        """The production host, wired so no member can be half-faked.

        ``capability`` is BOUND to this bundle's own ``gh_json`` rather than merely
        aliasing the module function — otherwise the binding depends on every call site
        remembering to pass ``reader=host.gh_json``, and forgetting once means real
        ``gh api`` calls against the operator's live GitHub while the host looks faked
        (external code review).
        """
        reader = gh_json
        return cls(
            gh=gh, gh_json=reader,
            capability=partial(read_capability, reader=reader),
            verify=reverify, refresh=refresh_branch, head_sha=head_sha,
            repo_args=("--repo", repo) if repo else (),
        )

    def call(self, args: list[str], *, cwd: Path | None = None):
        """A ``gh`` call with the repository pinned."""
        return self.gh([*args, *self.repo_args], cwd=cwd)

    def call_json(self, args: list[str], *, cwd: Path | None = None):
        """A JSON ``gh`` call with the repository pinned."""
        return self.gh_json([*args, *self.repo_args], cwd=cwd)


def read_capability(repo: str, base: str, *, cwd: Path | None = None,
                    reader=gh_json) -> dict:
    """The two facts that decide whether arming can EVER succeed.

    Both are readable without admin rights (verified on this repo):
    ``allow_auto_merge`` is the repository-wide switch, and ``protected`` on the branch
    object covers rulesets **and** classic branch protection.

    The rulesets endpoint (``/rules/branches/{branch}``) was rejected for this job: it
    reports rulesets only, so a classic-protection repo answers ``[]`` while arming works
    perfectly — using it as the discriminator would have silently demoted a whole class
    of repositories to self-merge (external review, HIGH).

    ``None`` for either means "could not read", which keeps the arm outcome transient and
    so denies permission to merge here.
    """
    repo_obj = reader(["api", f"repos/{repo}", "--jq",
                       "{allow_auto_merge: .allow_auto_merge}"], cwd=cwd)
    branch_obj = reader(["api", f"repos/{repo}/branches/{base}", "--jq",
                         "{protected: .protected}"], cwd=cwd)
    return {
        "allow_auto_merge": (repo_obj or {}).get("allow_auto_merge"),
        "base_protected": (branch_obj or {}).get("protected"),
    }


def reverify(project_root: Path, run_id: str, commit: str, *, run=_run,
             timeout: float = CHILD_TIMEOUT_SECONDS) -> bool:
    """Re-run the finalization verifier on ``commit``.

    Called after a mid-wait refresh made a new commit. F11 runs the verifier *before*
    the watch, so today the commit that merges is always the commit that was verified; a
    refresh during the wait would break that invariant for the first time. Red here
    STOPS delivery rather than merging something unverified.
    """
    proc = run(
        [sys.executable, str(SCRIPTS_ROOT / "tools" / "verify_iterate_finalization.py"),
         "--run-id", run_id, "--project-root", str(project_root), "--commit", commit],
        timeout=timeout,
    )
    if proc.returncode != 0:
        print(proc.stdout or "", file=sys.stderr)
        print(proc.stderr or "", file=sys.stderr)
    return proc.returncode == 0


def refresh_branch(project_root: Path, run_id: str, branch: str, *, run=_run,
                   timeout: float = CHILD_TIMEOUT_SECONDS) -> dict:
    """``ensure_current`` then push. Returns ``{ok, pushed, guard?, error?}``.

    Deliberately the SAME guard F11 runs before arming: only the merge path runs the
    regenerate-at-merge resolver, so a rebase — or the host's own server-side 3-way
    merge — would ship stale derived snapshots (Group-E). A branch already current is a
    clean no-op and nothing is pushed.
    """
    head_before = head_sha(project_root, run=run)
    proc = run(
        [sys.executable, str(SCRIPTS_ROOT / "tools" / "ensure_current.py"),
         "--project-root", str(project_root), "--run-id", run_id,
         "--reason", f"delivery refresh before self-merge: {run_id}"],
        timeout=timeout,
    )
    if proc.returncode != 0:
        return {"ok": False, "pushed": False,
                "error": (proc.stderr or proc.stdout or "ensure_current failed").strip()[:400]}
    try:
        guard = json.loads(proc.stdout)
    except (ValueError, TypeError):
        guard = {"action": "unparseable", "integrated": False}
    if not guard.get("integrated"):
        if guard.get("action") == "unparseable" and head_sha(project_root, run=run) != head_before:
            # The guard's own answer was unreadable AND HEAD moved, so a commit probably
            # WAS made and was never pushed. Saying "nothing integrated" here surfaces
            # later as "something else pushed to this branch" — naming a cause that did
            # not happen (Stage 3). Name the real one.
            return {"ok": False, "pushed": False, "guard": guard,
                    "error": "the refresh guard's output could not be read and HEAD moved — "
                             "an integrate commit may exist locally and was never pushed; "
                             "inspect the branch by hand"}
        return {"ok": True, "pushed": False, "guard": guard}
    pushed = run(["git", "-C", str(project_root), "push", "origin", branch],
                 timeout=timeout)
    if pushed.returncode != 0:
        return {"ok": False, "pushed": False, "guard": guard,
                "error": (pushed.stderr or "push failed").strip()[:400]}
    return {"ok": True, "pushed": True, "guard": guard}


def head_sha(project_root: Path, *, run=_run) -> str:
    """HEAD of ``project_root``. ``git -C`` always, never a bare ``git``: a Bash cwd
    silently resets between calls and a bare command would read the MAIN tree
    (memory ``feedback_git_dash_C_in_worktree``)."""
    proc = run(["git", "-C", str(project_root), "rev-parse", "HEAD"])
    return proc.stdout.strip() if proc.returncode == 0 else ""


__all__ = [
    "CHILD_TIMEOUT_SECONDS",
    "GH_TIMEOUT_SECONDS",
    "HOST_ERRORS",
    "Host",
    "SCRIPTS_ROOT",
    "gh",
    "gh_json",
    "head_sha",
    "read_capability",
    "refresh_branch",
    "reverify",
]
