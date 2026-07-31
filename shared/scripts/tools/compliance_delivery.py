#!/usr/bin/env python3
"""Putting the recomputed documents somewhere: the git primitives, and the PR path.

Fourth module of the compliance-evidence refresh
(iterate-2026-07-31-derived-docs-at-release). :mod:`tools.refresh_compliance_docs`
keeps the CLI and the one-line release delivery; this holds the shared git/index
**on-demand pull-request protocol**, which is its own
subject rather than its own line count: it has its own preconditions (a clean
checkout of an up-to-date default branch), its own five failure states
(``branch_failed``, ``restore_failed``, ``stage_failed``, ``base_moved``,
``base_unverifiable``, ``push_failed``), and its own cleanup obligation (the
operator gets their branch back, and is told when they did not).

Nothing here holds a credential. The pull request is opened with the operator's
own ``gh`` login; there is no bot, no deploy key, no ruleset bypass and nothing
that runs in CI.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

# UNCONDITIONAL — see the note in `tools/compliance_refresh_produce.py` (ADR-045).
_SCRIPTS_DIR = Path(__file__).resolve().parent.parent  # shared/scripts
sys.path.insert(0, str(_SCRIPTS_DIR))

from lib.compliance_refresh import (  # noqa: E402
    REFRESH_SET,
    branch_name,
    docs_commit_message,
    pr_body,
)
from tools.compliance_git import (  # noqa: E402
    restore_to_head,
    staged_difference,
    write_back,
)
from tools.compliance_refresh_produce import git  # noqa: E402

__all__ = ["deliver_pr", "preflight_pr"]


def _default_branch(root: Path) -> str:
    ref = (git(root, "symbolic-ref", "--short",
               "refs/remotes/origin/HEAD").stdout or "").strip()
    return ref.split("/", 1)[1] if ref.startswith("origin/") else "main"


def _remote_tip(root: Path, branch: str) -> str | None:
    """The remote branch's SHA, or ``None`` when git could not answer.

    ``None`` is NOT the empty string. AC-8b's re-check read a failed ``ls-remote``
    — offline, a credential prompt, transient DNS — as "the base did not move" and
    pushed anyway, shipping the knowingly-stale refresh the check exists to prevent
    with ``status: pr_opened`` and exit 0 (Stage-2 code review, medium). An
    unanswerable question is not a reassuring answer.
    """
    done = git(root, "ls-remote", "origin", f"refs/heads/{branch}")
    if done.returncode != 0:
        return None
    out = (done.stdout or "").strip()
    return out.split()[0] if out else ""


def _gh_pr_create(root: Path, base: str, head: str, title: str, body: str) -> tuple[int, str]:
    """Open the pull request under the operator's own ``gh`` login.

    Its own function so a test can substitute the ONE call that reaches GitHub.
    Patching ``subprocess.run`` wholesale would also silence every ``git`` call in
    this module — which is how a delivery test can pass while proving nothing.
    """
    done = subprocess.run(
        ["gh", "pr", "create", "--base", base, "--head", head,
         "--title", title, "--body", body],
        cwd=str(root), capture_output=True, text=True, encoding="utf-8", check=False,
    )
    return done.returncode, (done.stdout or done.stderr or "").strip()[-400:]


def deliver_pr(root: Path, result: dict, payload: dict[str, bytes]) -> dict:
    """Take-the-set on a fresh branch, then an ordinary pull request.

    "Nothing else can ride along" holds by CONSTRUCTION rather than by a check
    that can fail open: the worktree is restored to the base, the captured bytes
    are written back, and the commit carries an explicit pathspec. Both halves
    need that pathspec — ``git add`` is additive, and only ``git commit --
    <paths>`` commits those and nothing else whatever the index holds.

    The branch the operator started on is always restored, including on every
    failure path. A refusal after the commit leaves the work on the local refresh
    branch and says so, rather than discarding it.
    """
    base_sha = result["base"]
    branch = branch_name(base_sha)
    default = result["default_branch"]
    # The branch NAME on a normal checkout, the SHA on a detached HEAD. A detached
    # checkout at origin/<default> passes the preflight, and `--abbrev-ref` reports
    # it as the literal "HEAD" — which the old restore excluded, so that operator
    # was silently left on the refresh branch (Stage-2 code review, low).
    started_on = (git(root, "rev-parse", "--abbrev-ref", "HEAD").stdout or "").strip()
    if started_on in ("", "HEAD"):
        started_on = (git(root, "rev-parse", "HEAD").stdout or "").strip()
    if git(root, "switch", "-c", branch).returncode != 0:
        # Outside the `try`, so its cleanup is explicit: the producer already wrote
        # AND STAGED its output (`regenerate_tracked_snapshots` stages what it
        # writes), and leaving that in a checkout the operator believes is clean is
        # how the NEXT run fails preflight on changes they never made.
        result["status"] = "branch_failed"
        result["detail"] = (
            f"could not create {branch} — it already exists, most likely from an "
            "earlier run at this same base that did not push. Delete it or re-run "
            "once the default branch has moved."
        )
        result["restored"], result["unresolved"] = restore_to_head(root)
        return result
    try:
        if git(root, "checkout", "HEAD", "--", ".").returncode != 0:
            result["status"] = "restore_failed"
            result["detail"] = "could not restore the worktree to the base commit"
            result["restored"], result["unresolved"] = restore_to_head(root)
            return result
        write_back(root, payload)
        staged = staged_difference(root, sorted(REFRESH_SET))
        if staged is None:
            result["status"] = "stage_failed"
            result["detail"] = "git could not stage the evidence paths"
            result["restored"], result["unresolved"] = restore_to_head(root)
            return result
        result["staged"] = staged
        if not staged:
            result["status"] = "noop"
            result["detail"] = "the committed documents already match the tree"
            return result
        commit = git(root, "commit", "-m",
                     docs_commit_message(base_sha, result.get("run_id") or "compliance-docs-refresh"),
                     "--", *sorted(REFRESH_SET))
        if commit.returncode != 0:
            result["status"] = "commit_failed"
            result["detail"] = (commit.stderr or "")[-400:]
            # Before the `finally` switches back: the producer's output is written
            # AND STAGED, and the switch would carry it onto the operator's branch,
            # where the next run refuses preflight over changes they never made
            # (Stage-3 doubt S1). Three of six failure paths did exactly that.
            result["restored"], result["unresolved"] = restore_to_head(root)
            return result
        # Recomputing is cheap; shipping a knowingly-stale refresh is pointless.
        tip = _remote_tip(root, default)
        if tip is None:
            result["status"] = "base_unverifiable"
            result["detail"] = (
                f"could not read origin/{default} to confirm the base still holds, "
                f"so this refresh is not pushed; branch {branch} holds the work "
                "locally. An unanswerable question is not a green light."
            )
            return result
        if tip and tip != base_sha:
            result["status"] = "base_moved"
            result["detail"] = (
                f"origin/{default} advanced past {base_sha[:12]} during the "
                f"regeneration; branch {branch} holds the work locally — re-run "
                "from a fresh base"
            )
            return result
        if git(root, "push", "-u", "origin", branch).returncode != 0:
            result["status"] = "push_failed"
            result["detail"] = f"branch {branch} holds the work locally"
            return result
        code, output = _gh_pr_create(
            root, default, branch,
            f"chore(compliance): refresh evidence documents ({base_sha[:12]})",
            pr_body(base_sha, staged, result["ci_security"]["note"]),
        )
        result["status"] = "pr_opened" if code == 0 else "pr_failed"
        result["pr"] = output
        return result
    finally:
        # Checked, not assumed: `git switch` returns a CompletedProcess nobody was
        # reading, so a refused switch left the operator standing on the refresh
        # branch in silence. Where they ended up is now part of the record either
        # way (Stage-2 code review, low).
        if started_on:
            back = git(root, "switch", started_on)
            result["returned_to" if back.returncode == 0 else "left_on"] = (
                started_on if back.returncode == 0 else branch)


def preflight_pr(root: Path, result: dict) -> str | None:
    """Why ``--pr`` may not proceed, or ``None``. Refuses rather than repairs.

    A refresh computed on top of unrelated local work is not a refresh of the
    default branch, and no amount of pathspec discipline downstream fixes that —
    the regenerated CONTENT would already describe the wrong tree.
    """
    default = _default_branch(root)
    result["default_branch"] = default
    # A committer identity is a PRECONDITION, not something to discover at commit
    # time. Without it `git commit` fails with "unable to auto-detect email
    # address" — after the branch exists and the work is done, so the operator
    # gets a `commit_failed` and a branch to clean up instead of one sentence up
    # front. Measured: this is exactly how CI failed while every local run passed,
    # because a developer's machine has an identity and a fresh runner does not.
    if git(root, "var", "GIT_COMMITTER_IDENT").returncode != 0:
        return ("git has no committer identity here, so the refresh commit would "
                "fail — set user.name and user.email (this commit is yours, not a "
                "bot's, which is why the tool does not supply one)")
    if git(root, "fetch", "origin", default).returncode != 0:
        return f"could not fetch origin/{default}"
    dirty = (git(root, "status", "--porcelain",
                 "--untracked-files=no").stdout or "").strip()
    if dirty:
        return ("the working tree has uncommitted changes — run this on a clean "
                "checkout so the refresh cannot pick anything else up")
    head = (git(root, "rev-parse", "HEAD").stdout or "").strip()
    remote = (git(root, "rev-parse", f"origin/{default}").stdout or "").strip()
    if not head or not remote:
        # Both empty compare EQUAL, so an unreadable repository used to PASS the
        # preflight — caught one step later by the `safe_commit` refusal, but the
        # message it produced named a comparison that never happened (Stage-2 code
        # review, low).
        return (f"could not resolve {'HEAD' if not head else ''}"
                f"{' and ' if not head and not remote else ''}"
                f"{f'origin/{default}' if not remote else ''} — the repository "
                "could not be read, which is not the same as being up to date")
    if head != remote:
        return (f"HEAD is not origin/{default} ({head[:12]} vs {remote[:12]}) — "
                f"switch to an up-to-date {default} first")
    return None
